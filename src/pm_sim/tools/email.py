"""Email tool — formal comms."""

from __future__ import annotations

import uuid
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID, ToolError, require_coworker


class EmailTool:
  @staticmethod
  def list_unread(db: SimDatabase) -> list[dict[str, Any]]:
    rows = db.conn.execute(
      """
      SELECT id, sender_id, recipient_id, subject, body, sent_at
      FROM emails
      WHERE recipient_id = ? AND read_by_agent = 0
      ORDER BY sent_at, id
      """,
      (AGENT_ID,),
    ).fetchall()
    return [dict(row) for row in rows]

  @staticmethod
  def read(db: SimDatabase, email_id: str) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM emails WHERE id = ? AND recipient_id = ?",
      (email_id, AGENT_ID),
    ).fetchone()
    if row is None:
      raise ToolError(f"Email not found: {email_id}")
    db.conn.execute(
      "UPDATE emails SET read_by_agent = 1 WHERE id = ?",
      (email_id,),
    )
    return dict(row)

  @staticmethod
  def send(
    db: SimDatabase,
    to: str,
    subject: str,
    body: str,
    *,
    topic: str | None = None,
  ) -> dict[str, Any]:
    if not subject.strip():
      raise ToolError("Subject cannot be empty")
    if not body.strip():
      raise ToolError("Body cannot be empty")

    require_coworker(db, to)
    sim_time = get_sim_time(db)
    email_id = str(uuid.uuid4())
    db.conn.execute(
      """
      INSERT INTO emails (id, sender_id, recipient_id, subject, body, sent_at)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        email_id,
        AGENT_ID,
        to,
        subject,
        body,
        format_sim_time(sim_time),
      ),
    )
    return {
      "id": email_id,
      "sender_id": AGENT_ID,
      "recipient_id": to,
      "subject": subject,
      "body": body,
      "sent_at": format_sim_time(sim_time),
      "topic": topic,
    }
