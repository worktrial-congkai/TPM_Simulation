"""Eval report formatting and artifact writers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pm_sim.eval.context import EvalContext, build_eval_context
from pm_sim.eval.metrics import RunMetrics, compute_run_metrics
from pm_sim.eval.rubric import RubricSpec, load_rubric
from pm_sim.eval.scoring import RubricScore, score_rubric
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.runs import run_artifact_dir


def _format_clock(iso_time: str | None) -> str:
  if not iso_time:
    return "null"
  dt = parse_sim_time(iso_time)
  return dt.strftime("%a %I:%M %p").replace(" 0", " ")


_COMPONENT_LABELS = {
  "blocker_discovery": "Blocker discovery",
  "stakeholder_alignment": "Stakeholder alignment",
  "project_outcome": "Project outcome",
  "communication_discipline": "Communication discipline",
}


@dataclass(frozen=True)
class EvalReport:
  run_id: str
  scenario_id: str
  agent_id: str
  status: str
  metrics: RunMetrics
  rubric: RubricScore

def evaluate_run(db: SimDatabase, run_id: str, scenario_id: str) -> EvalReport:
  ctx = build_eval_context(db, run_id)
  rubric = load_rubric(scenario_id)
  metrics = compute_run_metrics(db, run_id, ctx=ctx)
  rubric_score = score_rubric(ctx, rubric)
  return EvalReport(
    run_id=run_id,
    scenario_id=scenario_id,
    agent_id=ctx.agent_id,
    status=ctx.status,
    metrics=metrics,
    rubric=rubric_score,
  )


def format_report_text(report: EvalReport) -> str:
  lines = [
    f"Evaluation: {report.scenario_id} / {report.agent_id}",
    "─" * 40,
    f"Run status: {report.status}",
    "",
    f"{'Component':<24} {'Score':>6}  {'Weight':>6}",
  ]
  for comp in report.rubric.components:
    label = _COMPONENT_LABELS.get(comp.component_id, comp.component_id)
    weight_pct = f"{int(comp.weight * 100)}%"
    lines.append(f"{label:<24} {comp.score:>5.1f}/10  {weight_pct:>6}")

  lines.extend([
    "─" * 40,
    f"Total                   {report.rubric.total:>5.1f}/10",
    "",
    "Strategy metrics:",
    f"  launch_sim_datetime:      {_format_clock(report.metrics.launch_sim_datetime)}",
    f"  time_to_blocker_known:    {_format_clock(report.metrics.time_to_blocker_known)}",
    f"  time_to_vendor_escalated: {_format_clock(report.metrics.time_to_vendor_escalated)}",
    f"  time_to_critical_path_clear: {_format_clock(report.metrics.time_to_critical_path_clear)}",
    f"  time_to_tradeoff_decision: {_format_clock(report.metrics.time_to_tradeoff_decision)}",
    f"  launch_slipped_days:      {report.metrics.launch_slipped_days}",
    f"  total_turns:              {report.metrics.total_turns}",
    f"  total_tool_count:         {report.metrics.total_tool_count}",
    f"  chat_tool_count:          {report.metrics.chat_tool_count}",
    f"  email_tool_count:         {report.metrics.email_tool_count}",
    f"  meeting_tool_count:       {report.metrics.meeting_tool_count}",
  ])
  return "\n".join(lines)


def format_report_json(report: EvalReport) -> dict:
  return {
    "run_id": report.run_id,
    "scenario_id": report.scenario_id,
    "agent_id": report.agent_id,
    "status": report.status,
    "metrics": {
      "total_turns": report.metrics.total_turns,
      "wait_turns": report.metrics.wait_turns,
      "launch_sim_datetime": report.metrics.launch_sim_datetime,
      "time_to_blocker_known": report.metrics.time_to_blocker_known,
      "time_to_vendor_escalated": report.metrics.time_to_vendor_escalated,
      "time_to_critical_path_clear": report.metrics.time_to_critical_path_clear,
      "time_to_tradeoff_decision": report.metrics.time_to_tradeoff_decision,
      "launch_slipped_days": report.metrics.launch_slipped_days,
      "total_tool_count": report.metrics.total_tool_count,
      "chat_tool_count": report.metrics.chat_tool_count,
      "email_tool_count": report.metrics.email_tool_count,
      "meeting_tool_count": report.metrics.meeting_tool_count,
    },
    "rubric": {
      "total": report.rubric.total,
      "components": [
        {
          "id": c.component_id,
          "score": c.score,
          "weight": c.weight,
          "check_results": dict(c.check_results),
        }
        for c in report.rubric.components
      ],
    },
  }


def write_eval_artifacts(report: EvalReport, artifact_dir: Path | None = None) -> Path:
  base = artifact_dir or run_artifact_dir(report.run_id)
  base.mkdir(parents=True, exist_ok=True)
  (base / "eval.txt").write_text(format_report_text(report) + "\n", encoding="utf-8")
  (base / "eval.json").write_text(
    json.dumps(format_report_json(report), indent=2) + "\n",
    encoding="utf-8",
  )
  return base


def format_launch_display(metrics: RunMetrics) -> str:
  if not metrics.launch_sim_datetime:
    return "null"
  label = _format_clock(metrics.launch_sim_datetime)
  if metrics.launch_slipped_days > 0:
    label += f" (+{metrics.launch_slipped_days} slip)"
  return label


def format_compare_row(agent_id: str, report: EvalReport) -> str:
  launch = format_launch_display(report.metrics)
  blocker = _format_clock(report.metrics.time_to_blocker_known)
  return (
    f"{agent_id:<16} {launch:<20} {blocker:<16} "
    f"{report.metrics.total_turns:<8} {report.rubric.total:.1f}"
  )


def _component_scores_by_id(report: EvalReport) -> dict[str, float]:
  return {comp.component_id: comp.score for comp in report.rubric.components}


def format_compare_rubric_rows(reports: list[EvalReport]) -> list[str]:
  """Rubric component breakdown rows for compare-agents output."""
  if not reports:
    return []

  sorted_reports = sorted(reports, key=lambda r: r.agent_id)
  component_ids = [comp.component_id for comp in sorted_reports[0].rubric.components]
  labels = [_COMPONENT_LABELS.get(component_id, component_id) for component_id in component_ids]
  col_widths = [len(label) + 2 for label in labels]

  header = f"{'Persona':<16}" + "".join(
    f"{label:>{width}}" for label, width in zip(labels, col_widths)
  )
  lines = [
    "",
    "Rubric components (/10):",
    header,
    "-" * len(header),
  ]
  for report in sorted_reports:
    scores = _component_scores_by_id(report)
    row = f"{report.agent_id:<16}" + "".join(
      f"{scores.get(component_id, 0.0):>{width}.1f}"
      for component_id, width in zip(component_ids, col_widths)
    )
    lines.append(row)
  return lines


def format_compare_table(reports: list[EvalReport]) -> str:
  header = (
    f"{'Persona':<16} {'launch_completed':<20} {'blocker_found':<16} "
    f"{'turns':<8} {'rubric'}"
  )
  lines = [header, "-" * len(header)]
  for report in sorted(reports, key=lambda r: r.agent_id):
    lines.append(format_compare_row(report.agent_id, report))
  lines.extend(format_compare_rubric_rows(reports))
  return "\n".join(lines)
