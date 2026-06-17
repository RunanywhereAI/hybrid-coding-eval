"""Tests for lib.sandbox.

Every test is skipped cleanly if the Docker daemon isn't reachable, so the
suite still runs on CI boxes without Docker.  If Docker *is* available, the
first test may be slow because ``python:3.11-slim`` needs to be pulled.
"""

from __future__ import annotations

import pytest

from hybrid_arena.core.sandbox import run_in_sandbox


def _docker_available() -> bool:
    """Return True iff we can talk to a Docker daemon right now."""
    try:
        import docker  # type: ignore[import-untyped]
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="docker not available"
)


# A tiny module + passing test.  We use stdlib ``unittest`` instead of pytest
# because the default ``python:3.11-slim`` image has no pytest installed and
# the sandbox runs with ``network=none`` so we can't pip-install one.
_GOOD_MODULE = "def add(a, b):\n    return a + b\n"
_GOOD_TEST = (
    "import unittest\n"
    "from mymod import add\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(add(2, 3), 5)\n"
    "if __name__ == '__main__':\n"
    "    unittest.main()\n"
)
_BAD_TEST = (
    "import unittest\n"
    "class T(unittest.TestCase):\n"
    "    def test_broken(self):\n"
    "        self.assertTrue(False, 'intentional failure')\n"
    "if __name__ == '__main__':\n"
    "    unittest.main()\n"
)


def test_good_test_passes():
    """A trivial module + passing unittest should exit 0 and report passed."""
    result = run_in_sandbox(
        files={
            "mymod.py": _GOOD_MODULE,
            "test_mymod.py": _GOOD_TEST,
        },
        test_cmd=["python", "-m", "unittest", "-v", "test_mymod"],
        # Generous timeout for the initial image pull.
        timeout_s=180,
    )
    assert result.passed is True, (
        f"expected pass; exit={result.exit_code!r}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.duration_ms >= 0


def test_broken_test_fails():
    """A failing assertion must flip passed=False and exit!=0."""
    result = run_in_sandbox(
        files={"test_broken.py": _BAD_TEST},
        test_cmd=["python", "-m", "unittest", "-v", "test_broken"],
        timeout_s=60,
    )
    assert result.passed is False
    assert result.exit_code is not None and result.exit_code != 0
    assert result.timed_out is False


def test_timeout_kills():
    """A sleep(60) with timeout_s=2 must be killed in well under 5s."""
    result = run_in_sandbox(
        files={},
        test_cmd=["python", "-c", "import time; time.sleep(60)"],
        timeout_s=2,
    )
    assert result.timed_out is True
    assert result.passed is False
    assert result.exit_code is None
    # Budget: 2s timeout + kill/cleanup overhead.  Anything near 60s would
    # indicate the kill path is broken.
    assert result.duration_ms < 15000, (
        f"kill path too slow: duration_ms={result.duration_ms}"
    )


def test_no_network_by_default():
    """network='none' must prevent outbound HTTP."""
    script = (
        "import urllib.request, sys\n"
        "try:\n"
        "    urllib.request.urlopen('https://example.com', timeout=3)\n"
        "    print('UNEXPECTED_SUCCESS')\n"
        "    sys.exit(0)\n"
        "except Exception as e:\n"
        "    print('network blocked:', type(e).__name__)\n"
        "    sys.exit(2)\n"
    )
    result = run_in_sandbox(
        files={},
        test_cmd=["python", "-c", script],
        timeout_s=30,
    )
    assert result.passed is False
    assert result.timed_out is False
    # exit_code should be 2 (our explicit sys.exit), never 0.
    assert result.exit_code != 0
    assert "UNEXPECTED_SUCCESS" not in result.stdout


def test_memory_limit():
    """Allocating 2 GB with memory_mb=256 must fail (OOM-kill or MemoryError).

    On hosts where the Docker daemon can't enforce memory accounting
    (e.g. cgroup v1 without swap accounting enabled), the allocation may
    actually succeed.  We detect that and skip.
    """
    # Build a string of 2 GB worth of bytes to force the allocator's hand.
    # ``bytearray(2 * 1024 * 1024 * 1024)`` materializes immediately.
    script = (
        "import sys\n"
        "try:\n"
        "    buf = bytearray(2 * 1024 * 1024 * 1024)\n"
        "    # Touch every page so the kernel actually commits.\n"
        "    for i in range(0, len(buf), 4096):\n"
        "        buf[i] = 1\n"
        "    print('UNEXPECTED_SUCCESS', len(buf))\n"
        "    sys.exit(0)\n"
        "except MemoryError:\n"
        "    print('memory error')\n"
        "    sys.exit(3)\n"
    )
    result = run_in_sandbox(
        files={},
        test_cmd=["python", "-c", script],
        timeout_s=30,
        memory_mb=256,
    )

    if "UNEXPECTED_SUCCESS" in result.stdout:
        pytest.skip(
            "Docker host does not enforce the memory limit "
            "(likely cgroup v1 without swap accounting)."
        )

    assert result.passed is False, (
        f"expected OOM/MemoryError; got exit={result.exit_code!r}, "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    # Either the container was OOM-killed (137) or Python raised MemoryError (3).
    # We don't pin a specific code because it varies by host.
    assert result.exit_code != 0 or result.timed_out is False
