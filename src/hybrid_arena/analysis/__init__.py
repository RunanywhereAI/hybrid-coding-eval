"""Post-experiment analysis pipeline.

Turns ``results/runs/<sweep>/raw.jsonl`` into the offline artefacts the
report consumes:

* :mod:`analysis.cost_scenarios` — re-price every row under the named
  pricing scenarios from ``configs/pricing/pricing_tables.json``.
* :mod:`analysis.aggregate` — per-``(category, route, strategy)`` medians,
  totals, success rates.
* :mod:`analysis.bootstrap` — 95% percentile CIs per cell.
* :mod:`analysis.decision_matrix` — ``category × route × strategy``
  recommendation grid rendered as Markdown.
* :mod:`analysis.all` — convenience CLI that wires them together.

Nothing in this package mutates ``raw.jsonl``. Every output is derived
(JSON / Markdown / PNG) and safe to regenerate.
"""
