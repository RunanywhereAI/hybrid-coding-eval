"""Tests for ``hybrid_coding_eval.cli.env_detect``.

Covers:

  1. End-to-end: the script runs on the current host and writes valid JSON.
  2. Schema: every expected key is present (null-valued is fine).
  3. Self-hash stability: two invocations back-to-back produce the same
     ``sha256_of_own_content_minus_hash`` (``generated_at`` is excluded
     from the hash by construction).
  4. Missing ollama: when ``shutil.which('ollama')`` returns None the
     manifest reports ``installed=false`` with safe empty lists.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from hybrid_coding_eval.cli import env_detect as ED

# ---------------------------------------------------------------------------
# Expected schema
# ---------------------------------------------------------------------------

TOP_LEVEL_KEYS = {
    "schema_version",
    "generated_at",
    "git_sha",
    "git_branch",
    "platform",
    "hardware",
    "ollama",
    "router_proxy",
    "api_keys_detected",
    "sha256_of_own_content_minus_hash",
}

PLATFORM_KEYS = {"os", "release", "arch", "python_version", "node_version", "docker_version"}
HARDWARE_KEYS = {"chip", "cores_total", "cores_performance", "cores_efficiency",
                 "ram_gb", "memory_bandwidth_gbps", "gpu"}
GPU_KEYS = {"type", "name", "vram_gb"}
OLLAMA_KEYS = {"installed", "version", "running", "loaded_models", "available_models"}
ROUTER_KEYS = {"reachable", "port", "local_model", "cloud_model", "cloud_key_present"}
API_KEY_NAMES = {"OPENAI_API_KEY", "OPEN_AI_API_KEY", "ANTHROPIC_API_KEY"}


# A session-scoped fixture would be overkill — the script runs in ~300ms.

def _run_and_load(tmp_path: Path) -> dict:
    out = tmp_path / "env-manifest.json"
    rc = ED.main(["--out", str(out)])
    assert rc == 0
    assert out.is_file()
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1: end-to-end — runs on the current host without crashing
# ---------------------------------------------------------------------------

def test_runs_without_crashing(tmp_path: Path):
    m = _run_and_load(tmp_path)
    # Minimal smoke — the manifest exists, is valid JSON (already asserted by
    # json.loads), and the top-level structure is a dict.
    assert isinstance(m, dict)
    assert m["schema_version"] == ED.SCHEMA_VERSION
    assert isinstance(m["git_sha"], str) and len(m["git_sha"]) == 40


# ---------------------------------------------------------------------------
# 2: schema validation — every expected field is present (null ok)
# ---------------------------------------------------------------------------

def test_schema_matches(tmp_path: Path):
    m = _run_and_load(tmp_path)

    # Top-level
    assert set(m.keys()) == TOP_LEVEL_KEYS, f"missing/extra keys: {set(m.keys()) ^ TOP_LEVEL_KEYS}"
    assert isinstance(m["generated_at"], str) and m["generated_at"].endswith("Z")
    assert isinstance(m["git_branch"], str)  # empty string allowed on detached HEAD

    # platform
    assert set(m["platform"].keys()) == PLATFORM_KEYS
    assert isinstance(m["platform"]["os"], str) and m["platform"]["os"]
    assert isinstance(m["platform"]["python_version"], str)

    # hardware
    assert set(m["hardware"].keys()) == HARDWARE_KEYS
    assert set(m["hardware"]["gpu"].keys()) == GPU_KEYS

    # ollama
    assert set(m["ollama"].keys()) == OLLAMA_KEYS
    assert isinstance(m["ollama"]["installed"], bool)
    assert isinstance(m["ollama"]["running"], bool)
    assert isinstance(m["ollama"]["loaded_models"], list)
    assert isinstance(m["ollama"]["available_models"], list)

    # router_proxy
    assert set(m["router_proxy"].keys()) == ROUTER_KEYS
    assert isinstance(m["router_proxy"]["reachable"], bool)
    assert m["router_proxy"]["port"] == 8787

    # api keys
    assert set(m["api_keys_detected"].keys()) == API_KEY_NAMES
    for v in m["api_keys_detected"].values():
        assert isinstance(v, bool)

    # self-hash
    assert isinstance(m["sha256_of_own_content_minus_hash"], str)
    assert len(m["sha256_of_own_content_minus_hash"]) == 64


# ---------------------------------------------------------------------------
# 3: self-hash stability
# ---------------------------------------------------------------------------

def test_self_hash_is_stable_across_runs(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    assert ED.main(["--out", str(a)]) == 0
    assert ED.main(["--out", str(b)]) == 0
    ma = json.loads(a.read_text(encoding="utf-8"))
    mb = json.loads(b.read_text(encoding="utf-8"))

    # generated_at is excluded from the hash, so the hashes MUST match even
    # if the timestamps differ (and in the common case they'll be equal too).
    assert ma["sha256_of_own_content_minus_hash"] == mb["sha256_of_own_content_minus_hash"]

    # Sanity — verify the hash function itself strips both HASH_FIELD and
    # generated_at before hashing (the only two intentionally-excluded fields).
    fixed = {"a": 1, "b": [1, 2, 3], "c": {"x": None}}
    h1 = ED.compute_self_hash(fixed)
    h2 = ED.compute_self_hash({**fixed, ED.HASH_FIELD: "whatever"})
    h3 = ED.compute_self_hash({**fixed, "generated_at": "2026-05-05T21:00:00Z"})
    assert h1 == h2 == h3


# ---------------------------------------------------------------------------
# 4: missing ollama graceful-degrades
# ---------------------------------------------------------------------------

def test_missing_ollama_is_safe():
    with mock.patch.object(ED.shutil, "which", side_effect=lambda name: None if name == "ollama" else "/usr/bin/" + name):
        result = ED.detect_ollama()
    assert result == {
        "installed": False,
        "version": None,
        "running": False,
        "loaded_models": [],
        "available_models": [],
    }
