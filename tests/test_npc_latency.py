"""Tests for seeded NPC reply latency."""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_sim.npcs.latency import schedule_reply_at
from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.reset import reset_scenario


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_same_seed_same_latency(db) -> None:
  first = schedule_reply_at(db, "alex")
  db.conn.execute(
    """
    INSERT INTO events (id, event_type, start_ts, source, payload, status, visibility)
    VALUES ('evt-1', 'npc.reply', ?, 'test', '{}', 'processed', 'public')
    """,
    (format_sim_time(get_sim_time(db)),),
  )
  db.conn.commit()
  second = schedule_reply_at(db, "alex")
  assert first == second


def test_different_coworkers_different_latency_bounds(db) -> None:
  alex_at = schedule_reply_at(db, "alex")
  jordan_at = schedule_reply_at(db, "jordan")
  now = get_sim_time(db)
  alex_minutes = (alex_at - now).total_seconds() / 60
  jordan_minutes = (jordan_at - now).total_seconds() / 60
  assert 15 <= alex_minutes <= 120
  assert 5 <= jordan_minutes <= 30
