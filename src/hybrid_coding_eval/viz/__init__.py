"""Matplotlib charts for the eval report.

Two scripts, both headless-safe (``matplotlib.use('Agg')`` before the
pyplot import) and both writing PNGs into ``results/<date>/charts/``.

  * :mod:`viz.cost_quality_pareto` — scatter of cost vs quality per
    (task × route), with a dashed Pareto-frontier.
  * :mod:`viz.decision_heatmap` — category × route heatmap of a
    parameterised metric (quality / cost / wall_ms).
"""
