"""Tests for the YAML config loader + resolver + schema (T-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hybrid_coding_eval.core.config.loader import (
    dump_schema_json,
    load_config,
)
from hybrid_coding_eval.core.config.resolve import apply_overrides

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _minimal_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "variant_tag: test\nout_dir: results/runs/xx-test\n"
        "models:\n  cloud: gpt-5.5\n  local: devstral:24b\n",
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #


def test_load_minimal_config(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    assert cfg.variant_tag == "test"
    assert cfg.models.cloud == "gpt-5.5"
    assert cfg.models.local == "devstral:24b"
    # Defaults survive.
    assert cfg.benchmark.task_classes == ["puzzles", "refactors"]
    assert cfg.benchmark.agents == ["aider", "opencode", "cline"]


def test_unknown_fields_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "variant_tag: x\nout_dir: results/x\nmodels:\n  cloud: gpt-5.5\n"
        "  local: devstral:24b\n  nonsense: 42\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(p)


def test_env_substitution(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_TEST_MODEL", "super-model")
    p = tmp_path / "env.yaml"
    p.write_text(
        "variant_tag: envsub\nout_dir: results/x\n"
        "models:\n  cloud: ${ENV:MY_TEST_MODEL}\n  local: devstral:24b\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.models.cloud == "super-model"


def test_env_substitution_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("NEVER_SET_VAR", raising=False)
    p = tmp_path / "env.yaml"
    p.write_text(
        "variant_tag: envsub\nout_dir: results/x\n"
        "models:\n  cloud: ${ENV:NEVER_SET_VAR}\n  local: devstral:24b\n",
        encoding="utf-8",
    )
    with pytest.raises(KeyError):
        load_config(p)


# --------------------------------------------------------------------------- #
# apply_overrides
# --------------------------------------------------------------------------- #


def test_apply_override_scalar(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    merged = apply_overrides(cfg, ["models.cloud=gpt-5"])
    assert merged.models.cloud == "gpt-5"
    # Original unchanged.
    assert cfg.models.cloud == "gpt-5.5"


def test_apply_override_bool(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    merged = apply_overrides(cfg, ["benchmark.smoke=true", "router.prompt_cache=true"])
    assert merged.benchmark.smoke is True
    assert merged.router.prompt_cache is True


def test_apply_override_list(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    merged = apply_overrides(
        cfg, ["benchmark.task_classes=puzzles,refactors"]
    )
    assert merged.benchmark.task_classes == ["puzzles", "refactors"]


def test_apply_override_invalid_path(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    with pytest.raises(ValueError):
        apply_overrides(cfg, ["models.nonexistent=x"])


# --------------------------------------------------------------------------- #
# canonical SHA
# --------------------------------------------------------------------------- #


def test_canonical_sha_is_stable(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    sha1 = cfg.canonical_sha256()
    sha2 = cfg.canonical_sha256()
    assert sha1 == sha2
    assert len(sha1) == 64


def test_canonical_sha_changes_with_override(tmp_path):
    cfg = load_config(_minimal_yaml(tmp_path))
    other = apply_overrides(cfg, ["models.cloud=gpt-5"])
    assert cfg.canonical_sha256() != other.canonical_sha256()


# --------------------------------------------------------------------------- #
# schema JSON is in sync with the Pydantic model
# --------------------------------------------------------------------------- #


def test_schema_json_matches_model():
    checked_in = json.loads(
        (_REPO_ROOT / "configs" / "schema.json").read_text(encoding="utf-8")
    )
    from_model = dump_schema_json()
    assert checked_in == from_model, (
        "configs/schema.json is stale. Regenerate with ``./bench schema "
        "--out configs/schema.json`` and commit the diff."
    )
