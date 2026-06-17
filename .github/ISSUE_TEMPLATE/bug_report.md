---
name: Bug report
about: Crash, hang, wrong result, or unexpected behavior in the harness, router, or analysis pipeline
title: "[bug] "
labels: ["bug"]
---

## Summary

<!-- One sentence: what is broken? -->

## Environment

- OS + version (e.g. macOS 14.5, Ubuntu 22.04):
- Python version (`python --version`):
- Node version (`node --version`):
- Ollama version (`ollama --version`):
- Docker version (`docker --version`):
- Repo commit (`git rev-parse HEAD`):
- Branch / tag (e.g. `v1.0.0`):

Output of `./arena env-detect` (paste the JSON or attach the file) is the most reliable single source for the above:

```json
<paste env-manifest.json here, or attach>
```

## Steps to reproduce

```bash
# exact commands that trigger the issue
```

## Expected behavior

<!-- What did you expect to happen? -->

## Actual behavior

<!-- What actually happened? -->

```text
<paste error output, traceback, or unexpected log lines>
```

## Additional context

<!-- Relevant variant config? Specific task that fails? Whether `--smoke` reproduces? Whether other routes work? Anything else that narrowed it down? -->
