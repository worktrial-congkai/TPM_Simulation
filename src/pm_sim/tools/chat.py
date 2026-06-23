"""Chat tool — channels, DMs, read/unread."""

from __future__ import annotations

import uuid
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID, ToolError, dm_channel, require_coworker


class ChatTool:
  @staticmethod
  def list_channels(db: SimDatabase) -> list[str]:
    rows = db.conn.execute(
      "SELECT DISTINCT channel FROM chat_messages ORDER BY channel"
    ).fetchall()
    return [row["channel"] for row in rows]

  @staticmethod
  def list_unread(db: SimDatabase) -> list[dict[str, Any]]:
    rows = db.conn.execute(
      """
      SELECT id, channel, sender_id, body, sent_at
      FROM chat_messages
      WHERE read_by_agent = 0
      ORDER BY sent_at, id
      """
    ).fetchall()
    return [dict(row) for row in rows]

  @staticmethod
  def read(db: SimDatabase, channel: str) -> list[dict[str, Any]]:
    rows = db.conn.execute(
      """
      SELECT id, channel, sender_id, body, sent_at, read_by_agent
      FROM chat_messages
      WHERE channel = ?
      ORDER BY sent_at, id
      """,
      (channel,),
    ).fetchall()
    db.conn.execute(
      "UPDATE chat_messages SET read_by_agent = 1 WHERE channel = ?",
      (channel,),
    )
    return [dict(row) for row in rows]

  @staticmethod
  def send(
    db: SimDatabase,
    to: str,
    body: str,
    *,
    topic: str | None = None,
  ) -> dict[str, Any]:
    if not body.strip():
      raise ToolError("Message body cannot be empty")

    if to.startswith("dm:") or to in ChatTool.list_channels(db):
      channel = to
    else:
      require_coworker(db, to)
      channel = dm_channel(to)

    sim_time = get_sim_time(db)
    msg_id = str(uuid.uuid4())
    db.conn.execute(
      """
      INSERT INTO chat_messages (id, channel, sender_id, body, sent_at)
      VALUES (?, ?, ?, ?, ?)
      """,
      (msg_id, channel, AGENT_ID, body, format_sim_time(sim_time)),
    )
    return {
      "id": msg_id,
      "channel": channel,
      "sender_id": AGENT_ID,
      "body": body,
      "sent_at": format_sim_time(sim_time),
      "topic": topic,
    }
