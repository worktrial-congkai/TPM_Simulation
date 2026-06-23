"""Event queue: SQLite-backed due-event processing."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase


@dataclass
class SimEvent:
  id: str
  event_type: str
  start_ts: datetime
  source: str
  actor_id: str | None = None
  payload: dict[str, Any] = field(default_factory=dict)
  status: str = "pending"
  visibility: str = "public"

  @staticmethod
  def create(
    event_type: str,
    start_ts: datetime,
    source: str,
    *,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
    visibility: str = "public",
  ) -> SimEvent:
    return SimEvent(
      id=str(uuid.uuid4()),
      event_type=event_type,
      start_ts=start_ts,
      source=source,
      actor_id=actor_id,
      payload=payload or {},
      visibility=visibility,
    )


def _row_to_event(row: Any) -> SimEvent:
  return SimEvent(
    id=row["id"],
    event_type=row["event_type"],
    start_ts=parse_sim_time(row["start_ts"]),
    source=row["source"],
    actor_id=row["actor_id"],
    payload=json.loads(row["payload"]),
    status=row["status"],
    visibility=row["visibility"],
  )


def insert_event(db: SimDatabase, event: SimEvent) -> None:
  db.conn.execute(
    """
    INSERT INTO events (id, event_type, start_ts, source, actor_id, payload, status, visibility)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      event.id,
      event.event_type,
      format_sim_time(event.start_ts),
      event.source,
      event.actor_id,
      json.dumps(event.payload),
      event.status,
      event.visibility,
    ),
  )
  db.conn.commit()


def enqueue(db: SimDatabase, event: SimEvent) -> SimEvent:
  insert_event(db, event)
  return event


def load_event(db: SimDatabase, event_id: str) -> SimEvent:
  row = db.conn.execute(
    "SELECT * FROM events WHERE id = ?", (event_id,)
  ).fetchone()
  if row is None:
    raise KeyError(f"Event not found: {event_id}")
  return _row_to_event(row)


def fetch_due_events(db: SimDatabase, up_to: datetime) -> list[SimEvent]:
  rows = db.conn.execute(
    """
    SELECT * FROM events
    WHERE status = 'pending' AND start_ts <= ?
    ORDER BY start_ts, id
    """,
    (format_sim_time(up_to),),
  ).fetchall()
  return [_row_to_event(row) for row in rows]


def process_due_events(db: SimDatabase) -> list[str]:
  """Process all pending events due at current sim time. Returns processed event ids."""
  from pm_sim.sim.handlers import dispatch_handler  # avoid circular import

  sim_time = get_sim_time(db)
  processed: list[str] = []

  while True:
    events = fetch_due_events(db, sim_time)
    if not events:
      break
    for event in events:
      followups = dispatch_handler(event.id, db)
      processed.append(event.id)
      for new_ev in followups:
        insert_event(db, new_ev)

  return processed
