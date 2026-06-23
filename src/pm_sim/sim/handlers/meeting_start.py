"""meeting.start — kick off meeting and schedule completion."""

from __future__ import annotations

from pm_sim.sim.clock import parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent


def handle_meeting_start(event: SimEvent, db: SimDatabase) -> list[SimEvent]:
  meeting_id = event.payload.get("meeting_id")
  if not meeting_id:
    return []

  row = db.conn.execute(
    "SELECT * FROM meetings WHERE id = ?",
    (meeting_id,),
  ).fetchone()
  if row is None or row["completed"]:
    return []

  end_at = parse_sim_time(row["end_at"])
  return [
    SimEvent.create(
      event_type="meeting.end",
      start_ts=end_at,
      source=f"meeting.start:{meeting_id}",
      payload={
        "meeting_id": meeting_id,
        "meeting_type": event.payload.get("meeting_type") or row["meeting_type"],
      },
    ),
  ]
