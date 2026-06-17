"""T-01 — assert the Python and Node pricing loaders resolve the same file.

After the mono-repo migration, ``configs/pricing/pricing_tables.json``
is the single source of truth. Both loaders must:

1. Find that exact path (or agree on an env-overridden one).
2. Compute the same SHA256 over the bytes they load.

This guards against the failure mode where one language gets updated
rates and the other silently keeps stale ones.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_python_loader_resolves_to_configs_path():
    """Python loader must use ``configs/pricing/pricing_tables.json``."""
    from hybrid_arena.core.pricing import PRICING_META  # noqa: E402

    path = Path(PRICING_META["path"])
    assert path.is_file(), f"path reported by loader does not exist: {path}"
    # Must be under configs/pricing/ — the post-reorg location.
    rel = path.relative_to(_REPO_ROOT)
    assert rel == Path("configs/pricing/pricing_tables.json"), (
        f"python loader resolved to unexpected path: {rel}"
    )


def test_python_loader_sha_matches_file_sha():
    from hybrid_arena.core.pricing import PRICING_META  # noqa: E402

    bytes_on_disk = Path(PRICING_META["path"]).read_bytes()
    disk_sha = hashlib.sha256(bytes_on_disk).hexdigest()
    assert PRICING_META["sha256"] == disk_sha


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_node_loader_sha_matches_python_loader_sha():
    """Spawn node, import ``router/pricing.mjs``, dump its PRICING_META.

    Assert the SHA256 it computed matches the Python side's SHA256.
    """
    from hybrid_arena.core.pricing import PRICING_META as PY_META  # noqa: E402

    shim = (
        "import { PRICING_META } from './router/pricing.mjs';\n"
        "process.stdout.write(JSON.stringify(PRICING_META));\n"
    )
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", shim],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, f"node failed: {proc.stderr!r}"
    js_meta = json.loads(proc.stdout)
    assert js_meta["sha256"] == PY_META["sha256"], (
        f"SHA mismatch — py={PY_META['sha256'][:12]}… "
        f"js={js_meta['sha256'][:12]}…"
    )
    # And both should be pointing at the new canonical path.
    assert "configs/pricing/pricing_tables.json" in js_meta["path"]
