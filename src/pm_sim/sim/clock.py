"""Simulation clock backed by sim_meta."""

from __future__ import annotations

from datetime import datetime, timedelta

from pm_sim.sim.db import SimDatabase

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def parse_sim_time(value: str) -> datetime:
  return datetime.strptime(value, ISO_FORMAT)


def format_sim_time(dt: datetime) -> str:
  return dt.strftime(ISO_FORMAT)


def get_sim_time(db: SimDatabase) -> datetime:
  raw = db.get_meta("sim_time")
  if raw is None:
    raise RuntimeError("sim_time not set in sim_meta")
  return parse_sim_time(raw)


def set_sim_time(db: SimDatabase, dt: datetime) -> None:
  db.set_meta("sim_time", format_sim_time(dt))


def advance_clock(db: SimDatabase, minutes: int = 1) -> datetime:
  current = get_sim_time(db)
  new_time = current + timedelta(minutes=minutes)
  set_sim_time(db, new_time)
  return new_time
