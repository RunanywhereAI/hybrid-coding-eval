"""R5 — Stanford DevMinion-style hybrid runner (Aider-style review loop).

Wraps ``vendor/minions/minions/minion_code.py`` (MIT-licensed). The
DevMinion protocol follows an architect/editor review loop:

  1. Cloud supervisor generates a development *runbook* (list of steps).
  2. For each step, the local worker implements it, then the cloud
     supervisor reviews. If the review says "request_edits" the worker
     retries with feedback, up to ``max_edit_rounds`` times per step.
  3. After all steps complete, cloud conducts a final integration review.

Both clients are ``minions.clients.openai.OpenAIClient`` instances
pointed at our router proxy on ``:8787`` — the same OpenAIClient-via-proxy
trick R4 uses. The OpenAI-compatible API keeps the proxy as the single
place where routing decisions, cost accounting, and backend selection
happen.

- supervisor → ``model=router/always-cloud`` → gpt-5.5 via OpenAI.
- worker     → ``model=router/always-local`` → qwen/devstral via Ollama.

Public API matches R1/R2/R3/R4: ``run(task, ...) -> ResultRow``. Rows
get ``route="R5"`` and the same tokens/latency/quality/routing shape as
the other runners, so the orchestrator + analysis pipeline don't need
changes.

Scope: R5 supports the same categories as R4 (primarily SWE-bench
Verified, category B). DevMinion is designed for greenfield software
projects, but for SWE-bench we frame the task as "implement a patch
that fixes the problem statement" and extract the final code from the
workspace. For non-SWE tasks (A/C) the prompt is passed as ``task``
with an empty requirements string.

# TODO: extract shared helper — large portions of the monkey-patch /
# client-bootstrap code are copied from r4_minion.py. A later pass
# should lift `_resilient_extract_json`, the minions-vendor sys.path
# tricks, and the stubbing of Together/Gemini into a shared
# ``runners._minions_shim`` module.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the vendored Minion library importable. It expects to be on
# ``sys.path`` at the ``vendor/minions`` level — i.e. the directory that
# contains the ``minions/`` package.
try:
    from hybrid_coding_eval.core.paths import repo_root as _resolve_repo_root
    _REPO_ROOT = _resolve_repo_root()
except ModuleNotFoundError:  # pragma: no cover — during migration
    _here = Path(__file__).resolve()
    for _p in (_here, *_here.parents):
        if (_p / "pyproject.toml").is_file():
            _REPO_ROOT = _p
            break
    else:
        _REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_REPO_ROOT))
_MINIONS_VENDOR = _REPO_ROOT / "vendor" / "minions"
_MINIONS_LEGACY = _REPO_ROOT / "EXTERNAL" / "minions"
_MINIONS_DIR = _MINIONS_VENDOR if _MINIONS_VENDOR.exists() else _MINIONS_LEGACY
sys.path.insert(0, str(_MINIONS_DIR))

# ---------------------------------------------------------------------------
# Reuse the r4_minion bootstrap.
#
# Importing ``hybrid_coding_eval.runners.r4_minion`` has a side effect: it
# patches ``minions.minion._extract_json`` with a resilient parser, stubs
# Together/Gemini/Sambanova clients, and registers ``minions.clients.openai``
# et al. in ``sys.modules``. We piggy-back on that bootstrap so R5 doesn't
# duplicate the work and so we don't double-patch a module shared with R4.
# ---------------------------------------------------------------------------
# Now that ``minions.clients`` is populated with the stub classes plus
# ``OpenAIClient``, and ``minions.usage`` / ``minions.clients.openai`` /
# ``minions.clients.base`` are in ``sys.modules``, we can import the
# DevMinion module. Like ``minions.minion``, the ``minion_code`` module
# has its own ``_extract_json`` that we need to patch too.
import importlib.util as _iu  # noqa: E402

from hybrid_coding_eval.runners import r4_minion as _r4  # noqa: E402, F401

_DEV_MODNAME = "minions.minion_code"
if _DEV_MODNAME not in sys.modules:
    _spec = _iu.spec_from_file_location(
        _DEV_MODNAME, _MINIONS_DIR / "minions" / "minion_code.py"
    )
    _mod = _iu.module_from_spec(_spec)
    sys.modules[_DEV_MODNAME] = _mod
    _spec.loader.exec_module(_mod)
_minion_code_mod = sys.modules[_DEV_MODNAME]

# Patch DevMinion's JSON extractor with R4's resilient version. Also rebind
# the module-level ``json`` symbol to the same ``_JsonProxy`` R4 installed
# on ``minion`` — this makes ``json.loads`` inside minion_code call sites
# route through our resilient loader without mutating the global
# :mod:`json` module.
_minion_code_mod._extract_json = _r4._resilient_extract_json
_minion_code_mod.json = _r4._minion_mod.json

from minions.clients.openai import OpenAIClient  # noqa: E402
from minions.minion_code import DevMinion  # noqa: E402

from hybrid_coding_eval.core.metrics import (  # noqa: E402
    Latency,
    Quality,
    ResultRow,
    Routing,
    TokenUsage,
)

ROUTE = "R5"
PROXY_URL = "http://127.0.0.1:8787"
CLOUD_MODEL = "router/always-cloud"
LOCAL_MODEL = "router/always-local"


def _ensure_v1(base: str) -> str:
    """Normalise the proxy base URL to include ``/v1`` for the OpenAI SDK."""
    base = (base or "").rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _task_slug(task_id: str) -> str:
    return task_id.replace("/", "__").replace(" ", "_")


def _load_dotenv_once() -> None:
    """Populate ``os.environ`` from the repo-root ``.env``. Minimal parser."""
    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    if "OPENAI_API_KEY" not in os.environ and os.environ.get("OPEN_AI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPEN_AI_API_KEY"]


def _devminion_inputs(task: Any) -> tuple[str, str]:
    """Build ``(task, requirements)`` for DevMinion's ``__call__``.

    DevMinion's signature is ``(task: str, requirements: str = "", ...)``.
    Unlike Minion (which takes ``task`` + ``context: list[str]``), DevMinion
    wants a single natural-language task description plus a free-form
    requirements string.
    """
    from hybrid_coding_eval.runners._shared import task_prompt

    prompt = task_prompt(task)
    tid = task.id
    if tid.startswith("swebench-verified/"):
        ps = getattr(task, "problem_statement", "") or ""
        repo = getattr(task, "repo", "?")
        base_commit = getattr(task, "base_commit", "?")
        task_desc = (
            "Produce a unified diff patch that resolves the following "
            "problem statement from the repository. The final deliverable "
            "is a single ```diff ... ``` code block that applies cleanly "
            "with `git apply`."
        )
        requirements = (
            f"Repository: {repo}\n"
            f"Base commit: {base_commit}\n\n"
            f"Problem statement:\n{ps}"
        )
        return task_desc, requirements
    # Fallback for non-SWE tasks: prompt text as the task; empty requirements.
    return prompt, ""


def _aggregate_calls(result: dict[str, Any]) -> tuple[int, int, list[str]]:
    """Walk DevMinion's return dict to count cloud + local calls.

    DevMinion issues:
      - 1 cloud call to generate the runbook
      - For each step: attempts x (1 local impl + 1 cloud review)
      - 1 cloud call for the final integration review

    Return (cloud_calls, local_calls, per_call_backends).
    """
    cloud_calls = 0
    local_calls = 0
    backends: list[str] = []

    session_log = (result or {}).get("session_log") or {}
    # Runbook generation is always a cloud call if it happened (runbook is set).
    if session_log.get("runbook"):
        cloud_calls += 1
        backends.append("gpt-5.5")

    steps_completed = session_log.get("steps_completed") or []
    for step_result in steps_completed:
        attempts = (step_result or {}).get("attempts") or []
        for attempt in attempts:
            # One local implementation per attempt.
            if attempt.get("local_response") is not None:
                local_calls += 1
                backends.append(LOCAL_MODEL)
            # One cloud review per attempt.
            if attempt.get("review_decision") is not None:
                cloud_calls += 1
                backends.append("gpt-5.5")

    # Final integration review (cloud) if we made it that far.
    if session_log.get("final_assessment") is not None:
        cloud_calls += 1
        backends.append("gpt-5.5")

    return cloud_calls, local_calls, backends


# ---------------------------------------------------------------------------
# Deliverable extraction
#
# DevMinion's call() returns a dict whose ``final_assessment`` is a
# project-manager style JSON report ("quality_score", "project_status",
# "action_items", ...). That report is NOT the code the downstream scorers
# expect — the actual deliverable code lives in the ``workspace_dir`` on
# disk. The helper below walks the workspace, filters out DevMinion
# bookkeeping (test_files/, docs/, __pycache__/, .backups/), picks the
# files that represent the true deliverable for the task's category, and
# returns a text blob shaped like what R1/R2/R3/R4 emit — so the
# functional / SWE-bench / LLM-judge scorers can consume the output
# without any R5-specific special-casing.
# ---------------------------------------------------------------------------


# Directories the WorkspaceManager creates for its own bookkeeping. These
# never contain the deliverable and should be skipped when scanning.
_WORKSPACE_SKIP_DIRS: frozenset[str] = frozenset({
    ".backups",       # workspace backups (one per step)
    "__pycache__",    # Python bytecode
    "docs",           # per-step implementation notes DevMinion writes
    "test_files",     # copy of the predefined test files from the runbook
    "tests",          # occasional alternate location for predefined tests
    ".pytest_cache",
})


def _is_workspace_bookkeeping(path: Path, workspace_dir: Path) -> bool:
    """Return True if ``path`` is a WorkspaceManager-internal file, not a
    deliverable. Used to filter the workspace tree down to model output.
    """
    try:
        rel = path.relative_to(workspace_dir)
    except ValueError:
        return False
    parts = rel.parts
    # Skip anything inside a bookkeeping subdir.
    for segment in parts[:-1]:
        if segment in _WORKSPACE_SKIP_DIRS:
            return True
    # Skip files that the runbook's ``test_files`` shipped as predefined
    # pytest scaffolding — scorers supply their own tests.
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name in {"conftest.py", "pytest.ini", "setup.cfg", "pyproject.toml"}:
        return True
    return False


def _last_successful_code_changes(result: dict[str, Any]) -> dict[str, str]:
    """Return ``{filename: content}`` from the LAST step that merged its
    changes. Prefers ``final_code_changes`` (set on the step on ``merge_changes``);
    falls back to the last attempt's ``code_changes`` if no step merged.

    This gives us the specific files the step reviewer actually approved,
    which is more reliable than an arbitrary workspace walk for tasks where
    DevMinion created scaffolding files that aren't in the final solution.
    """
    session_log = (result or {}).get("session_log") or {}
    steps = session_log.get("steps_completed") or []

    # Walk from the LAST step backwards so we pick up the most recent merge.
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        final = step.get("final_code_changes") or {}
        if isinstance(final, dict) and final:
            return {str(k): str(v) for k, v in final.items()}

    # No step merged. Fall back to the last attempt's code_changes so we
    # at least emit something the scorer can look at.
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        for attempt in reversed(step.get("attempts") or []):
            changes = (attempt or {}).get("code_changes") or {}
            if isinstance(changes, dict) and changes:
                return {str(k): str(v) for k, v in changes.items()}

    # Last-ditch: DevMinion's JSON extractor sometimes fails on the worker's
    # response (e.g. when the worker wraps code in triple-quoted Python
    # strings inside a JSON blob). In that case ``code_changes`` is empty
    # but ``local_response`` still carries a code block we can harvest.
    # Walk the attempts newest-to-oldest and try to extract a ``"files":
    # {...}`` mapping OR a fenced code block + plausible filename hint.
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        for attempt in reversed(step.get("attempts") or []):
            lr = (attempt or {}).get("local_response")
            if not isinstance(lr, str) or not lr.strip():
                continue
            harvested = _harvest_files_from_response(lr)
            if harvested:
                return harvested
    return {}


def _harvest_files_from_response(text: str) -> dict[str, str]:
    """Best-effort extraction of ``{filename: content}`` from a raw worker
    response when DevMinion's own JSON parser failed to populate
    ``code_changes``.

    Three heuristics, in order:

    1. Look for fenced blocks introduced by a filename-looking label
       (``### solution.py`` / ``**solution.py**`` / ``File: solution.py``).
       This is the same shape ``real_dev.scorers._extract_labeled_fences``
       recognises.
    2. Look for a bare fenced ``python``/``py`` block; use the filename
       hinted by a surrounding label if we can find one.
    3. Look for a ``json`` fence whose body starts with ``"files":`` — the
       worker's canonical output shape. We extract ``{filename: content}``
       even when the content uses Python-style triple-quoted strings
       (which make the blob not valid JSON, hence why DevMinion's own
       parser tripped).
    """
    import re as _re

    # (1) labeled fence
    label_re = _re.compile(
        r"(?:^|\n)\s*(?:(?:\#{1,6}\s+)|(?:\*\*)|(?:File:\s*))?"
        r"(?P<name>[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)\*{0,2}\s*\n"
        r"(?:[^`]*?)```(?P<lang>[A-Za-z0-9_+-]*)\s*\n(?P<body>.*?)\n```",
        _re.DOTALL,
    )
    out: dict[str, str] = {}
    for m in label_re.finditer(text):
        name = m.group("name").strip()
        body = m.group("body")
        if name and body.strip() and name not in out:
            out[name] = body.rstrip() + "\n"
    if out:
        return out

    # (3) JSON-shaped "files": {...} wrapper. Handle it before the plain
    # python fence because the latter would false-positive on the outer
    # ```json fence whose body is not runnable Python.
    json_fence = _re.compile(
        r"```json\s*\n(.*?)\n```", _re.DOTALL | _re.IGNORECASE
    )
    # Filename -> either a double-quoted JSON string OR a triple-quoted
    # Python string. Both shapes have been observed in worker output.
    #   "solution.py": """\n<body>\n"""
    #   "solution.py": "body"
    json_file_entry = _re.compile(
        r"\"(?P<name>[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)\"\s*:\s*"
        r"(?:\"\"\"(?P<tq>.*?)\"\"\"|\"(?P<dq>(?:\\\\.|[^\"\\\\])*)\")",
        _re.DOTALL,
    )
    for m in json_fence.finditer(text):
        body = m.group(1)
        for entry in json_file_entry.finditer(body):
            name = entry.group("name")
            content = entry.group("tq") if entry.group("tq") is not None else entry.group("dq")
            if content is None:
                continue
            # Unescape JSON-escaped strings for the dq variant.
            if entry.group("dq") is not None:
                content = (
                    content.replace('\\n', '\n')
                    .replace('\\t', '\t')
                    .replace('\\"', '"')
                    .replace('\\\\', '\\')
                )
            if name not in out and content.strip():
                out[name] = content.rstrip() + "\n"
    if out:
        return out

    # (2) any python-ish fence; name it after a nearby mention if possible.
    fence_re = _re.compile(
        r"```(python|py|py3|sh|bash)\s*\n(.*?)\n```", _re.DOTALL | _re.IGNORECASE
    )
    filename_hint_re = _re.compile(r"(?:[#/*]\s*)?([A-Za-z0-9_./-]+\.(?:py|sh))")
    for m in fence_re.finditer(text):
        lang = m.group(1).lower()
        body = m.group(2)
        if not body.strip():
            continue
        # Scan the 120 chars before this fence for a filename hint.
        prefix = text[max(0, m.start() - 200) : m.start()]
        hint = None
        for mh in filename_hint_re.finditer(prefix):
            hint = mh.group(1)
        if hint is None:
            hint = "solution.py" if lang in ("python", "py", "py3") else "solution.sh"
        out[hint] = body.rstrip() + "\n"
        # Stop at the first block; models usually emit one per response.
        break
    return out


def _read_workspace_files(
    workspace_dir: Path, exts: tuple[str, ...] | None = None
) -> dict[str, str]:
    """Walk the workspace and return ``{relpath: content}`` for files that
    look like deliverables.

    - Honours :func:`_is_workspace_bookkeeping` to skip DevMinion scaffolding.
    - If ``exts`` is given, only includes files whose suffix matches.
    """
    out: dict[str, str] = {}
    if not workspace_dir.exists():
        return out
    for p in sorted(workspace_dir.rglob("*")):
        if not p.is_file():
            continue
        if _is_workspace_bookkeeping(p, workspace_dir):
            continue
        if exts and p.suffix not in exts:
            continue
        try:
            out[p.relative_to(workspace_dir).as_posix()] = p.read_text(
                encoding="utf-8", errors="replace"
            )
        except Exception:  # noqa: BLE001
            continue
    return out


def _merge_workspace_and_session(
    workspace_files: dict[str, str], session_files: dict[str, str]
) -> dict[str, str]:
    """Combine session-log ``final_code_changes`` with workspace files.

    Session files win when both contain the same key, but any file that
    only exists in the workspace (e.g. a file created in an earlier step
    but not modified in the last one) is still included.
    """
    merged: dict[str, str] = dict(workspace_files)
    for k, v in session_files.items():
        merged[k] = v
    return merged


def _find_diff(candidates: list[str]) -> str | None:
    """Scan ``candidates`` for the first value that contains a unified
    diff. Returns the diff body (unfenced) or ``None``.
    """
    import re as _re

    diff_fence = _re.compile(
        r"```(?:diff|patch|git|gitdiff)?\s*\n(.*?)```",
        _re.DOTALL | _re.IGNORECASE,
    )
    diff_git = _re.compile(r"^diff --git ", _re.MULTILINE)
    diff_minus = _re.compile(r"^--- [^\n]*\n\+\+\+ [^\n]*", _re.MULTILINE)

    for text in candidates:
        if not text or not isinstance(text, str):
            continue
        for m in diff_fence.finditer(text):
            body = m.group(1)
            if diff_git.search(body) or diff_minus.search(body):
                return body.strip()
        if diff_git.search(text) or diff_minus.search(text):
            # Trim prose before the first header.
            cuts = [
                mm.start()
                for mm in (diff_git.search(text), diff_minus.search(text))
                if mm
            ]
            if cuts:
                return text[min(cuts):].strip()
    return None


def _category(task: Any) -> str:
    cat = getattr(task, "category", None) or ""
    return str(cat).upper()


def _task_id_prefix(task: Any) -> str:
    tid = getattr(task, "id", "") or ""
    return tid.split("/", 1)[0] if tid else ""


def _task_shape(task: Any) -> str:
    return str(getattr(task, "shape", "") or "").upper()


def _extract_deliverables_from_workspace(
    workspace_dir: Path, task: Any, result: dict[str, Any]
) -> str:
    """Build the text payload for ``out_path`` so downstream scorers can
    consume DevMinion's output the same way they consume R1..R4.

    The shape of the payload is chosen based on the task:

    - HumanEval+/BigCodeBench-Hard (cat A/C functional): concat ``.py``
      deliverables inside a single ``python`` fenced block — matches what
      the functional_python scorer already expects when it calls
      :func:`extract_python_code`.
    - SWE-bench Verified (cat B): emit the diff if DevMinion produced one
      (fenced block in the final assessment, any ``*.patch``/``*.diff``
      file in the workspace, or an embedded diff in the session log). If
      no diff was produced, fall back to a fenced dump of the modified
      ``.py`` files so post-hoc inspection at least has something.
    - Category-D real-dev:
        * D1 / D5: concat ``.py`` / ``.sh`` with ``### <filename>`` headers
          so :func:`_extract_labeled_fences` in real_dev.scorers maps them
          onto the fixture's target filenames.
        * D2: same as SWE-bench (emit a diff).
        * D3: concat refactored files with ``### <filename>`` headers —
          llm_judge compares the blob to ``_reference/`` concatenation of
          the same shape.
        * D4: prose review; prefer a ``.md`` file, fall back to the
          final-assessment prose.
    - Custom-arch (C non-functional): return whatever prose DevMinion
      produced — any ``.md`` file, otherwise concat of all non-test files.
    """
    cat = _category(task)
    tid_prefix = _task_id_prefix(task)
    shape = _task_shape(task)

    # Collect candidate files from both the workspace and the session log's
    # last successful attempt. Session-log files are preferred since they're
    # the content the step-reviewer actually approved.
    workspace_all = _read_workspace_files(workspace_dir)
    session_files = _last_successful_code_changes(result)
    all_files = _merge_workspace_and_session(workspace_all, session_files)

    # Final-assessment candidates for diff scanning (B, D2).
    final_assessment = (result or {}).get("final_assessment") or {}
    session_log = (result or {}).get("session_log") or {}
    diff_search_pool: list[str] = []
    if isinstance(final_assessment, dict):
        # Some DevMinion prompts stash the full answer under "answer" or
        # "response" at the runbook level; fall through to any nested str.
        for key in ("answer", "response", "summary", "message", "notes"):
            v = final_assessment.get(key)
            if isinstance(v, str):
                diff_search_pool.append(v)
    # Last attempt's local_response also sometimes carries the diff.
    steps_completed = session_log.get("steps_completed") or []
    for step in reversed(steps_completed):
        for attempt in reversed((step or {}).get("attempts") or []):
            lr = (attempt or {}).get("local_response")
            if isinstance(lr, str):
                diff_search_pool.append(lr)
    # Finally: the final-assessment answer on the runbook.
    runbook = session_log.get("runbook") or {}
    if isinstance(runbook, dict):
        ans = runbook.get("answer")
        if isinstance(ans, str):
            diff_search_pool.append(ans)

    # ---- Category B (SWE-bench) and D2 (bug fix) — diff preferred ------
    is_swebench = cat == "B" or tid_prefix == "swebench-verified"
    is_d2 = shape == "D2"
    if is_swebench or is_d2:
        # 1) any .patch / .diff file in the workspace
        for rel, body in all_files.items():
            if rel.endswith((".patch", ".diff")):
                body = body.strip()
                if body:
                    return f"```diff\n{body}\n```\n"
        # 2) scan the session/final-assessment pool
        diff_body = _find_diff(diff_search_pool)
        if diff_body:
            return f"```diff\n{diff_body}\n```\n"
        # 3) nothing found — dump modified .py files as prose so the
        #    scorer at least records "no patch" rather than a synthetic
        #    pass. SWE-bench scorer returns no-patch when extract_diff()
        #    returns "", which is the honest signal.
        py_files = {
            k: v for k, v in all_files.items()
            if k.endswith(".py") and not _looks_like_test_name(k)
        }
        if not py_files:
            return "[R5] no diff produced by DevMinion\n"
        parts: list[str] = []
        for rel, body in sorted(py_files.items()):
            parts.append(f"### {rel}\n```python\n{body.rstrip()}\n```")
        return "\n\n".join(parts) + "\n"

    # ---- Category D3 (refactor) — labeled fences for the judge ---------
    if shape == "D3":
        py_files = {
            k: v for k, v in all_files.items()
            if k.endswith(".py") and not _looks_like_test_name(k)
        }
        if not py_files:
            # Fall through to generic prose dump below.
            py_files = {
                k: v for k, v in all_files.items()
                if not _looks_like_test_name(k)
            }
        parts = []
        for rel, body in sorted(py_files.items()):
            lang = "python" if rel.endswith(".py") else ""
            parts.append(f"### {rel}\n```{lang}\n{body.rstrip()}\n```")
        return ("\n\n".join(parts) + "\n") if parts else "[R5] no deliverable\n"

    # ---- Category D4 (PR review) — prose preferred ---------------------
    if shape == "D4":
        # Prefer any .md file the worker wrote (review.md / gold_review.md
        # shape). Skip DevMinion's own step docs since they're under docs/
        # which we already filter in _is_workspace_bookkeeping.
        md_files = {
            k: v for k, v in all_files.items()
            if k.endswith(".md")
        }
        if md_files:
            # If there's a file that looks like a review, prefer it.
            for pref in ("review.md", "pr_review.md", "code_review.md"):
                for k, v in md_files.items():
                    if k.endswith(pref):
                        return v.rstrip() + "\n"
            # Otherwise pick the largest .md (longest review tends to be
            # the deliverable rather than a one-line summary).
            largest = max(md_files.items(), key=lambda kv: len(kv[1]))
            return largest[1].rstrip() + "\n"
        # Fallback: any prose in the final assessment.
        for s in diff_search_pool:
            if s and len(s) > 80:
                return s.rstrip() + "\n"
        return "[R5] no review produced\n"

    # ---- Category C custom-arch — prose preferred ----------------------
    if tid_prefix == "custom-arch":
        md_files = {k: v for k, v in all_files.items() if k.endswith(".md")}
        if md_files:
            largest = max(md_files.items(), key=lambda kv: len(kv[1]))
            return largest[1].rstrip() + "\n"
        for s in diff_search_pool:
            if s and len(s) > 80:
                return s.rstrip() + "\n"
        return "[R5] no answer produced\n"

    # ---- Default path: A (HumanEval+), C (BCB-Hard), D1, D5 ------------
    # Concatenate non-test deliverables into a single fenced block so the
    # functional_python scorer's extract_python_code() finds the code.
    # For D1/D5 we also emit ``### <filename>`` headers so real_dev's
    # _extract_labeled_fences() can map files back onto the fixture
    # target filenames.
    is_real_dev = tid_prefix == "real-dev"
    target_exts = (".sh",) if (shape == "D5" and any(
        k.endswith(".sh") for k in all_files
    )) else (".py", ".sh")

    deliverable_files = {
        k: v for k, v in all_files.items()
        if any(k.endswith(e) for e in target_exts)
        and not _looks_like_test_name(k)
    }

    if not deliverable_files:
        # No python/shell file — but we still need SOMETHING for the scorer.
        # Dump any non-test file from the workspace.
        deliverable_files = {
            k: v for k, v in all_files.items()
            if not _looks_like_test_name(k)
        }

    if not deliverable_files:
        return "[R5] DevMinion produced no deliverable files\n"

    if is_real_dev:
        # Labeled fences for the real_dev scorer.
        parts = []
        for rel, body in sorted(deliverable_files.items()):
            lang = "python" if rel.endswith(".py") else (
                "bash" if rel.endswith(".sh") else ""
            )
            parts.append(f"### {rel}\n```{lang}\n{body.rstrip()}\n```")
        return "\n\n".join(parts) + "\n"

    # A / C-functional — concatenate .py files into one fenced block. The
    # functional_python scorer's extractor picks the largest block, so we
    # put them all inside one fence to keep the scorer's heuristics happy.
    pys = sorted(
        (k for k in deliverable_files if k.endswith(".py")),
        key=lambda k: (len(k), k),
    )
    if pys:
        bodies = [deliverable_files[k].rstrip() for k in pys]
        return "```python\n" + "\n\n".join(bodies) + "\n```\n"

    # Neither python nor shell: best-effort concat.
    bodies = [
        deliverable_files[k].rstrip() for k in sorted(deliverable_files)
    ]
    return "```\n" + "\n\n".join(bodies) + "\n```\n"


def _looks_like_test_name(relpath: str) -> bool:
    """True if ``relpath`` looks like a test file the model wrote. Separate
    from :func:`_is_workspace_bookkeeping` because the session-log's
    ``final_code_changes`` dict uses bare filenames without dir context.
    """
    name = Path(relpath).name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name in {"conftest.py"}:
        return True
    # ``tests/foo.py`` or ``test_files/foo.py`` — the parent dir gives it away.
    parts = Path(relpath).parts
    return any(p in {"tests", "test_files"} for p in parts[:-1])


def _gather_final_output(result: dict[str, Any], workspace_dir: Path) -> str:
    """Legacy wrapper retained for backwards compatibility with any caller
    (or test) that still expects the old "FINAL ASSESSMENT + workspace
    dump" format. New callers should prefer
    :func:`_extract_deliverables_from_workspace`.
    """
    lines: list[str] = []
    final = (result or {}).get("final_assessment") or {}
    if isinstance(final, dict) and final:
        lines.append("=== FINAL ASSESSMENT ===")
        lines.append(json.dumps(final, indent=2, ensure_ascii=False))
        lines.append("")
    if workspace_dir.exists():
        lines.append("=== WORKSPACE FILES ===")
        for p in sorted(workspace_dir.rglob("*")):
            if not p.is_file() or ".backups" in p.parts:
                continue
            try:
                rel = p.relative_to(workspace_dir)
            except ValueError:
                rel = p
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                content = "<binary or unreadable>"
            lines.append(f"\n--- {rel} ---")
            lines.append(content)
    return "\n".join(lines).strip() + "\n"


def run(
    task: Any,
    proxy_url: str = PROXY_URL,
    hardware_profile_ref: str = "",
    output_dir: Path | None = None,
    max_edit_rounds: int = 3,
    timeout_s: int = 1200,  # noqa: ARG001
) -> ResultRow:
    """Execute one task through the hybrid-DevMinion route."""
    _load_dotenv_once()

    if output_dir is None:
        output_dir = _REPO_ROOT / "results" / "r5"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _task_slug(task.id)
    out_path = output_dir / f"{slug}_R5.txt"
    workspace_dir = output_dir / f"{slug}_R5_workspace"
    log_dir = output_dir / f"{slug}_R5_logs"
    try:
        output_ref = str(out_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        output_ref = str(out_path.resolve())

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    base_url = _ensure_v1(proxy_url)
    # GPT-5.5 is a reasoning model — the proxy echoes back ``gpt-5.5-*``
    # regardless of the client-side ``model_name`` we use. DevMinion issues
    # runbook / review calls with ``response_format={'type': 'json_object'}``,
    # where the reasoning-token budget is counted against max_completion_tokens.
    # A 4000-token budget (what R4's ``Minion`` supervisor uses) empties
    # into reasoning alone and returns zero content. Bump to 16000 so
    # reasoning + JSON both fit.
    supervisor = OpenAIClient(
        model_name=CLOUD_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=16000,
    )
    worker = OpenAIClient(
        model_name=LOCAL_MODEL,
        api_key=api_key,
        base_url=base_url,
        max_tokens=4000,
        local=True,  # tells the library to return the 3-tuple shape
    )

    devminion = DevMinion(
        local_client=worker,
        remote_client=supervisor,
        workspace_dir=str(workspace_dir),
        max_edit_rounds=max_edit_rounds,
        log_dir=str(log_dir),
        backup_enabled=False,  # no need to version backups during a sweep
    )

    dm_task, dm_requirements = _devminion_inputs(task)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    result: dict[str, Any] | None = None
    err_msg: str | None = None
    try:
        result = devminion(
            task=dm_task,
            requirements=dm_requirements,
            logging_id=slug,
        )
    except Exception as exc:  # noqa: BLE001
        # DevMinion's JSON parse path is fragile on SWE-bench diffs. When
        # the resilient parser can't recover, surface the failure as a
        # skipped row rather than a crash. Keep whatever partial usage
        # the clients already recorded on ``devminion``.
        err_msg = f"devminion_error: {type(exc).__name__}: {str(exc)[:200]}"

    wall_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    if result is None:
        out_path.write_text(f"[R5 ERROR] {err_msg}\n", encoding="utf-8")
        return ResultRow(
            task_id=task.id,
            category=getattr(task, "category", "?"),
            route=ROUTE,
            hardware_profile_ref=hardware_profile_ref,
            tokens=TokenUsage(),
            latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
            quality=Quality(),
            routing=Routing(total_calls=0, local_calls=0, cloud_calls=0),
            output_ref=output_ref,
            started_at=started_at,
            finished_at=finished_at,
            error=err_msg,
        )

    # Aggregate usage. DevMinion returns Usage dataclasses from minions.usage.
    remote_usage = result.get("remote_usage")
    local_usage = result.get("local_usage")
    r_prompt = getattr(remote_usage, "prompt_tokens", 0) or 0
    r_comp = getattr(remote_usage, "completion_tokens", 0) or 0
    l_prompt = getattr(local_usage, "prompt_tokens", 0) or 0
    l_comp = getattr(local_usage, "completion_tokens", 0) or 0

    cloud_calls, local_calls, backends = _aggregate_calls(result)

    # Write the deliverable in a shape the downstream scorers expect.
    # See _extract_deliverables_from_workspace for the per-category rules.
    # The workspace directory is kept as-is for audit (DevMinion's logs,
    # predefined test_files, and per-step docs all remain on disk).
    final_text = _extract_deliverables_from_workspace(
        workspace_dir, task, result
    )
    out_path.write_text(final_text, encoding="utf-8")

    return ResultRow(
        task_id=task.id,
        category=getattr(task, "category", "?"),
        route=ROUTE,
        hardware_profile_ref=hardware_profile_ref,
        tokens=TokenUsage(
            prompt=r_prompt + l_prompt,
            completion=r_comp + l_comp,
            cached=0,
            reasoning=0,
            local_prompt=l_prompt,
            local_completion=l_comp,
            cloud_prompt=r_prompt,
            cloud_completion=r_comp,
        ),
        latency=Latency(wall_ms=wall_ms, per_call_ms=[wall_ms]),
        quality=Quality(),
        routing=Routing(
            total_calls=cloud_calls + local_calls,
            local_calls=local_calls,
            cloud_calls=cloud_calls,
            per_call_backends=backends,
        ),
        output_ref=output_ref,
        started_at=started_at,
        finished_at=finished_at,
        error=None,
    )


def main() -> int:
    import argparse

    from hybrid_coding_eval.benchmarks.swebench_verified import adapter as swe_adapter

    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", help="specific SWE-bench task id (else first)")
    ap.add_argument("--out", default="results/r5")
    args = ap.parse_args()

    tasks = {t.id: t for t in swe_adapter.load_tasks(n=10, seed=42)}
    if args.task_id:
        task = tasks[args.task_id]
    else:
        task = next(iter(tasks.values()))
    row = run(task, output_dir=Path(args.out))
    print(json.dumps({
        "task_id": row.task_id,
        "route": row.route,
        "tokens": row.tokens.__dict__,
        "wall_ms": row.latency.wall_ms,
        "output_ref": row.output_ref,
        "error": row.error,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
