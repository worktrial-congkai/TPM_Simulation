"""Tests for email tool."""

from pathlib import Path

import pytest

from pm_sim.sim.reset import reset_scenario
from pm_sim.tools.email import EmailTool


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_send_inserts_email_and_read_seeded(db) -> None:
  sent = EmailTool.send(db, "sam", "Status update", "Working through blockers.")
  row = db.conn.execute(
    "SELECT recipient_id FROM emails WHERE id = ?",
    (sent["id"],),
  ).fetchone()
  assert row["recipient_id"] == "sam"

  read = EmailTool.read(db, "email-001")
  assert read["subject"] == "Scope question on launch feature"
  unread = EmailTool.list_unread(db)
  assert all(e["id"] != "email-001" for e in unread)
