"""Task tool — list and update tickets."""

from __future__ import annotations

import json
from typing import Any

from pm_sim.sim.db import SimDatabase
from pm_sim.tools.base import ToolError

ALLOWED_STATUSES = {"todo", "in_progress", "blocked", "done"}

VALID_TRANSITIONS: dict[str, set[str]] = {
  "todo": {"in_progress"},
  "in_progress": {"done"},
  "blocked": set(),
  "done": set(),
}


class TaskTool:
  @staticmethod
  def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["depends_on"] = json.loads(row["depends_on"] or "[]")
    data["critical_path"] = bool(row["critical_path"])
    return data

  @staticmethod
  def list_tasks(db: SimDatabase) -> list[dict[str, Any]]:
    rows = db.conn.execute(
      "SELECT * FROM tasks ORDER BY id"
    ).fetchall()
    return [TaskTool._row_to_dict(row) for row in rows]

  @staticmethod
  def get_task(db: SimDatabase, task_id: str) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM tasks WHERE id = ?",
      (task_id,),
    ).fetchone()
    if row is None:
      raise ToolError(f"Task not found: {task_id}")
    return TaskTool._row_to_dict(row)

  @staticmethod
  def update_task(db: SimDatabase, task_id: str, **fields: Any) -> dict[str, Any]:
    row = db.conn.execute(
      "SELECT * FROM tasks WHERE id = ?",
      (task_id,),
    ).fetchone()
    if row is None:
      raise ToolError(f"Task not found: {task_id}")

    current = TaskTool._row_to_dict(row)
    updates: dict[str, Any] = {}

    if "status" in fields:
      new_status = fields["status"]
      if new_status not in ALLOWED_STATUSES:
        raise ToolError(f"Invalid status: {new_status}")
      if new_status != current["status"]:
        allowed = VALID_TRANSITIONS.get(current["status"], set())
        if new_status not in allowed:
          raise ToolError(
            f"Cannot transition {task_id} from {current['status']} to {new_status}"
          )
      updates["status"] = new_status

    if "priority" in fields:
      updates["priority"] = fields["priority"]

    if not updates:
      return current

    if "status" in updates:
      db.conn.execute(
        "UPDATE tasks SET status = ? WHERE id = ?",
        (updates["status"], task_id),
      )

    return TaskTool.get_task(db, task_id)
