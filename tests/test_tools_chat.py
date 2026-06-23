"""Tests for chat tool."""

import json
from pathlib import Path

import pytest

from pm_sim.sim.reset import reset_scenario
from pm_sim.tools.chat import ChatTool


@pytest.fixture
def db(tmp_path: Path):
  database = reset_scenario("first-week-pm", db_path=tmp_path / "sim.db")
  yield database
  database.close()


def test_read_marks_channel_read(db) -> None:
  messages = ChatTool.read(db, "eng-launch")
  assert len(messages) == 2
  unread = ChatTool.list_unread(db)
  unread_channels = {msg["channel"] for msg in unread}
  assert "eng-launch" not in unread_channels
  assert unread_channels == {"dm:alex", "dm:sam"}


def test_send_inserts_dm_row(db) -> None:
  result = ChatTool.send(db, "alex", "What's blocking PROJ-17?")
  assert result["channel"] == "dm:alex"
  row = db.conn.execute(
    "SELECT body FROM chat_messages WHERE id = ?",
    (result["id"],),
  ).fetchone()
  assert row["body"] == "What's blocking PROJ-17?"
