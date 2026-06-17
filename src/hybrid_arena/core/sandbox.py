"""Ephemeral Docker sandbox for running untrusted generated code.

Used by the functional scorer to verify that generated code actually passes
the intended tests.  The sandbox is:

- *Ephemeral*: a fresh container is created + destroyed per invocation.
- *Network-isolated* by default (``network_mode="none"``).
- *Resource-capped*: memory, pids, and wall-clock time are bounded.
- *Output-bounded*: stdout / stderr each truncated to 16 KB (tail-preserving,
  because the *end* of a traceback is what you want).

Public API
----------

``run_in_sandbox(files, test_cmd, ...) -> SandboxResult``

Write ``files`` into a tempdir, mount it into a container at ``workdir``,
run ``test_cmd`` with the configured limits, and return a ``SandboxResult``.

If the Docker daemon is unreachable, ``RuntimeError("Docker not available")``
is raised with a helpful hint.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import docker  # type: ignore[import-untyped]
    from docker.errors import DockerException  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover - surfaced via RuntimeError at call time
    docker = None  # type: ignore[assignment]
    DockerException = Exception  # type: ignore[assignment,misc]
    _IMPORT_ERROR: Optional[BaseException] = exc
else:
    _IMPORT_ERROR = None


# Each log stream (stdout, stderr) is truncated to this many bytes.
# Truncation is tail-preserving: when a traceback blows past the cap, we keep
# the tail because the failing line + error type sit at the end.
_LOG_TRUNCATE_BYTES = 16 * 1024


@dataclass
class SandboxResult:
    """Outcome of a single sandboxed run."""

    passed: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    duration_ms: int
    timed_out: bool


def _get_client():
    """Return a connected Docker client, or raise RuntimeError with context."""
    if docker is None:
        raise RuntimeError(
            "Docker not available: the `docker` Python SDK is not installed. "
            "Install with `pip install docker`."
        ) from _IMPORT_ERROR
    try:
        client = docker.from_env()
        # Force a round-trip so we fail fast if the daemon is down.
        client.ping()
        return client
    except DockerException as exc:
        raise RuntimeError(
            "Docker not available: could not connect to the Docker daemon. "
            "Is Docker Desktop / dockerd running? "
            f"Underlying error: {exc!s}"
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(
            f"Docker not available: unexpected error contacting daemon ({exc!s})."
        ) from exc


def _truncate_tail(data: bytes, limit: int = _LOG_TRUNCATE_BYTES) -> str:
    """Decode ``data`` as UTF-8 (replacement on errors) and keep the last
    ``limit`` bytes if it is longer.  Errors are more useful than prologues."""
    if data is None:
        return ""
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace")
    truncated = data[-limit:]
    prefix = b"[...truncated...]\n"
    return (prefix + truncated).decode("utf-8", errors="replace")


def _write_files(tempdir: Path, files: dict[str, str]) -> None:
    """Materialize ``files`` (rel_path -> content) under ``tempdir``."""
    for rel_path, content in files.items():
        if os.path.isabs(rel_path) or ".." in Path(rel_path).parts:
            raise ValueError(
                f"File path must be relative and not escape the workdir: {rel_path!r}"
            )
        dest = tempdir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def run_in_sandbox(
    files: dict[str, str],
    test_cmd: list[str],
    timeout_s: int = 30,
    image: str = "python:3.11-slim",
    workdir: str = "/workspace",
    memory_mb: int = 512,
    pids_limit: int = 128,
    network: str = "none",
) -> SandboxResult:
    """Run ``test_cmd`` inside an ephemeral container with ``files`` mounted.

    Parameters
    ----------
    files:
        Mapping of relative path -> file content.  Written into a tempdir that
        is bind-mounted at ``workdir`` inside the container.
    test_cmd:
        The command to run, e.g. ``["python", "-m", "pytest", "tests/"]``.
    timeout_s:
        Wall-clock timeout; on expiry the container is killed and
        ``timed_out=True`` is returned with ``exit_code=None``.
    image:
        Docker image tag.  Pulled on first use.
    workdir:
        Path inside the container where ``files`` are mounted and where the
        command runs.
    memory_mb:
        Hard memory limit.  OOM inside the container produces exit code 137.
    pids_limit:
        Cap on concurrent processes.
    network:
        Docker network mode; ``"none"`` (default) disables networking.

    Returns
    -------
    SandboxResult
        ``passed=True`` iff ``exit_code == 0`` and the run didn't time out.
    """
    client = _get_client()

    # On POSIX hosts, run the container under the host user's uid:gid so
    # any files the container writes into the bind-mounted tempdir (e.g.
    # ``__pycache__``) stay owned by us and ``TemporaryDirectory.cleanup``
    # can chmod them. Without this, root-owned ``__pycache__`` dirs leak
    # back and crash the cleanup with PermissionError on CI runners.
    import os as _os
    container_user: Optional[str] = None
    if hasattr(_os, "getuid"):
        container_user = f"{_os.getuid()}:{_os.getgid()}"

    with tempfile.TemporaryDirectory(prefix="sandbox-") as td:
        tempdir = Path(td)
        _write_files(tempdir, files)
        # macOS tempdirs are often under /var/folders/... which symlinks through
        # /private; Docker Desktop's file-sharing likes the resolved path.
        host_path = str(tempdir.resolve())

        container = None
        started = time.monotonic()
        timed_out = False
        exit_code: Optional[int] = None

        try:
            try:
                run_kwargs: dict = dict(
                    image=image,
                    command=test_cmd,
                    working_dir=workdir,
                    volumes={host_path: {"bind": workdir, "mode": "rw"}},
                    network_mode=network,
                    mem_limit=f"{memory_mb}m",
                    pids_limit=pids_limit,
                    detach=True,
                    stdout=True,
                    stderr=True,
                    # We'll remove manually so we can grab logs after exit/kill.
                    auto_remove=False,
                )
                if container_user is not None:
                    run_kwargs["user"] = container_user
                container = client.containers.run(**run_kwargs)
            except DockerException as exc:
                # Covers image-pull errors, invalid args, etc.
                raise RuntimeError(f"Docker not available: {exc!s}") from exc

            try:
                wait_result = container.wait(timeout=timeout_s)
                exit_code = int(wait_result.get("StatusCode", -1))
            except Exception:
                # docker-py raises requests.exceptions.ConnectionError /
                # ReadTimeout when the wait timeout hits.  Treat *any* wait
                # failure after startup as a timeout: we kill + force-remove.
                timed_out = True
                exit_code = None
                try:
                    container.kill()
                except DockerException:
                    # Already dead or removing; ignore.
                    pass

            duration_ms = int((time.monotonic() - started) * 1000)

            try:
                stdout_bytes = container.logs(stdout=True, stderr=False)
            except DockerException:
                stdout_bytes = b""
            try:
                stderr_bytes = container.logs(stdout=False, stderr=True)
            except DockerException:
                stderr_bytes = b""

            stdout = _truncate_tail(stdout_bytes)
            stderr = _truncate_tail(stderr_bytes)

            passed = (not timed_out) and exit_code == 0

            return SandboxResult(
                passed=passed,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
                timed_out=timed_out,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    # Best-effort cleanup; the container may already be gone.
                    pass
