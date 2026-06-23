"""Evaluation context — action log, agent state, and world snapshot for a run."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pm_sim.agent.conditions import OAUTH_BLOCKER_KEY
from pm_sim.agent.state import get_flag
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.health import compute_project_health

OAUTH_MARKERS = (OAUTH_BLOCKER_KEY, "OAuth")


@dataclass(frozen=True)
class ActionLogEntry:
  turn: int
  sim_time: str
  action_type: str
  payload: dict[str, Any]
  result: Any


@dataclass
class EvalContext:
  run_id: str
  scenario_id: str
  agent_id: str
  status: str
  start_time: datetime
  end_sim_time: datetime
  world_exec_id: str
  launch_slipped_days: int
  actions: list[ActionLogEntry]
  action_counts: dict[str, int]
  blockers_known: list[str]
  tradeoff_documented: bool
  docs: list[dict[str, Any]]
  milestones: list[dict[str, Any]]
  tasks: list[dict[str, Any]]
  project_health: str
  check_times: dict[str, str] = field(default_factory=dict)

  def sim_day_at(self, sim_time: str) -> int:
    dt = parse_sim_time(sim_time)
    return (dt.date() - self.start_time.date()).days + 1

  def deadline_end(self, sim_day: int) -> datetime:
    day_start = self.start_time + timedelta(days=sim_day - 1)
    return day_start.replace(hour=23, minute=59, second=59)

  def blockers_known_count(self) -> int:
    return len(self.blockers_known)


def _parse_json(raw: str | None, default: Any = None) -> Any:
  if raw is None:
    return default
  try:
    return json.loads(raw)
  except json.JSONDecodeError:
    return default


def _result_contains_blocker(result: Any) -> bool:
  if result is None:
    return False
  text = json.dumps(result) if not isinstance(result, str) else result
  return any(marker in text for marker in OAUTH_MARKERS)


def _load_actions(db: SimDatabase, run_id: str) -> list[ActionLogEntry]:
  rows = db.conn.execute(
    """
    SELECT turn, sim_time, action_type, payload, result
    FROM action_log
    WHERE run_id = ?
    ORDER BY turn, id
    """,
    (run_id,),
  ).fetchall()
  return [
    ActionLogEntry(
      turn=row["turn"],
      sim_time=row["sim_time"],
      action_type=row["action_type"],
      payload=_parse_json(row["payload"], {}),
      result=_parse_json(row["result"]),
    )
    for row in rows
  ]


def _derive_check_times(actions: list[ActionLogEntry]) -> dict[str, str]:
  times: dict[str, str] = {}
  chat_send_count = 0
  blockers_known: list[str] = []

  for entry in actions:
    if entry.action_type == "chat_send":
      chat_send_count += 1
      for threshold in (3, 5, 10, 15, 30):
        key = f"chat_send_gt_{threshold}"
        if chat_send_count > threshold and key not in times:
          times[key] = entry.sim_time

    if entry.action_type == "tasks_list" and "tasks_list" not in times:
      times["tasks_list"] = entry.sim_time

    if entry.action_type == "chat_read" and _result_contains_blocker(entry.result):
      if OAUTH_BLOCKER_KEY not in blockers_known:
        blockers_known.append(OAUTH_BLOCKER_KEY)
        times["blocker_known"] = entry.sim_time

    if entry.action_type == "email_send":
      topic = entry.payload.get("topic")
      if topic == "vendor_escalation" and "vendor_escalated" not in times:
        times["vendor_escalated"] = entry.sim_time
      if topic == "status_update" and "status_update" not in times:
        times["status_update"] = entry.sim_time
      recipient = entry.payload.get("to")
      if recipient and f"email_send_to_{recipient}" not in times:
        times[f"email_send_to_{recipient}"] = entry.sim_time

    if entry.action_type == "docs_write":
      if entry.payload.get("doc_type") == "decision-log" and "tradeoff_decision" not in times:
        times["tradeoff_decision"] = entry.sim_time

    if entry.action_type == "calendar_schedule":
      attendees = entry.payload.get("attendee_ids") or []
      if "sam" in attendees and "alex" in attendees and "meeting_sam_alex" not in times:
        times["meeting_sam_alex"] = entry.sim_time

  return times


def build_eval_context(db: SimDatabase, run_id: str) -> EvalContext:
  run = db.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
  if run is None:
    raise KeyError(f"Run not found: {run_id}")

  start_raw = db.get_meta("start_time")
  if start_raw is None:
    raise RuntimeError("start_time not set in sim_meta")
  start_time = parse_sim_time(start_raw)

  actions = _load_actions(db, run_id)
  end_sim_time = parse_sim_time(actions[-1].sim_time) if actions else start_time

  action_counts: dict[str, int] = {}
  for entry in actions:
    action_counts[entry.action_type] = action_counts.get(entry.action_type, 0) + 1

  docs = [
    dict(row)
    for row in db.conn.execute("SELECT * FROM docs").fetchall()
  ]
  milestones = [
    dict(row)
    for row in db.conn.execute("SELECT * FROM milestones").fetchall()
  ]
  tasks = [
    dict(row)
    for row in db.conn.execute("SELECT * FROM tasks").fetchall()
  ]

  blockers = get_flag(db, "blockers_known", [])
  if not isinstance(blockers, list):
    blockers = []

  check_times = _derive_check_times(actions)
  if OAUTH_BLOCKER_KEY in blockers and "blocker_known" not in check_times:
    for entry in actions:
      if entry.action_type == "chat_read":
        check_times["blocker_known"] = entry.sim_time
        break

  launch_row = next((m for m in milestones if m.get("id") == "launch"), None)
  if launch_row and launch_row.get("status") == "completed":
    launch_ts = db.get_meta("launch_sim_datetime")
    if launch_ts:
      check_times["launch_completed"] = launch_ts

  return EvalContext(
    run_id=run_id,
    scenario_id=run["scenario_id"],
    agent_id=run["agent_id"],
    status=run["status"],
    start_time=start_time,
    end_sim_time=end_sim_time,
    world_exec_id=db.get_meta("world_exec_id") or "exec",
    launch_slipped_days=int(db.get_meta("launch_slipped_days") or "0"),
    actions=actions,
    action_counts=action_counts,
    blockers_known=list(blockers),
    tradeoff_documented=bool(get_flag(db, "tradeoff_documented", False)),
    docs=docs,
    milestones=milestones,
    tasks=tasks,
    project_health=compute_project_health(db),
    check_times=check_times,
  )
