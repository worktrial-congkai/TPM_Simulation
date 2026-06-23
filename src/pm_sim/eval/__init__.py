"""Evaluation package — metrics, rubric scoring, compare-agents."""

from pm_sim.eval.metrics import RunMetrics, compute_run_metrics
from pm_sim.eval.report import EvalReport, evaluate_run, format_compare_table, write_eval_artifacts

__all__ = [
  "EvalReport",
  "RunMetrics",
  "compute_run_metrics",
  "evaluate_run",
  "format_compare_table",
  "write_eval_artifacts",
]
