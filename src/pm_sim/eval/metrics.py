"""Strategy metrics for evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from pm_sim.agent.conditions import OAUTH_BLOCKER_KEY
from pm_sim.eval.context import EvalContext, build_eval_context
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase

CHAT_TOOL_ACTIONS = frozenset({"chat_send", "chat_read"})
EMAIL_TOOL_ACTIONS = frozenset({"email_send", "email_read"})
MEETING_TOOL_ACTIONS = frozenset({
  "calendar_schedule",
  "calendar_list",
  "meeting_join",
  "meeting_transcript",
})
NON_TOOL_ACTIONS = frozenset({"wait", "policy_decision"})


@dataclass(frozen=True)
class RunMetrics:
  run_id: str
  scenario_id: str
  agent_id: str
  status: str
  total_turns: int
  wait_turns: int
  chat_tool_count: int
  email_tool_count: int
  meeting_tool_count: int
  total_tool_count: int
  launch_sim_datetime: str | None
  time_to_blocker_known: str | None
  time_to_vendor_escalated: str | None
  time_to_critical_path_clear: str | None
  time_to_tradeoff_decision: str | None
  launch_slipped_days: int


def _critical_path_clear_time(ctx: EvalContext) -> str | None:
  proj17 = next((t for t in ctx.tasks if t.get("id") == "PROJ-17"), None)
  proj22 = next((t for t in ctx.tasks if t.get("id") == "PROJ-22"), None)
  if not proj17 or not proj22:
    return None
  if proj17.get("status") == "blocked" or proj22.get("status") == "blocked":
    return None
  for entry in reversed(ctx.actions):
    if entry.action_type in ("tasks_update", "meeting_transcript"):
      return entry.sim_time
  return ctx.actions[-1].sim_time if ctx.actions else None


def _count_tool_actions(action_counts: dict[str, int], action_types: frozenset[str]) -> int:
  return sum(action_counts.get(action_type, 0) for action_type in action_types)


def _total_tool_count(action_counts: dict[str, int]) -> int:
  return sum(
    count
    for action_type, count in action_counts.items()
    if action_type not in NON_TOOL_ACTIONS
  )


def compute_run_metrics(
  db: SimDatabase,
  run_id: str,
  *,
  ctx: EvalContext | None = None,
) -> RunMetrics:
  if ctx is None:
    ctx = build_eval_context(db, run_id)

  total_turns = max((e.turn for e in ctx.actions), default=0)
  wait_turns = ctx.action_counts.get("wait", 0)

  time_to_blocker_known = ctx.check_times.get("blocker_known")
  if time_to_blocker_known is None and OAUTH_BLOCKER_KEY in ctx.blockers_known:
    for entry in ctx.actions:
      if entry.action_type == "chat_read":
        time_to_blocker_known = entry.sim_time
        break

  launch_sim_datetime = None
  launch = next((m for m in ctx.milestones if m.get("id") == "launch"), None)
  if launch and launch.get("status") == "completed":
    launch_sim_datetime = db.get_meta("launch_sim_datetime")

  time_to_vendor_escalated = ctx.check_times.get("vendor_escalated")
  time_to_tradeoff_decision = ctx.check_times.get("tradeoff_decision")

  time_to_critical_path_clear = _critical_path_clear_time(ctx)

  chat_tool_count = _count_tool_actions(ctx.action_counts, CHAT_TOOL_ACTIONS)
  email_tool_count = _count_tool_actions(ctx.action_counts, EMAIL_TOOL_ACTIONS)
  meeting_tool_count = _count_tool_actions(ctx.action_counts, MEETING_TOOL_ACTIONS)
  total_tool_count = _total_tool_count(ctx.action_counts)

  return RunMetrics(
    run_id=run_id,
    scenario_id=ctx.scenario_id,
    agent_id=ctx.agent_id,
    status=ctx.status,
    total_turns=total_turns,
    wait_turns=wait_turns,
    chat_tool_count=chat_tool_count,
    email_tool_count=email_tool_count,
    meeting_tool_count=meeting_tool_count,
    total_tool_count=total_tool_count,
    launch_sim_datetime=launch_sim_datetime,
    time_to_blocker_known=time_to_blocker_known,
    time_to_vendor_escalated=time_to_vendor_escalated,
    time_to_critical_path_clear=time_to_critical_path_clear,
    time_to_tradeoff_decision=time_to_tradeoff_decision,
    launch_slipped_days=ctx.launch_slipped_days,
  )
