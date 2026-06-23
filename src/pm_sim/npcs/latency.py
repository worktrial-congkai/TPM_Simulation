"""Seeded NPC reply latency scheduling."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from pm_sim.npcs.templates import load_coworkers
from pm_sim.sim.clock import get_sim_time
from pm_sim.sim.db import SimDatabase


def _reply_count(db: SimDatabase, coworker_id: str) -> int:
  row = db.conn.execute(
    """
    SELECT COUNT(*) AS c FROM events
    WHERE event_type = 'npc.reply' AND actor_id = ?
    """,
    (coworker_id,),
  ).fetchone()
  return int(row["c"])


def schedule_reply_at(db: SimDatabase, coworker_id: str) -> datetime:
  """Return when an NPC reply should fire using seeded per-coworker latency."""
  scenario_id = db.get_meta("scenario_id") or "first-week-pm"
  coworkers = load_coworkers(scenario_id)
  coworker = coworkers.get(coworker_id, {})
  latency = coworker.get("response_latency") or {}

  fixed = latency.get("fixed_minutes")
  if fixed is not None:
    minutes = int(fixed)
  else:
    seed = int(db.get_meta("seed") or "0")
    seed_key = latency.get("seed_key", f"{coworker_id}-latency")
    count = _reply_count(db, coworker_id)
    rng = random.Random(f"{seed}:{seed_key}:{count}")
    min_minutes = int(latency.get("min_minutes", 15))
    max_minutes = int(latency.get("max_minutes", 120))
    minutes = rng.randint(min_minutes, max_minutes)

  return get_sim_time(db) + timedelta(minutes=minutes)
