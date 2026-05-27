# Security policy

`hybrid-coding-eval` is a research artefact, not a hosted service.
That said, two surfaces have real security implications:

1. The Node **router proxy** on `127.0.0.1:8787` forwards bearer-token
   authenticated requests to OpenAI / Anthropic on behalf of the agent
   subprocesses it spawns. It binds loopback only and ships without
   auth — never expose it on a non-loopback interface.
2. Agent subprocesses (`aider`, `opencode`, `mini-swe-agent`, `cline`)
   execute model-suggested code inside a Docker sandbox
   (`scorers/Dockerfile.functional_python`) with `--network none` and
   memory caps. The sandbox is hardening, not a security boundary —
   don't run this harness against untrusted models with critical secrets
   on the same machine.

## Reporting a vulnerability

Please **do not open public GitHub issues** for security findings.
Instead, email the maintainer privately:

> **security@runanywhere.ai** (preferred)
>
> or open a draft GitHub Security Advisory at
> <https://github.com/RunanywhereAI/hybrid-coding-eval/security/advisories/new>

We aim to triage within **5 business days** and ship a fix within
**30 days** for high-severity issues (CVSS ≥ 7.0). We'll credit you in
the release notes unless you ask us not to.

## In-scope

- Code execution outside the Docker sandbox triggered by adversarial
  model output.
- Secret exfiltration via the router proxy (token leakage,
  cross-strategy session bleed).
- Path-traversal / arbitrary-file-write via the task adapters.
- Supply-chain issues in the Python or Node dependency tree.

## Out-of-scope

- Issues that only affect a `--external-router` deployment where the user
  has bound the proxy to non-loopback by hand.
- Issues that require an attacker with shell access to the host running
  the sweep.
- Findings against vendored third-party code (`vendor/opencode/`) —
  please report those to the respective upstream maintainer; we'll
  pull updates once they ship.

## Coordinated disclosure

If you give us a private reproduction case, we will:

1. Acknowledge within 5 business days.
2. Confirm or contest the finding within 14 days.
3. Ship a patch + advisory within 30 days for high-severity issues.
4. Credit you in the release notes and the advisory.

Thank you for helping keep the project safe.
