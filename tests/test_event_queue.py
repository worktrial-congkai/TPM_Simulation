"""Tests for event queue ordering and drain behavior."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.clock import get_sim_time, set_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.sim.events import SimEvent, enqueue, load_event, process_due_events


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  return database


def _noop_at(db: SimDatabase, ts: datetime, marker: str) -> SimEvent:
  return SimEvent.create(
    event_type="noop",
    start_ts=ts,
    source="test",
    payload={"marker": marker},
  )


def test_drain_processes_only_due_events_in_order(db: SimDatabase) -> None:
  t0 = get_sim_time(db)
  t1 = t0.replace(minute=t0.minute + 5)

  future = SimEvent(
    id="evt-future",
    event_type="noop",
    start_ts=t1,
    source="test",
    payload={"marker": "future"},
  )
  first = SimEvent(
    id="evt-001",
    event_type="noop",
    start_ts=t0,
    source="test",
    payload={"marker": "first"},
  )
  second = SimEvent(
    id="evt-002",
    event_type="noop",
    start_ts=t0,
    source="test",
    payload={"marker": "second"},
  )

  enqueue(db, future)
  enqueue(db, second)
  enqueue(db, first)

  processed = process_due_events(db)
  assert processed == ["evt-001", "evt-002"]

  markers = db.conn.execute(
    "SELECT marker FROM handler_markers ORDER BY id"
  ).fetchall()
  assert [row["marker"] for row in markers] == ["first", "second"]

  pending = load_event(db, "evt-future")
  assert pending.status == "pending"


def test_future_followup_stays_pending_until_clock_advances(db: SimDatabase) -> None:
  t0 = get_sim_time(db)
  t_future = t0.replace(minute=t0.minute + 10)

  enqueue(db, SimEvent.create(
    event_type="noop",
    start_ts=t0,
    source="test",
    payload={"marker": "parent", "followup_at": t_future.isoformat()},
  ))
  process_due_events(db)

  pending = db.conn.execute(
    "SELECT COUNT(*) AS c FROM events WHERE status = 'pending'"
  ).fetchone()["c"]
  assert pending == 1

  set_sim_time(db, t_future)
  process_due_events(db)

  pending_after = db.conn.execute(
    "SELECT COUNT(*) AS c FROM events WHERE status = 'pending'"
  ).fetchone()["c"]
  assert pending_after == 0


def test_same_seed_same_processing_order(db: SimDatabase) -> None:
  t0 = get_sim_time(db)
  events = [
    _noop_at(db, t0, "x"),
    _noop_at(db, t0, "y"),
    _noop_at(db, t0, "z"),
  ]
  # Sort by id for deterministic enqueue order
  for ev in sorted(events, key=lambda e: e.id):
    enqueue(db, ev)

  processed = process_due_events(db)
  assert processed == sorted(processed, key=lambda eid: eid)
