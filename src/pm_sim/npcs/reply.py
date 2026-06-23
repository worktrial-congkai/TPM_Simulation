"""Schedule npc.reply events from resolved NPC policies."""

from __future__ import annotations

from pm_sim.npcs.actions import ACTION_ACK, plan_reply
from pm_sim.npcs.latency import schedule_reply_at
from pm_sim.npcs.resolver import pick_reactive_reply
from pm_sim.npcs.templates import load_message_templates
from pm_sim.npcs.types import NpcContext, NpcReplyPlan
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent
from pm_sim.tools.base import dm_channel


def _default_plan(db: SimDatabase) -> NpcReplyPlan:
  scenario_id = db.get_meta("scenario_id") or "first-week-pm"
  messages = load_message_templates(scenario_id)
  return NpcReplyPlan(
    template_id="default_ack",
    action=ACTION_ACK,
    body=messages.get(ACTION_ACK, "Got it, thanks."),
  )


def plan_message_reply(
  db: SimDatabase,
  *,
  coworker_id: str,
  channel: str,
  topic: str | None,
  message_kind: str,
) -> tuple[str, NpcReplyPlan]:
  ctx = NpcContext(
    coworker_id=coworker_id,
    channel=channel,
    topic=topic,
    message_kind=message_kind,  # type: ignore[arg-type]
  )
  match = pick_reactive_reply(db, ctx)
  if match is None:
    return coworker_id, _default_plan(db)
  responder_id, template = match
  return responder_id, plan_reply(db, template, ctx)


def schedule_npc_reply(
  db: SimDatabase,
  *,
  coworker_id: str,
  channel: str,
  plan: NpcReplyPlan,
  source: str,
) -> SimEvent:
  reply_at = schedule_reply_at(db, coworker_id)
  return SimEvent.create(
    event_type="npc.reply",
    start_ts=reply_at,
    source=source,
    actor_id=coworker_id,
    payload={
      "coworker_id": coworker_id,
      "channel": channel,
      "action": plan.action,
      "template_id": plan.template_id,
      "body": plan.body,
      "disclose_blocker": plan.disclose_blocker,
    },
  )


def build_message_context(
  to: str,
  channel: str,
) -> tuple[str, str, str]:
  """Return coworker_id, channel, message_kind from chat send target."""
  if to.startswith("dm:"):
    return to.split(":", 1)[1], channel, "dm"
  if to == channel and not to.startswith("dm:"):
    return "", channel, "channel"
  return to, channel, "dm"


def reply_channel_for(coworker_id: str, message_kind: str, channel: str) -> str:
  if message_kind == "channel":
    return channel
  return dm_channel(coworker_id)
