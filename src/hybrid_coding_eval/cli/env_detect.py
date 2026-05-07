#!/usr/bin/env python3
"""Hardware + software manifest generator for hybrid-coding-eval.

Writes ``env-manifest.json`` capturing everything that can affect a run's
results: chip / core counts / RAM / memory bandwidth, Ollama daemon state
and loaded models, router-proxy reachability, API key presence (names only,
never values), git HEAD, and platform versions.

The manifest includes a self-hash (``sha256_of_own_content_minus_hash``)
computed over a canonical JSON serialisation of the manifest with that
field omitted — that hash is what result rows point at via
``hardware_profile_ref`` for reproducibility.

Usage::

    python bin/env-detect.py [--out env-manifest.json]

Design notes:
  * Graceful degradation — missing ollama / docker / proxy never raises.
  * Hard failure — unable to read git state (this script is meant to be
    run from inside the hybrid-coding-eval repo).
  * Stdlib + httpx only. No new dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SCHEMA_VERSION = 1

# Memory-bandwidth lookup (GB/s) by chip name. M-series don't expose this
# directly via sysctl / system_profiler, so we hardcode known values.
MEMORY_BANDWIDTH_GBPS = {
    "Apple M4 Max": 546,
    "Apple M4 Pro": 273,
    "Apple M4": 120,
    "Apple M3 Max": 400,  # 40-core GPU variant; 30-core is 300 — handled below
    "Apple M3 Pro": 150,
    "Apple M3": 100,
    "Apple M2 Ultra": 800,
    "Apple M2 Max": 400,
    "Apple M2 Pro": 200,
    "Apple M2": 100,
    "Apple M1 Ultra": 800,
    "Apple M1 Max": 400,
    "Apple M1 Pro": 200,
    "Apple M1": 68,
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, cwd: str | Path | None = None, timeout: float = 5.0) -> str | None:
    """Run ``cmd`` and return stripped stdout, or None on any failure."""
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def _run_required(cmd: list[str], *, cwd: str | Path | None = None) -> str:
    """Run ``cmd`` and return stripped stdout; raise RuntimeError on failure."""
    out = _run(cmd, cwd=cwd)
    if out is None:
        raise RuntimeError(f"required command failed: {' '.join(cmd)}")
    return out


# ---------------------------------------------------------------------------
# Platform / hardware
# ---------------------------------------------------------------------------

def detect_platform() -> dict[str, Any]:
    uname = platform.uname()
    node_version = _run(["node", "--version"])
    if node_version and node_version.startswith("v"):
        # Keep leading 'v' per the example payload in the spec.
        pass

    docker_raw = _run(["docker", "--version"])
    docker_version = None
    if docker_raw:
        m = re.search(r"(\d+\.\d+\.\d+)", docker_raw)
        docker_version = m.group(1) if m else docker_raw

    return {
        "os": uname.system,
        "release": uname.release,
        "arch": uname.machine,
        "python_version": sys.version.split()[0],
        "node_version": node_version,
        "docker_version": docker_version,
    }


def _sysctl(key: str) -> str | None:
    return _run(["sysctl", "-n", key])


def detect_hardware() -> dict[str, Any]:
    system = platform.system()
    if system != "Darwin":
        # Best-effort for non-macOS hosts; the benchmark is macOS-first but
        # the manifest should still be valid.
        ram_bytes = None
        try:
            if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names and "SC_PAGE_SIZE" in os.sysconf_names:
                ram_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError):
            ram_bytes = None
        ram_gb = round(ram_bytes / (1024 ** 3)) if ram_bytes else None
        return {
            "chip": platform.processor() or None,
            "cores_total": os.cpu_count(),
            "cores_performance": None,
            "cores_efficiency": None,
            "ram_gb": ram_gb,
            "memory_bandwidth_gbps": None,
            "gpu": {"type": "none", "name": None, "vram_gb": None},
        }

    chip = _sysctl("machdep.cpu.brand_string")
    perf = _sysctl("hw.perflevel0.physicalcpu")
    eff = _sysctl("hw.perflevel1.physicalcpu")
    total = _sysctl("hw.physicalcpu")
    memsize = _sysctl("hw.memsize")

    cores_performance = int(perf) if perf and perf.isdigit() else None
    cores_efficiency = int(eff) if eff and eff.isdigit() else None
    cores_total = int(total) if total and total.isdigit() else os.cpu_count()
    ram_gb = round(int(memsize) / (1024 ** 3)) if memsize and memsize.isdigit() else None

    bandwidth = _memory_bandwidth_for(chip)

    # On Apple Silicon, GPU is Metal-integrated with unified memory (VRAM=null).
    if chip and chip.startswith("Apple "):
        gpu_name = _gpu_name_darwin() or chip
        gpu = {"type": "metal-integrated", "name": gpu_name, "vram_gb": None}
    else:
        gpu = {"type": "none", "name": None, "vram_gb": None}

    return {
        "chip": chip,
        "cores_total": cores_total,
        "cores_performance": cores_performance,
        "cores_efficiency": cores_efficiency,
        "ram_gb": ram_gb,
        "memory_bandwidth_gbps": bandwidth,
        "gpu": gpu,
    }


def _memory_bandwidth_for(chip: str | None) -> int | None:
    if not chip:
        return None
    # Exact match first
    if chip in MEMORY_BANDWIDTH_GBPS:
        return MEMORY_BANDWIDTH_GBPS[chip]
    # Fallback — longest-prefix match (e.g. "Apple M3 Max 40-core" if
    # sysctl ever returned the long form).
    best: tuple[str, int] | None = None
    for key, val in MEMORY_BANDWIDTH_GBPS.items():
        if chip.startswith(key) and (best is None or len(key) > len(best[0])):
            best = (key, val)
    return best[1] if best else None


def _gpu_name_darwin() -> str | None:
    """Extract the GPU chipset model from ``system_profiler SPDisplaysDataType``.

    Cheap parse — we only want the display name ("Apple M4 Max"). If the
    command fails, return None.
    """
    out = _run(["system_profiler", "SPDisplaysDataType"], timeout=8.0)
    if not out:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Chipset Model:"):
            return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

_SIZE_UNITS = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
               "KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40}


def _parse_size_to_gb(token: str) -> float | None:
    """Parse "27 GB" / "613 MB" / "1.2GiB" → float GB. None if unparseable."""
    m = re.match(r"^\s*([\d.]+)\s*([KMGT]i?B|B)\s*$", token, re.IGNORECASE)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).upper()
    factor = _SIZE_UNITS.get(unit)
    if factor is None:
        return None
    return round(val * factor / 1e9, 2)


def _parse_ollama_table(text: str) -> list[dict[str, Any]]:
    """Parse ``ollama list`` / ``ollama ps`` tabular output.

    We expect a header row plus zero or more model rows. Columns vary across
    versions, but the first column is always the model NAME and a SIZE
    column (``27 GB`` style) is always present. Extract just those two.
    """
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0]
    header_upper = header.upper()
    if "NAME" not in header_upper:
        return []

    # Find SIZE column by header position
    size_idx = header_upper.find("SIZE")
    models: list[dict[str, Any]] = []
    for row in lines[1:]:
        # First token is model name
        parts = row.split()
        if not parts:
            continue
        name = parts[0]
        size_gb: float | None = None
        if size_idx >= 0 and len(row) > size_idx:
            # Grab the SIZE column value — it's "27 GB" (two tokens)
            # starting at size_idx.
            tail = row[size_idx:]
            m = re.match(r"\s*([\d.]+\s*[KMGT]?i?B)", tail, re.IGNORECASE)
            if m:
                size_gb = _parse_size_to_gb(m.group(1))
        models.append({"name": name, "size_gb": size_gb})
    return models


def detect_ollama() -> dict[str, Any]:
    installed = shutil.which("ollama") is not None
    if not installed:
        return {
            "installed": False,
            "version": None,
            "running": False,
            "loaded_models": [],
            "available_models": [],
        }

    version_raw = _run(["ollama", "--version"])
    version: str | None = None
    if version_raw:
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", version_raw)
        version = m.group(1) if m else version_raw

    # Is the daemon up? Short-timeout GET on the default port.
    running = False
    try:
        r = httpx.get("http://127.0.0.1:11434/", timeout=2.0)
        running = r.status_code == 200
    except httpx.HTTPError:
        running = False

    loaded_models: list[dict[str, Any]] = []
    available_models: list[dict[str, Any]] = []

    if running:
        ps_out = _run(["ollama", "ps"], timeout=10.0)
        if ps_out:
            parsed = _parse_ollama_table(ps_out)
            loaded_models = [{**m, "loaded": True} for m in parsed]
        list_out = _run(["ollama", "list"], timeout=10.0)
        if list_out:
            available_models = _parse_ollama_table(list_out)

    return {
        "installed": True,
        "version": version,
        "running": running,
        "loaded_models": loaded_models,
        "available_models": available_models,
    }


# ---------------------------------------------------------------------------
# Router proxy
# ---------------------------------------------------------------------------

def detect_router_proxy(port: int = 8787) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/healthz"
    try:
        r = httpx.get(url, timeout=3.0)
    except httpx.HTTPError:
        return {
            "reachable": False,
            "port": port,
            "local_model": None,
            "cloud_model": None,
            "cloud_key_present": None,
        }
    if r.status_code != 200:
        return {
            "reachable": False,
            "port": port,
            "local_model": None,
            "cloud_model": None,
            "cloud_key_present": None,
        }

    try:
        body = r.json()
    except ValueError:
        body = {}

    local = body.get("local") or {}
    cloud = body.get("cloud") or {}

    return {
        "reachable": True,
        "port": port,
        "local_model": local.get("model"),
        "cloud_model": cloud.get("model"),
        "cloud_key_present": bool(cloud.get("key_present")) if "key_present" in cloud else None,
    }


# ---------------------------------------------------------------------------
# API keys (presence only)
# ---------------------------------------------------------------------------

API_KEY_NAMES = ("OPENAI_API_KEY", "OPEN_AI_API_KEY", "ANTHROPIC_API_KEY")


def _parse_dotenv_keys(path: Path) -> set[str]:
    """Return the set of KEY names that have a non-empty value in ``path``.

    Minimal parser — we only care about presence, not values. Skips blank
    lines and ``#`` comments. Accepts ``KEY=...`` and ``export KEY=...``.
    Values may be quoted; a quoted-empty value counts as absent.
    """
    if not path.is_file():
        return set()
    present: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # Strip matching surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and val:
            present.add(key)
    return present


def detect_api_keys(repo_root: Path) -> dict[str, bool]:
    env_keys = _parse_dotenv_keys(repo_root / ".env")
    return {
        name: bool(os.environ.get(name)) or (name in env_keys)
        for name in API_KEY_NAMES
    }


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def detect_git(repo_root: Path) -> tuple[str, str]:
    """Return (sha, branch) for ``repo_root``. Raises RuntimeError on failure."""
    sha = _run_required(["git", "rev-parse", "HEAD"], cwd=repo_root)
    # branch --show-current prints empty on detached HEAD, which is fine.
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root) or ""
    return sha, branch


# ---------------------------------------------------------------------------
# Self-hash
# ---------------------------------------------------------------------------

HASH_FIELD = "sha256_of_own_content_minus_hash"

# Fields deliberately excluded from the self-hash. The hash is the
# ``hardware_profile_ref`` — a stable pointer to the *hardware + software
# identity* of this host, not its transient runtime state. Anything that
# legitimately changes minute-to-minute without the hardware changing
# (wall-clock, daemon up/down, what models are currently paged in) must be
# excluded so that two back-to-back detections on the same machine agree.
HASH_EXCLUDED_FIELDS = frozenset({HASH_FIELD, "generated_at"})

# Inside nested dicts we further drop runtime-state sub-fields. Note these
# DO appear in the manifest (they're useful for debugging a run) — they
# just don't participate in the identity hash.
_OLLAMA_RUNTIME_FIELDS = frozenset({"running", "loaded_models", "available_models"})
_ROUTER_RUNTIME_FIELDS = frozenset({"reachable", "cloud_key_present"})


def _hash_canonicalise(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``manifest`` with runtime-only fields stripped."""
    copy: dict[str, Any] = {}
    for k, v in manifest.items():
        if k in HASH_EXCLUDED_FIELDS:
            continue
        if k == "ollama" and isinstance(v, dict):
            copy[k] = {sk: sv for sk, sv in v.items() if sk not in _OLLAMA_RUNTIME_FIELDS}
        elif k == "router_proxy" and isinstance(v, dict):
            copy[k] = {sk: sv for sk, sv in v.items() if sk not in _ROUTER_RUNTIME_FIELDS}
        else:
            copy[k] = v
    return copy


def compute_self_hash(manifest: dict[str, Any]) -> str:
    payload = json.dumps(
        _hash_canonicalise(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    # The script lives at <repo>/bin/env-detect.py
    return Path(__file__).resolve().parent.parent


def build_manifest() -> dict[str, Any]:
    repo_root = _repo_root()
    git_sha, git_branch = detect_git(repo_root)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "git_branch": git_branch,
        "platform": detect_platform(),
        "hardware": detect_hardware(),
        "ollama": detect_ollama(),
        "router_proxy": detect_router_proxy(),
        "api_keys_detected": detect_api_keys(repo_root),
    }
    manifest[HASH_FIELD] = compute_self_hash(manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect hardware + software environment and write env-manifest.json",
    )
    parser.add_argument(
        "--out",
        default="env-manifest.json",
        help="Output path for the manifest JSON (default: ./env-manifest.json)",
    )
    args = parser.parse_args(argv)

    try:
        manifest = build_manifest()
    except RuntimeError as e:
        print(f"env-detect: fatal: {e}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    hw = manifest["hardware"]
    chip = hw.get("chip") or "unknown-chip"
    ram = hw.get("ram_gb")
    ram_str = f"{ram}GB" if ram is not None else "?GB"
    short_sha = (manifest["git_sha"] or "")[:7]
    print(f"wrote {out_path} — {chip}, {ram_str}, git {short_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
