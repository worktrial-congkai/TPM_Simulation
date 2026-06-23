"""Semantic policy action → agent.* event resolver."""

from __future__ import annotations

from datetime import timedelta

from pm_sim.agent.conditions import SPAM_PING_TARGETS, next_ready_critical_task
from pm_sim.agent.state import get_flag
from pm_sim.agent.types import AgentAction, Observation, WorldConfig
from pm_sim.sim.clock import format_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID, dm_channel


class ActionError(Exception):
  """Raised when an action cannot be resolved from current observation."""


def _pick_read_dm_channel(obs: Observation) -> str:
  if obs.blocker_owner:
    preferred = dm_channel(obs.blocker_owner)
    if preferred in obs.unread_channels:
      return preferred
  for channel in obs.unread_channels:
    if channel.startswith("dm:"):
      return channel
  if obs.unread_channels:
    return obs.unread_channels[0]
  raise ActionError("No unread channel for read_dm")


def _meeting_slot(obs: Observation, *, hours_ahead: int = 2, duration_minutes: int = 60) -> tuple[str, str]:
  start = obs.sim_time + timedelta(hours=hours_ahead)
  end = start + timedelta(minutes=duration_minutes)
  return format_sim_time(start), format_sim_time(end)


def _next_spam_ping_target(db: SimDatabase) -> str:
  sent_to = get_flag(db, "spam_ping_sent_to", [])
  if not isinstance(sent_to, list):
    sent_to = []
  for target in SPAM_PING_TARGETS:
    if target not in sent_to:
      return target
  raise ActionError("No spam ping targets remaining")


def resolve_action(
  name: str,
  obs: Observation,
  db: SimDatabase,
  *,
  world: WorldConfig,
) -> AgentAction:
  _ = db
  if name == "wait":
    return AgentAction(type="wait", name="wait")
  if name == "done":
    return AgentAction(type="done", name="done")

  if name == "tasks_list":
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.tasks_list",
      payload={"action": "tasks_list"},
    )

  if name == "ask_blocker_owner_dm":
    if not obs.blocker_owner:
      raise ActionError("No blocker_owner for ask_blocker_owner_dm")
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.chat_send",
      payload={
        "action": "chat_send",
        "to": obs.blocker_owner,
        "body": "What's blocking the critical path task?",
        "topic": "blocker_status",
      },
    )

  if name == "read_dm":
    channel = _pick_read_dm_channel(obs)
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.chat_read",
      payload={"action": "chat_read", "channel": channel},
    )

  if name == "read_email":
    if not obs.unread_email_ids:
      raise ActionError("No unread email for read_email")
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.email_read",
      payload={"action": "email_read", "email_id": obs.unread_email_ids[0]},
    )

  if name == "escalate_vendor":
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.email_send",
      payload={
        "action": "email_send",
        "to": world.vendor_id,
        "subject": "OAuth scope escalation",
        "body": "Please approve extended OAuth read scope for PROJ-17.",
        "topic": "vendor_escalation",
      },
    )

  if name == "schedule_requirements_meeting":
    start_at, end_at = _meeting_slot(obs)
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.calendar_schedule",
      payload={
        "action": "calendar_schedule",
        "title": "Requirements review",
        "start_at": start_at,
        "end_at": end_at,
        "attendee_ids": [AGENT_ID, "morgan", "alex"],
        "event_type": "meeting",
        "meeting_type": "requirements",
      },
    )

  if name == "schedule_tradeoff_meeting":
    start_at, end_at = _meeting_slot(obs, hours_ahead=3)
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.calendar_schedule",
      payload={
        "action": "calendar_schedule",
        "title": "Launch tradeoff discussion",
        "start_at": start_at,
        "end_at": end_at,
        "attendee_ids": [AGENT_ID, "sam", "alex", "jordan"],
        "event_type": "meeting",
        "meeting_type": "tradeoff",
      },
    )

  if name == "write_decision_doc":
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.docs_write",
      payload={
        "action": "docs_write",
        "title": "Launch tradeoff decision",
        "body": (
          "Options: (1) scope cut — drop analytics dashboard; "
          "(2) delay 2 days; (3) add eng capacity."
        ),
        "doc_type": "decision-log",
      },
    )

  if name == "send_status_update":
    recipient = "sam"
    if "sam" in obs.stakeholders_informed and world.exec_id not in obs.stakeholders_informed:
      recipient = world.exec_id
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.email_send",
      payload={
        "action": "email_send",
        "to": recipient,
        "subject": "Launch status update",
        "body": "Blocker identified; vendor escalation and meetings in progress.",
        "topic": "status_update",
      },
    )

  if name == "spam_ping_dm":
    target = _next_spam_ping_target(db)
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.chat_send",
      payload={
        "action": "chat_send",
        "to": target,
        "body": "Any updates?",
        "topic": "spam_ping",
      },
    )

  if name == "start_next_critical_task":
    task_id = next_ready_critical_task(db)
    if task_id is None:
      raise ActionError("No critical path task ready to start")
    return AgentAction(
      type="tool",
      name=name,
      event_type="agent.tasks_update",
      payload={
        "action": "tasks_update",
        "task_id": task_id,
        "status": "in_progress",
      },
    )

  raise ActionError(f"Unknown action: {name}")
