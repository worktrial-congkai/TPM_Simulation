"""Calendar tool — schedule and list events."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import AGENT_ID, ToolError, require_coworker


class CalendarTool:
  @staticmethod
  def list_upcoming(db: SimDatabase) -> list[dict[str, Any]]:
    sim_time = format_sim_time(get_sim_time(db))
    rows = db.conn.execute(
      """
      SELECT id, title, start_at, end_at, organizer_id, attendee_ids, event_type
      FROM calendar_events
      WHERE start_at >= ?
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
  def _has_overlap(
    db: SimDatabase,
    start_at: datetime,
    end_at: datetime,
    *,
    exclude_id: str | None = None,
  ) -> bool:
    start_s = format_sim_time(start_at)
    end_s = format_sim_time(end_at)
    query = """
      SELECT 1 FROM calendar_events
      WHERE start_at < ? AND end_at > ?
    """
    params: list[str] = [end_s, start_s]
    if exclude_id:
      query += " AND id != ?"
      params.append(exclude_id)
    row = db.conn.execute(query, params).fetchone()
    return row is not None

  @staticmethod
  def schedule(
    db: SimDatabase,
    title: str,
    start_at: datetime,
    end_at: datetime,
    attendee_ids: list[str],
    *,
    event_type: str | None = None,
    meeting_type: str | None = None,
  ) -> dict[str, Any]:
    if not title.strip():
      raise ToolError("Title cannot be empty")
    if end_at <= start_at:
      raise ToolError("end_at must be after start_at")

    sim_time = get_sim_time(db)
    if start_at < sim_time:
      raise ToolError("Cannot schedule events in the past")

    for attendee_id in attendee_ids:
      if attendee_id != AGENT_ID:
        require_coworker(db, attendee_id)

    if CalendarTool._has_overlap(db, start_at, end_at):
      raise ToolError("Calendar conflict with existing event")

    cal_id = str(uuid.uuid4())
    db.conn.execute(
      """
      INSERT INTO calendar_events (
        id, title, start_at, end_at, organizer_id, attendee_ids, event_type
      )
      VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      (
        cal_id,
        title,
        format_sim_time(start_at),
        format_sim_time(end_at),
        AGENT_ID,
        json.dumps(attendee_ids),
        event_type,
      ),
    )

    meeting_id: str | None = None
    if event_type == "meeting":
      meeting_id = str(uuid.uuid4())
      db.conn.execute(
        """
        INSERT INTO meetings (
          id, title, start_at, end_at, attendee_ids, meeting_type, transcript, completed
        )
        VALUES (?, ?, ?, ?, ?, ?, NULL, 0)
        """,
        (
          meeting_id,
          title,
          format_sim_time(start_at),
          format_sim_time(end_at),
          json.dumps(attendee_ids),
          meeting_type or event_type,
        ),
      )

    return {
      "id": cal_id,
      "title": title,
      "start_at": format_sim_time(start_at),
      "end_at": format_sim_time(end_at),
      "organizer_id": AGENT_ID,
      "attendee_ids": attendee_ids,
      "event_type": event_type,
      "meeting_type": meeting_type,
      "meeting_id": meeting_id,
    }
