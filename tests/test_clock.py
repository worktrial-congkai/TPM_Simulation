"""Tests for simulation clock."""

from datetime import datetime
from pathlib import Path

import pytest

from pm_sim.sim.clock import advance_clock, format_sim_time, get_sim_time, set_sim_time
from pm_sim.sim.db import SimDatabase


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  database.set_meta("sim_time", "2026-06-22T09:00:00")
  return database


def test_get_and_set_sim_time(db: SimDatabase) -> None:
  dt = datetime(2026, 6, 22, 10, 30)
  set_sim_time(db, dt)
  assert get_sim_time(db) == dt


def test_advance_clock_moves_forward(db: SimDatabase) -> None:
  before = get_sim_time(db)
  after = advance_clock(db, minutes=1)
  assert after == before.replace(minute=before.minute + 1)
  assert get_sim_time(db) == after


def test_advance_clock_independent_of_wall_clock(db: SimDatabase) -> None:
  set_sim_time(db, datetime(2026, 6, 22, 9, 0))
  for _ in range(100):
    advance_clock(db, minutes=1)
  assert get_sim_time(db) == datetime(2026, 6, 22, 10, 40)
  assert format_sim_time(get_sim_time(db)) == "2026-06-22T10:40:00"
