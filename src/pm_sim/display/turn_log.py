"""Turn log formatting and artifact writers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pm_sim.agent.state import get_flag
from pm_sim.agent.types import AgentAction, Observation
from pm_sim.display.turn_collapser import TurnLogCollapser, TurnLogPushResult, format_collapsed_block
from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase

OAUTH_BLOCKER_KEY = "PROJ-17_oauth_scope"


def _quote_snippet(text: str, max_len: int = 80) -> str:
  collapsed = " ".join(text.split())
  if len(collapsed) > max_len:
    collapsed = collapsed[: max_len - 1] + "…"
  return f'"{collapsed}"'


def _sim_day_label(sim_time: datetime, start_time: datetime) -> str:
  day = (sim_time.date() - start_time.date()).days + 1
  return f"Day {day}"


def _format_clock(sim_time: datetime) -> str:
  return sim_time.strftime("%a %I:%M %p").replace(" 0", " ")


def _task_label(task_id: str, title: str) -> str:
  return f"{task_id} ({title})"


def _task_title(db: SimDatabase, task_id: str) -> str | None:
  row = db.conn.execute(
    "SELECT title FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  return row["title"] if row else None


def _blocked_task_labels(db: SimDatabase) -> list[str]:
  rows = db.conn.execute(
    """
    SELECT id, title FROM tasks
    WHERE critical_path = 1 AND status = 'blocked'
    ORDER BY id
    """
  ).fetchall()
  return [_task_label(row["id"], row["title"]) for row in rows]


def _all_task_labels(db: SimDatabase) -> list[str]:
  rows = db.conn.execute(
    """
    SELECT id, title FROM tasks
    ORDER BY id
    """
  ).fetchall()
  return [_task_label(row["id"], row["title"]) for row in rows]


def _email_subject(db: SimDatabase, email_id: str) -> str | None:
  row = db.conn.execute(
    "SELECT subject FROM emails WHERE id = ?",
    (email_id,),
  ).fetchone()
  return row["subject"] if row else None


def _format_email_action(payload: dict[str, Any]) -> str:
  to = payload.get("to", "?")
  subject = payload.get("subject", "")
  body = payload.get("body", "")
  parts = [f"email send → {to}"]
  if subject:
    parts.append(_quote_snippet(subject, max_len=60))
  if body:
    parts.append(_quote_snippet(body))
  return ": ".join(parts)


def _pending_npc_replies(db: SimDatabase) -> list[tuple[str, datetime]]:
  rows = db.conn.execute(
    """
    SELECT actor_id, start_ts FROM events
    WHERE event_type = 'npc.reply' AND status = 'pending'
    ORDER BY start_ts, id
    """
  ).fetchall()
  return [
    (row["actor_id"] or "npc", parse_sim_time(row["start_ts"]))
    for row in rows
  ]


def _latest_action_log_entry(db: SimDatabase, turn: int) -> dict[str, Any] | None:
  run_id = db.get_meta("active_run_id")
  if not run_id:
    return None
  row = db.conn.execute(
    """
    SELECT action_type, payload, result
    FROM action_log
    WHERE run_id = ? AND turn = ?
    ORDER BY id DESC
    LIMIT 1
    """,
    (run_id, turn),
  ).fetchone()
  if row is None:
    return None
  return {
    "action_type": row["action_type"],
    "payload": json.loads(row["payload"]) if row["payload"] else {},
    "result": json.loads(row["result"]) if row["result"] else {},
  }


def _blocked_task_summaries(db: SimDatabase) -> list[str]:
  rows = db.conn.execute(
    """
    SELECT id, blocker_reason FROM tasks
    WHERE critical_path = 1 AND status = 'blocked'
    ORDER BY id
    """
  ).fetchall()
  return [
    f"{row['id']} blocked ({row['blocker_reason'] or 'unknown'})"
    for row in rows
  ]


def _describe_processed_event(db: SimDatabase, event_id: str) -> str:
  row = db.conn.execute(
    "SELECT event_type, actor_id, payload FROM events WHERE id = ?",
    (event_id,),
  ).fetchone()
  if row is None:
    return event_id[:8]

  event_type = row["event_type"]
  actor_id = row["actor_id"]
  payload = json.loads(row["payload"]) if row["payload"] else {}

  if event_type == "npc.reply":
    body = payload.get("body", "")
    if body:
      return f"{actor_id or 'npc'} reply: {_quote_snippet(body)}"
    return f"{actor_id or 'npc'} reply"
  if event_type == "vendor.turnaround_complete":
    return "vendor turnaround complete"
  if event_type == "meeting.start":
    title = payload.get("title")
    if title:
      return f"meeting started: {title}"
    return "meeting started"
  if event_type == "task.complete":
    return f"{payload.get('task_id', 'task')} complete"
  if event_type == "milestone.check":
    launch = db.conn.execute(
      "SELECT status FROM milestones WHERE id = 'launch'"
    ).fetchone()
    if launch and launch["status"] == "completed":
      return "launch complete"
    return "milestone check"
  if event_type == "agent.chat_send":
    to = payload.get("to", "?")
    body = payload.get("body", "")
    if body:
      return f"agent → {to}: {_quote_snippet(body)}"
    return "chat_send"
  if event_type == "agent.tasks_update":
    task_id = payload.get("task_id", "task")
    return f"{task_id} started"
  if event_type.startswith("agent."):
    return event_type.removeprefix("agent.")
  return event_type


def _world_event_labels(db: SimDatabase, event_ids: list[str]) -> list[str]:
  labels: list[str] = []
  for event_id in event_ids:
    row = db.conn.execute(
      "SELECT event_type FROM events WHERE id = ?",
      (event_id,),
    ).fetchone()
    if row is None or row["event_type"].startswith("agent."):
      continue
    labels.append(_describe_processed_event(db, event_id))
  return labels


def _describe_tool_result(db: SimDatabase, turn: int, action: AgentAction) -> str | None:
  entry = _latest_action_log_entry(db, turn)
  if entry is None:
    return None

  action_type = entry["action_type"]
  payload = entry["payload"]
  result = entry["result"]

  if action_type == "tasks_list":
    blocked = _blocked_task_summaries(db)
    if blocked:
      return ", ".join(blocked)
    count = result.get("count", 0)
    return f"{count} task(s) listed"

  if action_type == "chat_send":
    body = payload.get("body", "")
    quoted = _quote_snippet(body) if body else None
    pending = _pending_npc_replies(db)
    if pending:
      actor, reply_at = pending[0]
      if quoted:
        return f"sent: {quoted} → reply ~{_format_clock(reply_at)} ({actor})"
      return f"Reply scheduled ~{_format_clock(reply_at)} ({actor})"
    if quoted:
      return f"sent: {quoted}"
    return "message sent"

  if action_type == "chat_read":
    blockers_known = get_flag(db, "blockers_known", [])
    if isinstance(blockers_known, list) and OAUTH_BLOCKER_KEY in blockers_known:
      return "OAuth scope disclosed → blocker_known"
    incoming = result.get("incoming", [])
    if incoming:
      parts = [
        f'read from {msg["sender_id"]}: {_quote_snippet(msg["body"])}'
        for msg in incoming
      ]
      return ", ".join(parts)
    count = result.get("count", 0)
    return f"{count} message(s) read"

  if action_type == "email_read":
    count = result.get("count", 0)
    return f"{count} email(s) read"

  if action_type == "email_send":
    topic = payload.get("topic")
    if topic == "vendor_escalation":
      row = db.conn.execute(
        """
        SELECT start_ts FROM events
        WHERE event_type = 'vendor.turnaround_complete' AND status = 'pending'
        ORDER BY start_ts
        LIMIT 1
        """
      ).fetchone()
      if row:
        at = parse_sim_time(row["start_ts"])
        return f"24h vendor timer scheduled (~{_format_clock(at)})"
      return "vendor escalation sent"
    pending = _pending_npc_replies(db)
    if pending:
      actor, reply_at = pending[0]
      return f"Reply scheduled ~{_format_clock(reply_at)} ({actor})"
    return "email sent"

  if action_type == "calendar_schedule":
    title = payload.get("title") or result.get("title")
    if title:
      return f"meeting scheduled: {title}"
    return "meeting scheduled"

  if action_type == "docs_write":
    title = result.get("title") or payload.get("title")
    if title:
      return f"doc written: {title}"
    return "doc written"

  if action_type == "tasks_update":
    task_id = payload.get("task_id") or result.get("id")
    if task_id and db is not None:
      title = _task_title(db, task_id)
      if title:
        return f"task started: {_task_label(task_id, title)}"
    if task_id:
      return f"task started: {task_id}"
    return "task started"

  if action_type == "send_status_update" or action.name == "send_status_update":
    return "status update sent"

  if action.name:
    return None
  return None


def format_observation_line(obs: Observation, db: SimDatabase, health: str) -> str:
  unread_chat = len(obs.unread_channels)
  unread_email = len(obs.unread_email_ids)
  blocker_labels = _blocked_task_labels(db)
  parts = [
    f"chat unread: {unread_chat}",
    f"email unread: {unread_email}",
    f"blockers: {', '.join(blocker_labels) if blocker_labels else 'none'}",
  ]

  if blocker_labels:
    if obs.blockers_known:
      known = ", ".join(obs.blockers_known)
      parts.append(f"blocker cause: discovered ({known})")
    else:
      parts.append("blocker cause: undiscovered")

  pending = _pending_npc_replies(db)
  if pending:
    await_parts = [f"{actor} ~{_format_clock(at)}" for actor, at in pending[:3]]
    parts.append(f"awaiting: {', '.join(await_parts)}")
  elif obs.waiting_on_reply:
    parts.append("awaiting: reply")

  parts.append(f"health: {health}")
  return "OBSERVE:  " + " | ".join(parts)


def format_action_label(action: AgentAction, db: SimDatabase | None = None) -> str:
  return _format_action_target(action, db)


def _format_action_target(action: AgentAction, db: SimDatabase | None = None) -> str:
  if action.type == "wait":
    return "wait"
  if action.type == "done":
    return "done"

  payload = action.payload or {}
  name = action.name
  if name == "tasks_list":
    if db is not None:
      tasks = ", ".join(_all_task_labels(db))
      return f"tasks list → {tasks} ({name})"
    return f"tasks list ({name})"
  if name == "read_dm":
    channel = payload.get("channel", "?")
    target = channel.split(":", 1)[-1] if channel.startswith("dm:") else channel
    return f"chat read → {target} ({name})"
  if name == "read_email":
    email_id = payload.get("email_id")
    if db is not None and email_id:
      subject = _email_subject(db, email_id)
      if subject:
        return f"email read → {_quote_snippet(subject, max_len=60)} ({name})"
    return f"email read ({name})"
  if name in ("ask_blocker_owner_dm", "spam_ping_dm"):
    target = payload.get("to", "?")
    body = payload.get("body", "")
    if body:
      return f"chat send → {target}: {_quote_snippet(body)} ({name})"
    return f"chat send → {target} ({name})"
  if name == "escalate_vendor":
    detail = _format_email_action(payload)
    return f"{detail} ({name})"
  if name == "schedule_requirements_meeting":
    title = payload.get("title", "Requirements review")
    return f"calendar schedule → {_quote_snippet(title, max_len=60)} ({name})"
  if name == "schedule_tradeoff_meeting":
    title = payload.get("title", "Launch tradeoff discussion")
    return f"calendar schedule → {_quote_snippet(title, max_len=60)} ({name})"
  if name == "write_decision_doc":
    title = payload.get("title", "")
    body = payload.get("body", "")
    if title and body:
      return (
        f"docs write → {_quote_snippet(title, max_len=60)}: "
        f"{_quote_snippet(body)} ({name})"
      )
    if title:
      return f"docs write → {_quote_snippet(title, max_len=60)} ({name})"
    return f"docs write ({name})"
  if name == "send_status_update":
    detail = _format_email_action(payload)
    return f"{detail} ({name})"
  if name == "start_next_critical_task":
    task_id = payload.get("task_id")
    if db is not None and task_id:
      title = _task_title(db, task_id)
      if title:
        return f"task start → {_task_label(task_id, title)} ({name})"
    if task_id:
      return f"task start → {task_id} ({name})"
    return f"task start ({name})"
  return f"{name}"


def format_result_line(
  action: AgentAction,
  *,
  db: SimDatabase | None = None,
  turn: int | None = None,
  processed_event_ids: list[str] | None = None,
  health: str | None = None,
  minutes_advanced: int | None = None,
) -> str:
  if action.type == "done":
    return "RESULT:   run ending (done)"

  if minutes_advanced and action.type in ("wait", "tool"):
    lines = [f"RESULT:   SIM: +{minutes_advanced}min"]
    if action.type == "tool" and db is not None and turn is not None:
      summary = _describe_tool_result(db, turn, action)
      if summary:
        lines.append(f"          {summary}")
    if processed_event_ids and db is not None:
      if action.type == "tool":
        labels = _world_event_labels(db, processed_event_ids)
      else:
        labels = [_describe_processed_event(db, eid) for eid in processed_event_ids]
      if labels:
        lines.append(f"          events: {', '.join(labels)}")
    elif processed_event_ids:
      lines.append(f"          events: {len(processed_event_ids)} processed")
    if health and action.type == "wait":
      lines.append(f"          health: {health}")
    return "\n".join(lines)

  if db is not None and turn is not None and action.type == "tool":
    summary = _describe_tool_result(db, turn, action)
    if summary:
      return f"RESULT:   {summary}"

  if processed_event_ids:
    return f"RESULT:   {len(processed_event_ids)} event(s) processed"
  return "RESULT:   ok"


def format_turn_block(
  turn: int,
  obs: Observation,
  action: AgentAction,
  db: SimDatabase,
  *,
  start_time: datetime,
  health: str,
  processed_event_ids: list[str] | None = None,
  minutes_advanced: int | None = None,
) -> str:
  day_label = _sim_day_label(obs.sim_time, start_time)
  header = f"[Turn {turn}, {_format_clock(obs.sim_time)}, {day_label}]"
  observe = format_observation_line(obs, db, health)
  action_line = f"ACTION:   {_format_action_target(action, db)}"
  result = format_result_line(
    action,
    db=db,
    turn=turn,
    processed_event_ids=processed_event_ids,
    health=health if action.type == "wait" else None,
    minutes_advanced=minutes_advanced,
  )
  return "\n".join([header, f"  {observe}", f"  {action_line}", f"  {result}"])


def append_turn_log(path: Path, block: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("a", encoding="utf-8") as f:
    f.write(block)
    f.write("\n\n")


class CollapsingTurnLogWriter:
  """Write turn.log with in-place collapse of consecutive identical blocks."""

  def __init__(self, path: Path, *, start_time: datetime) -> None:
    self.path = path
    self._collapser = TurnLogCollapser(start_time=start_time)
    self._last_offset: int | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
      path.touch()

  def push(
    self,
    turn: int,
    sim_time: datetime,
    block: str,
    *,
    minutes_advanced: int,
    action_label: str,
  ) -> TurnLogPushResult:
    result = self._collapser.push(
      turn,
      sim_time,
      block,
      minutes_advanced=minutes_advanced,
      action_label=action_label,
    )
    self._sync_file(result)
    return self._display_result(result)

  def flush(self) -> TurnLogPushResult:
    block = self._collapser.flush()
    if block is None:
      return TurnLogPushResult()
    if self._last_offset is not None:
      self._rewrite_last_block(block)
    else:
      self._write_new_block(block)
    return TurnLogPushResult(live_block=block, finalize=True)

  def _sync_file(self, result: TurnLogPushResult) -> None:
    if result.flushed_block is not None:
      if result.live_block is not None:
        self._write_new_block(result.live_block)
      return

    streak = self._collapser._streak
    if streak is None:
      return
    collapsed = format_collapsed_block(streak)
    if streak.count == 1:
      if self._last_offset is None:
        self._write_new_block(collapsed)
      else:
        self._rewrite_last_block(collapsed)
    else:
      self._rewrite_last_block(collapsed)

  def _display_result(self, result: TurnLogPushResult) -> TurnLogPushResult:
    streak = self._collapser._streak
    if streak is not None and streak.count > 1:
      return TurnLogPushResult(
        flushed_block=result.flushed_block,
        live_block=format_collapsed_block(streak),
        in_place=result.flushed_block is None,
      )
    return result

  def _write_new_block(self, block: str) -> None:
    with self.path.open("a", encoding="utf-8") as f:
      self._last_offset = f.tell()
      f.write(block)
      f.write("\n\n")

  def _rewrite_last_block(self, block: str) -> None:
    if self._last_offset is None:
      self._write_new_block(block)
      return
    with self.path.open("r+", encoding="utf-8") as f:
      f.seek(self._last_offset)
      f.truncate()
      f.write(block)
      f.write("\n\n")


def export_action_log_json(db: SimDatabase, run_id: str, path: Path) -> None:
  rows = db.conn.execute(
    """
    SELECT turn, sim_time, action_type, payload, result
    FROM action_log
    WHERE run_id = ?
    ORDER BY turn, id
    """,
    (run_id,),
  ).fetchall()
  entries = [
    {
      "turn": row["turn"],
      "sim_time": row["sim_time"],
      "action_type": row["action_type"],
      "payload": json.loads(row["payload"]),
      "result": json.loads(row["result"]) if row["result"] else None,
    }
    for row in rows
  ]
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def format_run_summary(
  *,
  scenario_id: str,
  agent_id: str,
  status: str,
  total_turns: int,
  wait_turns: int,
  launch_sim_datetime: str | None,
  time_to_blocker_known: str | None,
  rubric_total: float | None = None,
) -> str:
  launch = launch_sim_datetime or "null"
  blocker = time_to_blocker_known or "null"
  text = (
    f"Run complete: {scenario_id} / {agent_id} / {total_turns} turns\n"
    f"  Status: {status}\n"
    f"  Launch: {launch}\n"
    f"  Blocker found: {blocker}\n"
    f"  Turns: {total_turns} (wait: {wait_turns})"
  )
  if rubric_total is not None:
    text += f"\n  Rubric: {rubric_total:.1f}/10"
  return text
