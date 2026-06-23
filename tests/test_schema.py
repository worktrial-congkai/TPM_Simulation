"""Tests for SQLite schema initialization."""

from pathlib import Path

import pytest

from pm_sim.sim.db import SimDatabase

EXPECTED_TABLES = {
  "sim_meta",
  "tasks",
  "chat_messages",
  "emails",
  "calendar_events",
  "meetings",
  "docs",
  "milestones",
  "agent_state",
  "coworker_state",
  "coworker_policies",
  "action_log",
  "runs",
  "events",
  "handler_markers",
}


@pytest.fixture
def db(tmp_path: Path) -> SimDatabase:
  database = SimDatabase(tmp_path / "test.db")
  database.init_schema()
  return database


def test_all_tables_exist(db: SimDatabase) -> None:
  rows = db.conn.execute(
    "SELECT name FROM sqlite_master WHERE type = 'table'"
  ).fetchall()
  tables = {row["name"] for row in rows}
  assert EXPECTED_TABLES.issubset(tables)


def test_events_partial_index_exists(db: SimDatabase) -> None:
  rows = db.conn.execute(
    "SELECT name FROM sqlite_master WHERE type = 'index'"
  ).fetchall()
  index_names = {row["name"] for row in rows}
  assert "idx_events_pending_due" in index_names
