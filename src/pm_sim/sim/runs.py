"""Run registry helpers for Phase 6 run loop."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from pm_sim.sim.db import SimDatabase
from pm_sim.sim.reset import _repo_root

DATA_RUNS_DIR = Path("data/runs")


def runs_root(base: Path | None = None) -> Path:
  return base if base is not None else _repo_root() / DATA_RUNS_DIR


def run_artifact_dir(run_id: str, base: Path | None = None) -> Path:
  return runs_root(base) / run_id


def create_run(
  db: SimDatabase,
  *,
  scenario_id: str,
  agent_id: str,
  base: Path | None = None,
) -> tuple[str, Path]:
  run_id = str(uuid.uuid4())
  seed = int(db.get_meta("seed") or "0")
  started_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")

  db.conn.execute(
    """
    INSERT INTO runs (id, scenario_id, agent_id, status, started_at, ended_at, seed)
    VALUES (?, ?, ?, 'running', ?, NULL, ?)
    """,
    (run_id, scenario_id, agent_id, started_at, seed),
  )
  db.conn.commit()

  artifact_dir = run_artifact_dir(run_id, base=base)
  artifact_dir.mkdir(parents=True, exist_ok=True)

  db.set_meta("active_run_id", run_id)
  db.set_meta("current_turn", "0")
  return run_id, artifact_dir


def finalize_run(
  db: SimDatabase,
  run_id: str,
  *,
  status: str,
) -> None:
  ended_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
  db.conn.execute(
    "UPDATE runs SET status = ?, ended_at = ? WHERE id = ?",
    (status, ended_at, run_id),
  )
  db.conn.commit()


def clear_run_context(db: SimDatabase) -> None:
  db.conn.execute("DELETE FROM sim_meta WHERE key IN ('active_run_id', 'current_turn')")
  db.conn.commit()


def get_run(db: SimDatabase, run_id: str) -> dict | None:
  row = db.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
  if row is None:
    return None
  return dict(row)
