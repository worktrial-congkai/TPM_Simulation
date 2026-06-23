"""Doc tool — read and write documents."""

from __future__ import annotations

import uuid
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID, ToolError


class DocTool:
  @staticmethod
  def list_docs(db: SimDatabase) -> list[dict[str, Any]]:
    rows = db.conn.execute(
      "SELECT id, title, author_id, created_at, doc_type FROM docs ORDER BY created_at, id"
    ).fetchall()
    return [dict(row) for row in rows]

  @staticmethod
  def read(db: SimDatabase, doc_id: str) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM docs WHERE id = ?",
      (doc_id,),
    ).fetchone()
    if row is None:
      raise ToolError(f"Document not found: {doc_id}")
    return dict(row)

  @staticmethod
  def write(
    db: SimDatabase,
    title: str,
    body: str,
    *,
    doc_type: str | None = None,
  ) -> dict[str, Any]:
    if not title.strip():
      raise ToolError("Title cannot be empty")

    sim_time = get_sim_time(db)
    doc_id = str(uuid.uuid4())
    db.conn.execute(
      """
      INSERT INTO docs (id, title, body, author_id, created_at, doc_type)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        doc_id,
        title,
        body,
        AGENT_ID,
        format_sim_time(sim_time),
        doc_type,
      ),
    )
    return {
      "id": doc_id,
      "title": title,
      "body": body,
      "author_id": AGENT_ID,
      "created_at": format_sim_time(sim_time),
      "doc_type": doc_type,
    }
