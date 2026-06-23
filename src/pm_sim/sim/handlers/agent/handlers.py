"""Agent event handlers — thin wrappers around tools."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pm_sim.agent.action_log import log_action
from pm_sim.agent.state import add_to_set, append_to_list, set_flag
from pm_sim.npcs.reply import (
  build_message_context,
  plan_message_reply,
  reply_channel_for,
  schedule_npc_reply,
)
from pm_sim.sim.clock import get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.sim.task_timers import schedule_task_complete
from pm_sim.tools.base import AGENT_ID, dm_channel
from pm_sim.tools.calendar import CalendarTool
from pm_sim.tools.chat import ChatTool
from pm_sim.tools.doc import DocTool
from pm_sim.tools.email import EmailTool
from pm_sim.tools.meeting import MeetingTool
from pm_sim.tools.task import TaskTool

OAUTH_MARKER = "OAuth"


def _payload(event: SimEvent) -> dict[str, Any]:
  return event.payload or {}


def handle_agent_tasks_list(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  tasks = TaskTool.list_tasks(db)
  set_flag(db, "tasks_checked", True)
  blocked_ids = [t["id"] for t in tasks if t["status"] == "blocked"]
  set_flag(db, "blockers_unknown", blocked_ids)
  log_action(db, "tasks_list", _payload(event), {"count": len(tasks)})
  return []


def handle_agent_tasks_update(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  task_id = p["task_id"]
  fields = {k: v for k, v in p.items() if k not in ("action", "task_id")}
  result = TaskTool.update_task(db, task_id, **fields)
  log_action(db, "tasks_update", p, result)

  followups: list[SimEvent] = []
  if result.get("status") == "in_progress":
    completion = schedule_task_complete(
      db,
      task_id,
      source=f"agent.tasks_update:{task_id}",
    )
    if completion:
      followups.append(completion)
  return followups


def handle_agent_chat_read(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  channel = p["channel"]
  messages = ChatTool.read(db, channel)
  incoming = [
    {"sender_id": msg["sender_id"], "body": msg["body"]}
    for msg in messages
    if msg["sender_id"] != AGENT_ID and not msg.get("read_by_agent")
  ]
  append_to_list(db, "channels_read", channel)
  for msg in messages:
    if OAUTH_MARKER in msg.get("body", ""):
      add_to_set(db, "blockers_known", "PROJ-17_oauth_scope")
  log_action(db, "chat_read", p, {"count": len(messages), "incoming": incoming})
  return []


def handle_agent_chat_send(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = ChatTool.send(db, p["to"], p["body"], topic=p.get("topic"))
  log_action(db, "chat_send", p, result)

  to = p["to"]
  coworker_id, _channel, message_kind = build_message_context(to, result["channel"])
  if p.get("topic") == "spam_ping":
    raw_id = to if not to.startswith("dm:") else to.split(":", 1)[1]
    append_to_list(db, "spam_ping_sent_to", raw_id)

  responder_id, plan = plan_message_reply(
    db,
    coworker_id=coworker_id,
    channel=result["channel"],
    topic=p.get("topic"),
    message_kind=message_kind,
  )
  reply_channel = reply_channel_for(responder_id, message_kind, result["channel"])
  return [
    schedule_npc_reply(
      db,
      coworker_id=responder_id,
      channel=reply_channel,
      plan=plan,
      source=f"agent.chat_send:{result['id']}",
    ),
  ]


def handle_agent_email_read(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = EmailTool.read(db, p["email_id"])
  log_action(db, "email_read", p, result)
  return []


def handle_agent_email_send(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = EmailTool.send(
    db,
    p["to"],
    p["subject"],
    p["body"],
    topic=p.get("topic"),
  )
  log_action(db, "email_send", p, result)

  topic = p.get("topic")
  if topic == "status_update":
    append_to_list(db, "stakeholders_informed", p["to"])

  followups: list[SimEvent] = []
  if topic == "vendor_escalation":
    set_flag(db, "vendor_escalated", True)
    sim_time = get_sim_time(db)
    followups.append(
      SimEvent.create(
        event_type="vendor.turnaround_complete",
        start_ts=sim_time + timedelta(hours=24),
        source=f"agent.email_send:{result['id']}",
        payload={"task_id": "PROJ-17"},
      )
    )
  else:
    responder_id, plan = plan_message_reply(
      db,
      coworker_id=p["to"],
      channel=dm_channel(p["to"]),
      topic=topic,
      message_kind="email",
    )
    followups.append(
      schedule_npc_reply(
        db,
        coworker_id=responder_id,
        channel=dm_channel(responder_id),
        plan=plan,
        source=f"agent.email_send:{result['id']}",
      )
    )
  return followups


def handle_agent_calendar_list(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  events = CalendarTool.list_upcoming(db)
  log_action(db, "calendar_list", p, {"count": len(events)})
  return []


def handle_agent_calendar_schedule(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  start_at = parse_sim_time(p["start_at"])
  end_at = parse_sim_time(p["end_at"])
  result = CalendarTool.schedule(
    db,
    p["title"],
    start_at,
    end_at,
    p.get("attendee_ids") or [],
    event_type=p.get("event_type"),
    meeting_type=p.get("meeting_type"),
  )
  log_action(db, "calendar_schedule", p, result)

  followups: list[SimEvent] = []
  meeting_type = p.get("meeting_type")
  if meeting_type == "requirements":
    set_flag(db, "requirements_meeting_scheduled", True)
  elif meeting_type == "tradeoff":
    set_flag(db, "tradeoff_meeting_scheduled", True)
  if p.get("event_type") == "meeting" and result.get("meeting_id"):
    followups.append(
      SimEvent.create(
        event_type="meeting.start",
        start_ts=start_at,
        source=f"agent.calendar_schedule:{result['id']}",
        payload={
          "meeting_id": result["meeting_id"],
          "meeting_type": p.get("meeting_type"),
        },
      )
    )
  return followups


def handle_agent_meeting_join(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = MeetingTool.join(db, p["meeting_id"])
  append_to_list(db, "meetings_joined", p["meeting_id"])
  log_action(db, "meeting_join", p, result)
  return []


def handle_agent_meeting_transcript(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = MeetingTool.get_transcript(db, p["meeting_id"])
  if result.get("meeting_type") == "requirements":
    set_flag(db, "requirements_meeting_held", True)
  log_action(db, "meeting_transcript", p, result)
  return []


def handle_agent_docs_read(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = DocTool.read(db, p["doc_id"])
  log_action(db, "docs_read", p, result)
  return []


def handle_agent_docs_write(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  p = _payload(event)
  result = DocTool.write(
    db,
    p["title"],
    p.get("body", ""),
    doc_type=p.get("doc_type"),
  )
  if p.get("doc_type") == "decision-log":
    set_flag(db, "tradeoff_documented", True)
    set_flag(db, "tradeoff_decision", {"doc_id": result["id"], "title": result["title"]})
  log_action(db, "docs_write", p, result)
  return []


AGENT_HANDLERS: dict[str, Any] = {
  "agent.tasks_list": handle_agent_tasks_list,
  "agent.tasks_update": handle_agent_tasks_update,
  "agent.chat_read": handle_agent_chat_read,
  "agent.chat_send": handle_agent_chat_send,
  "agent.email_read": handle_agent_email_read,
  "agent.email_send": handle_agent_email_send,
  "agent.calendar_list": handle_agent_calendar_list,
  "agent.calendar_schedule": handle_agent_calendar_schedule,
  "agent.meeting_join": handle_agent_meeting_join,
  "agent.meeting_transcript": handle_agent_meeting_transcript,
  "agent.docs_read": handle_agent_docs_read,
  "agent.docs_write": handle_agent_docs_write,
}
