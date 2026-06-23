"""SQLite database wrapper with schema management and transactions."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Generator, Iterator


class SimDatabase:
  """Thin wrapper around sqlite3 with transaction support."""

  def __init__(self, path: Path | str) -> None:
    self.path = Path(path)
    self.path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(self.path)
    self._conn.row_factory = sqlite3.Row
    self._conn.execute("PRAGMA foreign_keys = ON")

  @property
  def conn(self) -> sqlite3.Connection:
    return self._conn

  def close(self) -> None:
    self._conn.close()

  def init_schema(self) -> None:
    schema_path = resources.files("pm_sim.sim").joinpath("schema.sql")
    ddl = schema_path.read_text(encoding="utf-8")
    self._conn.executescript(ddl)
    self._conn.commit()

  def wipe(self) -> None:
    self.close()
    if self.path.exists():
      self.path.unlink()

  @contextmanager
  def transaction(self) -> Iterator[sqlite3.Connection]:
    try:
      self._conn.execute("BEGIN")
      yield self._conn
      self._conn.commit()
    except Exception:
      self._conn.rollback()
      raise

  def get_meta(self, key: str) -> str | None:
    row = self._conn.execute(
      "SELECT value FROM sim_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None

  def set_meta(self, key: str, value: str) -> None:
    self._conn.execute(
      "INSERT INTO sim_meta (key, value) VALUES (?, ?) "
      "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      (key, value),
    )
    self._conn.commit()

  def set_meta_batch(self, pairs: dict[str, str]) -> None:
    with self.transaction():
      for key, value in pairs.items():
        self._conn.execute(
          "INSERT INTO sim_meta (key, value) VALUES (?, ?) "
          "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
          (key, value),
        )


def open_db(path: Path | str) -> SimDatabase:
  db = SimDatabase(path)
  db.init_schema()
  return db


def open_existing_db(path: Path | str) -> SimDatabase:
  """Open a scenario database that was previously reset (does not re-seed)."""
  db = SimDatabase(path)
  if db.get_meta("sim_time") is None:
    db.close()
    raise RuntimeError(
      "Database not initialized. Run: pm-sim scenario reset <scenario_id>"
    )
  return db
