"""Action log helper — no-op until run loop binds active_run_id."""

from __future__ import annotations

import json
from typing import Any

from pm_sim.sim.clock import format_sim_time, get_sim_time
from pm_sim.sim.db import SimDatabase


def log_action(
  db: SimDatabase,
  action_type: str,
  payload: dict[str, Any],
  result: Any = None,
) -> None:
  run_id = db.get_meta("active_run_id")
  if not run_id:
    return

  turn = int(db.get_meta("current_turn") or "0")
  sim_time = format_sim_time(get_sim_time(db))
  db.conn.execute(
    """
    INSERT INTO action_log (run_id, turn, sim_time, action_type, payload, result)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
      run_id,
      turn,
      sim_time,
      action_type,
      json.dumps(payload),
      json.dumps(result) if result is not None else None,
    ),
  )
