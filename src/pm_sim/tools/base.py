"""Shared tool helpers and errors."""

from __future__ import annotations

from pm_sim.sim.db import SimDatabase

AGENT_ID = "agent"


class ToolError(Exception):
  """Raised when a tool action is invalid."""


def require_coworker(db: SimDatabase, coworker_id: str) -> None:
  row = db.conn.execute(
    "SELECT 1 FROM coworker_state WHERE coworker_id = ?",
    (coworker_id,),
  ).fetchone()
  if row is None:
    raise ToolError(f"Unknown coworker: {coworker_id}")


def dm_channel(coworker_id: str) -> str:
  return f"dm:{coworker_id}"
