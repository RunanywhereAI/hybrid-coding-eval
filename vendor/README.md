# vendor/

Optional third-party source we vendor or reference at build time. Treat
everything under `vendor/` as **read-only**: patch the wrapper in
`src/hybrid_coding_eval/agents/`, not the vendored source.

## Contents

| Path        | What it is                                              | License | Tracked in git? |
| ----------- | ------------------------------------------------------- | ------- | --------------- |
| `opencode/` | Fork of the `opencode` agent used by `agents/opencode.py` | MIT     | No (gitignored) |

## opencode/

- **Upstream fork**: `https://github.com/RunanywhereAI/opencode-1.git`,
  branch `feat/hybrid-routing-plugin`. The env vars
  `OPENCODE_GIT_URL` / `OPENCODE_GIT_REF` let you pin a different
  fork/ref without code edits.
- **License**: MIT (upstream).
- **What we use**: the `opencode` CLI binary, invoked as a subprocess
  by `src/hybrid_coding_eval/agents/opencode.py`. No library code is
  imported.
- **Auto-install**: only cloned when you opt in:

  ```bash
  BENCH_SETUP_OPENCODE=1 ./bench setup
  ```

  `./bench setup` skips the opencode clone by default because the fork
  is large and most users only benchmark the other three agents.
- **Manual refresh**:

  ```bash
  rm -rf vendor/opencode
  git clone --branch feat/hybrid-routing-plugin \
      https://github.com/RunanywhereAI/opencode-1.git vendor/opencode
  ```

If you find a bug in `vendor/opencode/`, **don't patch it here** —
patch our wrapper in `agents/opencode.py` instead, and file an
upstream issue/PR on the fork.
