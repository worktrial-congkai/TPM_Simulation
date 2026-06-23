"""Rubric scoring — component scores, penalties, weighted total."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from pm_sim.agent.conditions import OAUTH_BLOCKER_KEY
from pm_sim.eval.conditions import (
  condition_satisfied_at,
  evaluate_rubric_condition,
  parse_deadline_sim_day,
  penalty_severity,
)
from pm_sim.eval.context import EvalContext
from pm_sim.eval.rubric import RubricCheck, RubricComponent, RubricSpec
from pm_sim.sim.clock import parse_sim_time

DEFAULT_FULL_CREDIT_MINUTES = 30
DEFAULT_DECAY_MINUTES = 60
DEFAULT_ON_TIME_FLOOR = 0.4
DEFAULT_LATE_DECAY_DAYS = 1.0
DEFAULT_PENALTY_MAX = 2.0
DEFAULT_PENALTY_SCALE = 5.0


@dataclass(frozen=True)
class ComponentScore:
  component_id: str
  score: float
  weight: float
  check_results: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RubricScore:
  components: tuple[ComponentScore, ...]
  penalties: tuple[str, ...]
  total: float


def _deadline_day_start(ctx: EvalContext, deadline_day: int):
  return ctx.start_time + timedelta(days=deadline_day - 1)


def _score_condition_fraction(check: RubricCheck, ctx: EvalContext) -> float:
  if not check.condition or not evaluate_rubric_condition(check.condition, ctx):
    return 0.0

  satisfied_at = condition_satisfied_at(ctx, check.condition)
  if satisfied_at is None:
    return 0.0

  deadline_day = parse_deadline_sim_day(check.deadline)
  if deadline_day is None:
    return 1.0

  satisfied_dt = parse_sim_time(satisfied_at)
  day_start = _deadline_day_start(ctx, deadline_day)
  deadline_end = ctx.deadline_end(deadline_day)

  full_credit_minutes = (
    check.full_credit_within_minutes
    if check.full_credit_within_minutes is not None
    else DEFAULT_FULL_CREDIT_MINUTES
  )
  decay_minutes = check.decay_minutes if check.decay_minutes is not None else DEFAULT_DECAY_MINUTES
  on_time_floor = check.on_time_floor if check.on_time_floor is not None else DEFAULT_ON_TIME_FLOOR
  late_decay_days = (
    check.late_decay_days if check.late_decay_days is not None else DEFAULT_LATE_DECAY_DAYS
  )

  full_credit_deadline = day_start + timedelta(minutes=full_credit_minutes)
  decay_end = full_credit_deadline + timedelta(minutes=decay_minutes)

  if satisfied_dt <= full_credit_deadline:
    return 1.0

  if satisfied_dt <= deadline_end:
    if satisfied_dt <= decay_end and decay_minutes > 0:
      elapsed = (satisfied_dt - full_credit_deadline).total_seconds()
      span = decay_minutes * 60
      return max(on_time_floor, 1.0 - (1.0 - on_time_floor) * (elapsed / span))
    return on_time_floor

  days_late = max(1, (satisfied_dt.date() - deadline_end.date()).days)
  return max(0.0, on_time_floor * (1.0 - days_late / late_decay_days))


def _score_penalty_deduction(check: RubricCheck, ctx: EvalContext) -> float:
  if not check.penalty_if:
    return 0.0
  severity = penalty_severity(check.penalty_if, ctx)
  if severity <= 0:
    return 0.0
  penalty_max = check.penalty_max if check.penalty_max is not None else DEFAULT_PENALTY_MAX
  penalty_scale = check.penalty_scale if check.penalty_scale is not None else DEFAULT_PENALTY_SCALE
  return min(penalty_max, severity / penalty_scale)


def _supplemental_penalties(ctx: EvalContext) -> list[str]:
  penalties: list[str] = []
  vendor_time = ctx.check_times.get("vendor_escalated")
  blocker_time = ctx.check_times.get("blocker_known")
  if vendor_time and blocker_time and parse_sim_time(vendor_time) < parse_sim_time(blocker_time):
    penalties.append("vendor_escalated_before_blocker_known")
  elif vendor_time and OAUTH_BLOCKER_KEY not in ctx.blockers_known:
    penalties.append("vendor_escalated_before_blocker_known")
  return penalties


def _score_project_outcome(component: RubricComponent, ctx: EvalContext) -> float:
  scoring = component.scoring
  launch = next((m for m in ctx.milestones if m.get("id") == "launch"), None)
  if launch is None or launch.get("status") != "completed":
    return float(scoring.get("launch_failed", 0))

  due_at = launch.get("due_at")
  launch_time = ctx.check_times.get("launch_completed")
  slipped = ctx.launch_slipped_days > 0
  on_time = not slipped
  if due_at and launch_time:
    on_time = parse_sim_time(launch_time) <= parse_sim_time(due_at) and not slipped

  if on_time:
    return float(scoring.get("on_time_launch", 10))

  if ctx.tradeoff_documented:
    return float(scoring.get("delayed_with_scope_cut", 7))

  return float(scoring.get("delayed_no_decision", 3))


def score_rubric(ctx: EvalContext, rubric: RubricSpec) -> RubricScore:
  supplemental = _supplemental_penalties(ctx)
  component_scores: list[ComponentScore] = []

  for component in rubric.components:
    if component.id == "project_outcome":
      score = _score_project_outcome(component, ctx)
      component_scores.append(
        ComponentScore(component_id=component.id, score=score, weight=component.weight)
      )
      continue

    condition_checks = [c for c in component.checks if c.condition]
    penalty_checks = [c for c in component.checks if c.penalty_if]

    points_per_check = 10.0 / len(condition_checks) if condition_checks else 0.0
    score = 10.0 if not condition_checks else 0.0
    check_results: dict[str, float] = {}

    for check in condition_checks:
      fraction = _score_condition_fraction(check, ctx)
      check_results[check.id] = round(fraction, 4)
      score += points_per_check * fraction

    for check in penalty_checks:
      deduction = _score_penalty_deduction(check, ctx)
      check_results[check.id] = round(deduction, 4)
      score = max(0.0, score - deduction)

    component_scores.append(
      ComponentScore(
        component_id=component.id,
        score=round(min(10.0, score), 2),
        weight=component.weight,
        check_results=check_results,
      )
    )

  total_weight = sum(c.weight for c in component_scores)
  if total_weight <= 0:
    total = 0.0
  else:
    total = sum(c.score * c.weight for c in component_scores) / total_weight

  all_penalties = list(supplemental)
  for component in rubric.components:
    for check in component.checks:
      if check.penalty_if and evaluate_rubric_condition(check.penalty_if, ctx):
        all_penalties.append(check.id)

  return RubricScore(
    components=tuple(component_scores),
    penalties=tuple(dict.fromkeys(all_penalties)),
    total=round(total, 2),
  )
