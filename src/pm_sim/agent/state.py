"""Agent state JSON helpers."""

from __future__ import annotations

import json
from typing import Any

from pm_sim.sim.db import SimDatabase


def get_flag(db: SimDatabase, key: str, default: Any = None) -> Any:
  row = db.conn.execute(
    "SELECT value FROM agent_state WHERE key = ?",
    (key,),
  ).fetchone()
  if row is None:
    return default
  return json.loads(row["value"])


def set_flag(db: SimDatabase, key: str, value: Any) -> None:
  db.conn.execute(
    "INSERT INTO agent_state (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    (key, json.dumps(value)),
  )


def append_to_list(db: SimDatabase, key: str, item: Any) -> list[Any]:
  current = get_flag(db, key, [])
  if not isinstance(current, list):
    current = []
  if item not in current:
    current.append(item)
  set_flag(db, key, current)
  return current


def add_to_set(db: SimDatabase, key: str, item: Any) -> list[Any]:
  current = get_flag(db, key, [])
  if not isinstance(current, list):
    current = []
  if item not in current:
    current.append(item)
  set_flag(db, key, current)
  return current
