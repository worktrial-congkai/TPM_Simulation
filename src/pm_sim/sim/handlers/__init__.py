"""Event handler registry and transactional dispatch."""

from __future__ import annotations

from typing import Callable

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent, load_event
from pm_sim.sim.handlers.agent import AGENT_HANDLERS
from pm_sim.sim.handlers.meeting_end import handle_meeting_end
from pm_sim.sim.handlers.meeting_start import handle_meeting_start
from pm_sim.sim.handlers.milestone_check import handle_milestone_check
from pm_sim.sim.handlers.milestone_drift import handle_milestone_drift
from pm_sim.sim.handlers.noop import handle_noop
from pm_sim.sim.handlers.npc_policy_scan import handle_npc_policy_scan
from pm_sim.sim.handlers.npc_reply import handle_npc_reply
from pm_sim.sim.handlers.task_complete import handle_task_complete
from pm_sim.sim.handlers.vendor_turnaround import handle_vendor_turnaround

HandlerFn = Callable[[SimEvent, SimDatabase], list[SimEvent]]

HANDLERS: dict[str, HandlerFn] = {
  "noop": handle_noop,
  "milestone.check": handle_milestone_check,
  "milestone.drift": handle_milestone_drift,
  "vendor.turnaround_complete": handle_vendor_turnaround,
  "npc.reply": handle_npc_reply,
  "npc.policy_scan": handle_npc_policy_scan,
  "task.complete": handle_task_complete,
  "meeting.start": handle_meeting_start,
  "meeting.end": handle_meeting_end,
  **AGENT_HANDLERS,
}


def dispatch_handler(event_id: str, db: SimDatabase) -> list[SimEvent]:
  with db.transaction():
    event = load_event(db, event_id)
    handler = HANDLERS.get(event.event_type)
    if handler is None:
      raise ValueError(f"No handler registered for event type: {event.event_type}")
    followups = handler(event, db)
    db.conn.execute(
      "UPDATE events SET status = 'processed' WHERE id = ?",
      (event_id,),
    )
  return followups
