"""No-op test handler for unit tests."""

from __future__ import annotations

from datetime import datetime

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def handle_noop(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  sim_time = get_sim_time(db)
  marker = event.payload.get("marker", "processed")
  db.conn.execute(
    "INSERT INTO handler_markers (event_id, marker, created_at) VALUES (?, ?, ?)",
    (event.id, marker, format_sim_time(sim_time)),
  )
  followups: list[SimEvent] = []
  followup_at = event.payload.get("followup_at")
  if followup_at:
    followups.append(
      SimEvent.create(
        event_type="noop",
        start_ts=datetime.fromisoformat(followup_at),
        source=f"noop:followup:{event.id}",
        payload={"marker": "followup"},
      )
    )
  return followups
