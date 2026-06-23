"""ASCII interaction timeline from action_log and processed world events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID

TIMELINE_WIDTH = 80
DETAIL_INDENT = " " * 15
DETAIL_KEY_WIDTH = 10

SIGNIFICANT_WORLD_EVENTS = frozenset({
  "npc.reply",
  "npc.policy_scan",
  "vendor.turnaround_complete",
  "meeting.start",
  "meeting.end",
  "task.complete",
  "milestone.check",
  "milestone.drift",
})


@dataclass(frozen=True)
class TimelineEntry:
  sim_time: datetime
  turn: int
  source: str
  target: str
  headline: str
  details: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def _collapse_text(text: str) -> str:
  return " ".join(str(text).split())


def _detail_lines(*pairs: tuple[str, str]) -> tuple[tuple[str, str], ...]:
  return tuple((key, _collapse_text(value)) for key, value in pairs if value)


def _policy_details(policy: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
  if not policy:
    return ()
  condition = policy.get("condition")
  action = policy.get("action")
  if condition and action:
    return (("why", f"{condition} → {action}"),)
  return ()


def _format_clock(sim_time: datetime) -> str:
  return sim_time.strftime("%a %I:%M %p").replace(" 0", " ")


def _format_time_range(start_at: str, end_at: str) -> str:
  start = parse_sim_time(start_at)
  end = parse_sim_time(end_at)
  return f"{_format_clock(start)}–{_format_clock(end)}"


def _task_owner(db: SimDatabase, task_id: str) -> str | None:
  row = db.conn.execute(
    "SELECT owner_id FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  if row is None:
    return None
  return row["owner_id"]


def _task_title(db: SimDatabase, task_id: str) -> str | None:
  row = db.conn.execute(
    "SELECT title FROM tasks WHERE id = ?",
    (task_id,),
  ).fetchone()
  if row is None:
    return None
  return row["title"]


def _meeting_row(db: SimDatabase, meeting_id: str | None) -> dict[str, Any] | None:
  if not meeting_id:
    return None
  row = db.conn.execute(
    "SELECT title, start_at, end_at, attendee_ids, meeting_type FROM meetings WHERE id = ?",
    (meeting_id,),
  ).fetchone()
  return dict(row) if row else None


def _meeting_attendees(db: SimDatabase, meeting_id: str | None) -> str:
  meeting = _meeting_row(db, meeting_id)
  if meeting is None:
    return "team"
  attendees = [
    a for a in json.loads(meeting["attendee_ids"] or "[]") if a != AGENT_ID
  ]
  return ", ".join(attendees) if attendees else "team"


def _email_sender(db: SimDatabase, email_id: str | None) -> str:
  if not email_id:
    return "inbox"
  row = db.conn.execute(
    "SELECT sender_id FROM emails WHERE id = ?",
    (email_id,),
  ).fetchone()
  return row["sender_id"] if row else "inbox"


def _load_action_log(db: SimDatabase, run_id: str) -> list[dict[str, Any]]:
  rows = db.conn.execute(
    """
    SELECT turn, sim_time, action_type, payload, result
    FROM action_log
    WHERE run_id = ?
    ORDER BY turn, id
    """,
    (run_id,),
  ).fetchall()
  entries: list[dict[str, Any]] = []
  for row in rows:
    entries.append({
      "turn": row["turn"],
      "sim_time": row["sim_time"],
      "action_type": row["action_type"],
      "payload": json.loads(row["payload"]) if row["payload"] else {},
      "result": json.loads(row["result"]) if row["result"] else None,
    })
  return entries


def _describe_world_event(db: SimDatabase, event_id: str) -> TimelineEntry | None:
  row = db.conn.execute(
    "SELECT event_type, actor_id, start_ts, payload FROM events WHERE id = ?",
    (event_id,),
  ).fetchone()
  if row is None:
    return None

  event_type = row["event_type"]
  if event_type not in SIGNIFICANT_WORLD_EVENTS:
    return None

  payload = json.loads(row["payload"]) if row["payload"] else {}
  actor_id = row["actor_id"] or "npc"
  sim_time = parse_sim_time(row["start_ts"])

  if event_type == "npc.reply":
    coworker = payload.get("coworker_id", actor_id)
    body = payload.get("body", "")
    if payload.get("disclose_blocker"):
      headline = "OAuth scope disclosed"
      details = _detail_lines(("message", body)) if body else ()
    elif body:
      headline = "reply"
      details = _detail_lines(("message", body))
    else:
      headline = "reply"
      details = ()
    return TimelineEntry(sim_time, 0, coworker, "agent", headline, details)

  if event_type == "npc.policy_scan":
    coworker = payload.get("coworker_id", "npc")
    return TimelineEntry(
      sim_time, 0, coworker, "agent", "proactive DM (policy scan)",
    )

  if event_type == "vendor.turnaround_complete":
    task_id = payload.get("task_id", "PROJ-17")
    owner = _task_owner(db, task_id) or "alex"
    return TimelineEntry(sim_time, 0, "vendor_api", owner, f"{task_id} unblocked")

  if event_type == "meeting.start":
    meeting_id = payload.get("meeting_id")
    meeting = _meeting_row(db, meeting_id)
    title = payload.get("title") or (meeting or {}).get("title") or "meeting"
    attendees = _meeting_attendees(db, meeting_id)
    details: list[tuple[str, str]] = []
    if meeting:
      details.append(("when", _format_time_range(meeting["start_at"], meeting["end_at"])))
    headline = f"meeting started: {title}"
    return TimelineEntry(sim_time, 0, "agent", attendees, headline, tuple(details))

  if event_type == "meeting.end":
    meeting_type = payload.get("meeting_type", "meeting")
    meeting_id = payload.get("meeting_id")
    attendees = _meeting_attendees(db, meeting_id)
    meeting = _meeting_row(db, meeting_id)
    details = []
    if meeting:
      details.append(("when", _format_time_range(meeting["start_at"], meeting["end_at"])))
    headline = f"{meeting_type} meeting ended"
    return TimelineEntry(sim_time, 0, attendees, "agent", headline, tuple(details))

  if event_type == "task.complete":
    task_id = payload.get("task_id", "task")
    owner = _task_owner(db, task_id) or "team"
    title = _task_title(db, task_id)
    details = _detail_lines(("task", f"{task_id} ({title})")) if title else ()
    return TimelineEntry(sim_time, 0, owner, "agent", f"{task_id} complete", details)

  if event_type == "milestone.check":
    trigger = payload.get("task_id", "task")
    launch_ts = db.get_meta("launch_sim_datetime")
    if launch_ts and row["start_ts"] == launch_ts:
      owner = _task_owner(db, trigger) or "team"
      return TimelineEntry(sim_time, 0, owner, "launch", "launch complete")
    return None

  if event_type == "milestone.drift":
    if int(db.get_meta("launch_slipped_days") or "0") <= 0:
      return None
    slip = payload.get("slip_days", 1)
    return TimelineEntry(sim_time, 0, "schedule", "launch", f"launch slipped +{slip}d")

  return None


def _agent_action_entries(
  db: SimDatabase,
  entry: dict[str, Any],
  *,
  policy: dict[str, Any] | None = None,
) -> list[TimelineEntry]:
  sim_time = parse_sim_time(entry["sim_time"])
  turn = entry["turn"]
  action_type = entry["action_type"]
  payload = entry["payload"]
  result = entry["result"] or {}
  policy_prefix = _policy_details(policy)

  if action_type in ("wait", "policy_decision"):
    return []

  if action_type == "tasks_list":
    count = (result or {}).get("count")
    headline = f"tasks_list ({count} tasks)" if count else "tasks_list"
    rows = db.conn.execute(
      "SELECT id, title FROM tasks ORDER BY id",
    ).fetchall()
    task_summary = ", ".join(f"{row['id']} ({row['title']})" for row in rows)
    details = policy_prefix + _detail_lines(("tasks", task_summary))
    return [TimelineEntry(sim_time, turn, "agent", "tasks", headline, details)]

  if action_type == "chat_send":
    target = payload.get("to", "?")
    topic = payload.get("topic", "")
    body = payload.get("body", "")
    headline = f"chat → {target}"
    details = policy_prefix + _detail_lines(
      ("topic", topic),
      ("message", body),
    )
    return [TimelineEntry(sim_time, turn, "agent", target, headline, details)]

  if action_type == "chat_read":
    channel = payload.get("channel", "")
    incoming = result.get("incoming", [])
    if incoming:
      return [
        TimelineEntry(
          sim_time,
          turn,
          msg.get("sender_id", "?"),
          "agent",
          "reply",
          policy_prefix + _detail_lines(("message", msg.get("body", ""))),
        )
        for msg in incoming
      ]
    target = channel.split(":", 1)[-1] if channel.startswith("dm:") else channel
    return [TimelineEntry(
      sim_time, turn, "agent", target or "chat", "read messages", policy_prefix,
    )]

  if action_type == "email_send":
    target = payload.get("to", "?")
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    topic = payload.get("topic", "")
    headline = f"email → {target}"
    details = policy_prefix + _detail_lines(
      ("topic", topic),
      ("subject", subject),
      ("body", body),
    )
    return [TimelineEntry(sim_time, turn, "agent", target, headline, details)]

  if action_type == "email_read":
    sender = result.get("sender_id") or _email_sender(db, payload.get("email_id"))
    subject = result.get("subject", "")
    body = result.get("body", "")
    headline = f"read email from {sender}"
    details = policy_prefix + _detail_lines(
      ("subject", subject),
      ("body", body),
    )
    return [TimelineEntry(sim_time, turn, "agent", sender, headline, details)]

  if action_type == "calendar_schedule":
    attendees = [
      a for a in payload.get("attendee_ids", []) if a != AGENT_ID
    ]
    target = ", ".join(attendees) if attendees else "team"
    title = payload.get("title", "meeting")
    meeting_type = payload.get("meeting_type", "")
    start_at = payload.get("start_at", "")
    end_at = payload.get("end_at", "")
    when = _format_time_range(start_at, end_at) if start_at and end_at else ""
    headline = f"schedule: {title}"
    details = policy_prefix + _detail_lines(
      ("when", when),
      ("attendees", target),
      ("type", meeting_type),
    )
    return [TimelineEntry(sim_time, turn, "agent", target, headline, details)]

  if action_type == "docs_write":
    title = payload.get("title") or (result or {}).get("title") or "doc"
    body = payload.get("body") or (result or {}).get("body") or ""
    headline = f"write: {title}"
    details = policy_prefix + _detail_lines(("body", body))
    return [TimelineEntry(sim_time, turn, "agent", "decision-log", headline, details)]

  if action_type == "tasks_update":
    task_id = payload.get("task_id", "task")
    status = payload.get("status", "update")
    owner = _task_owner(db, task_id) or "team"
    title = _task_title(db, task_id)
    headline = f"{task_id} → {status}"
    details = policy_prefix
    if title:
      details = details + _detail_lines(("task", f"{task_id} ({title})"))
    return [TimelineEntry(sim_time, turn, "agent", owner, headline, details)]

  return []


def collect_timeline_entries(db: SimDatabase, run_id: str) -> list[TimelineEntry]:
  policy_by_turn: dict[int, dict[str, Any]] = {}
  for row in _load_action_log(db, run_id):
    if row["action_type"] == "policy_decision":
      policy_by_turn[row["turn"]] = row["payload"]

  entries: list[TimelineEntry] = []
  for row in _load_action_log(db, run_id):
    policy = policy_by_turn.get(row["turn"])
    entries.extend(_agent_action_entries(db, row, policy=policy))
    if row["action_type"] == "wait":
      processed = (row["result"] or {}).get("processed", [])
      turn = row["turn"]
      for event_id in processed:
        world_entry = _describe_world_event(db, event_id)
        if world_entry is not None:
          entries.append(TimelineEntry(
            world_entry.sim_time,
            turn,
            world_entry.source,
            world_entry.target,
            world_entry.headline,
            world_entry.details,
          ))

  entries.sort(key=lambda e: (e.sim_time, e.turn))
  return _dedupe_entries(entries)


def _dedupe_entries(entries: list[TimelineEntry]) -> list[TimelineEntry]:
  seen: set[tuple[str, str, str, str, tuple[tuple[str, str], ...]]] = set()
  unique: list[TimelineEntry] = []
  for entry in entries:
    key = (
      entry.sim_time.isoformat(),
      entry.source,
      entry.target,
      entry.headline,
      entry.details,
    )
    if key in seen:
      continue
    seen.add(key)
    unique.append(entry)
  return unique


def _arrow(source: str, target: str) -> str:
  if source == "agent":
    return f"agent ──► {target:<16}"
  if target == "agent":
    return f"{source:<16} ──► agent"
  return f"{source:<16} ──► {target:<16}"


def _format_row(entry: TimelineEntry) -> list[str]:
  clock = _format_clock(entry.sim_time)
  arrow = _arrow(entry.source, entry.target)
  lines = [f"  {clock:<12} {arrow}  {entry.headline}"]
  for key, value in entry.details:
    lines.append(f"{DETAIL_INDENT}{key:<{DETAIL_KEY_WIDTH}} {value}")
  return lines


def format_interaction_timeline(
  entries: list[TimelineEntry],
  *,
  start_time: datetime,
) -> str:
  _ = start_time
  if not entries:
    return "Interaction timeline\n  (no interactions recorded)"

  lines = [
    "Interaction timeline (agent ↔ coworkers)",
    "═" * TIMELINE_WIDTH,
  ]

  for entry in entries:
    lines.extend(_format_row(entry))

  lines.append("═" * TIMELINE_WIDTH)
  return "\n".join(lines)


def build_interaction_timeline(db: SimDatabase, run_id: str) -> str:
  start_raw = db.get_meta("start_time")
  if start_raw is None:
    raise RuntimeError("start_time not set in sim_meta")
  start_time = parse_sim_time(start_raw)
  entries = collect_timeline_entries(db, run_id)
  return format_interaction_timeline(entries, start_time=start_time)


def write_interaction_timeline(db: SimDatabase, run_id: str, path: Path) -> str:
  text = build_interaction_timeline(db, run_id)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text + "\n", encoding="utf-8")
  return text
