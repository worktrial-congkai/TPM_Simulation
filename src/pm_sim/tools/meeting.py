"""Meeting tool — join and transcripts."""

from __future__ import annotations

import json
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import ToolError


class MeetingTool:
  @staticmethod
  def list_upcoming(db: SimDatabase) -> list[dict[str, Any]]:
    sim_time = format_sim_time(get_sim_time(db))
    rows = db.conn.execute(
      """
      SELECT id, title, start_at, end_at, attendee_ids, meeting_type, completed
      FROM meetings
      WHERE start_at >= ? AND completed = 0
      ORDER BY start_at, id
      """,
      (sim_time,),
    ).fetchall()
    result = []
    for row in rows:
      item = dict(row)
      item["attendee_ids"] = json.loads(row["attendee_ids"] or "[]")
      result.append(item)
    return result

  @staticmethod
  def join(db: SimDatabase, meeting_id: str) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM meetings WHERE id = ?",
      (meeting_id,),
    ).fetchone()
    if row is None:
      raise ToolError(f"Meeting not found: {meeting_id}")

    sim_time = get_sim_time(db)
    start_at = parse_sim_time(row["start_at"])
    if sim_time < start_at:
      raise ToolError("Meeting has not started yet")

    return {
      "meeting_id": meeting_id,
      "title": row["title"],
      "joined_at": format_sim_time(sim_time),
    }

  @staticmethod
  def get_transcript(db: SimDatabase, meeting_id: str) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM meetings WHERE id = ?",
      (meeting_id,),
    ).fetchone()
    if row is None:
      raise ToolError(f"Meeting not found: {meeting_id}")

    sim_time = get_sim_time(db)
    end_at = parse_sim_time(row["end_at"])
    if sim_time < end_at:
      raise ToolError("Meeting has not ended yet")
    if not row["completed"]:
      raise ToolError("Meeting transcript not available yet")

    return {
      "meeting_id": meeting_id,
      "title": row["title"],
      "meeting_type": row["meeting_type"],
      "transcript": row["transcript"] or "",
    }
