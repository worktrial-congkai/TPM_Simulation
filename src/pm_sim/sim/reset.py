"""Scenario reset orchestration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from datetime import timedelta

from pm_sim.npcs.resolver import resolve_policies
from pm_sim.scenario import validate_scenario
from pm_sim.scenario.load import load_yaml, scenario_dir
from pm_sim.sim.clock import format_sim_time, parse_sim_time
from pm_sim.sim.db import SimDatabase, open_db
from pm_sim.sim.action_duration import DEFAULT_ACTION_DURATIONS, DEFAULT_WAIT_MINUTES
from pm_sim.sim.events import SimEvent

DEFAULT_DB_PATH = Path("data/sim.db")


def _repo_root() -> Path:
  return Path(__file__).resolve().parents[3]


def _seed_agent_state(db: SimDatabase) -> None:
  defaults = {
    "tasks_checked": json.dumps(False),
    "blockers_known": json.dumps([]),
    "blockers_unknown": json.dumps(["PROJ-17"]),
    "channels_read": json.dumps([]),
    "stakeholders_informed": json.dumps([]),
    "tradeoff_decision": json.dumps(None),
    "vendor_escalated": json.dumps(False),
    "requirements_meeting_held": json.dumps(False),
    "tradeoff_documented": json.dumps(False),
    "meetings_joined": json.dumps([]),
    "spam_ping_sent_to": json.dumps([]),
  }
  with db.transaction():
    for key, value in defaults.items():
      db.conn.execute(
        "INSERT INTO agent_state (key, value) VALUES (?, ?)",
        (key, value),
      )


def _insert_event(db: SimDatabase, ev: dict[str, Any]) -> None:
  event = SimEvent.create(
    event_type=ev["event_type"],
    start_ts=parse_sim_time(ev["start_ts"]),
    source=ev.get("source", "scenario:seed"),
    payload=ev.get("payload") or {},
  )
  db.conn.execute(
    """
    INSERT INTO events (id, event_type, start_ts, source, actor_id, payload, status, visibility)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      event.id,
      event.event_type,
      format_sim_time(event.start_ts),
      event.source,
      event.actor_id,
      json.dumps(event.payload),
      event.status,
      event.visibility,
    ),
  )


def _seed_world(
  db: SimDatabase,
  scenario: dict[str, Any],
  coworkers: list[dict[str, Any]],
  templates: list[dict[str, Any]],
  *,
  start_time: str,
) -> None:
  seed = scenario.get("seed") or {}

  with db.transaction():
    for milestone in seed.get("milestones") or []:
      db.conn.execute(
        """
        INSERT INTO milestones (id, title, due_at, status, depends_on_tasks)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
          milestone["id"],
          milestone["title"],
          milestone["due_at"],
          milestone.get("status", "pending"),
          json.dumps(milestone.get("depends_on_tasks") or []),
        ),
      )

    for task in seed.get("tasks") or []:
      db.conn.execute(
        """
        INSERT INTO tasks (
          id, title, status, owner_id, duration_minutes,
          blocker_reason, critical_path, depends_on
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          task["id"],
          task["title"],
          task["status"],
          task.get("owner_id"),
          task.get("duration_minutes"),
          task.get("blocker_reason"),
          1 if task.get("critical_path") else 0,
          json.dumps(task.get("depends_on") or []),
        ),
      )

    for msg in seed.get("chat_messages") or []:
      db.conn.execute(
        """
        INSERT INTO chat_messages (id, channel, sender_id, body, sent_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (msg["id"], msg["channel"], msg["sender_id"], msg["body"], msg["sent_at"]),
      )

    for email in seed.get("emails") or []:
      db.conn.execute(
        """
        INSERT INTO emails (id, sender_id, recipient_id, subject, body, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
          email["id"],
          email["sender_id"],
          email["recipient_id"],
          email["subject"],
          email["body"],
          email["sent_at"],
        ),
      )

    for cal in seed.get("calendar_events") or []:
      db.conn.execute(
        """
        INSERT INTO calendar_events (
          id, title, start_at, end_at, organizer_id, attendee_ids, event_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
          cal["id"],
          cal["title"],
          cal["start_at"],
          cal["end_at"],
          cal.get("organizer_id"),
          json.dumps(cal.get("attendee_ids") or []),
          cal.get("event_type"),
        ),
      )

    for meeting in seed.get("meetings") or []:
      db.conn.execute(
        """
        INSERT INTO meetings (
          id, title, start_at, end_at, attendee_ids, meeting_type, transcript, completed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          meeting["id"],
          meeting["title"],
          meeting["start_at"],
          meeting["end_at"],
          json.dumps(meeting.get("attendee_ids") or []),
          meeting.get("meeting_type"),
          meeting.get("transcript"),
          1 if meeting.get("completed") else 0,
        ),
      )

    for doc in seed.get("docs") or []:
      db.conn.execute(
        """
        INSERT INTO docs (id, title, body, author_id, created_at, doc_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
          doc["id"],
          doc["title"],
          doc["body"],
          doc.get("author_id"),
          doc["created_at"],
          doc.get("doc_type"),
        ),
      )

    for coworker in coworkers:
      db.conn.execute(
        """
        INSERT INTO coworker_state (coworker_id, current_commitments)
        VALUES (?, ?)
        """,
        (coworker["id"], json.dumps([])),
      )
      for template_id in resolve_policies(coworker, templates):
        db.conn.execute(
          "INSERT INTO coworker_policies (coworker_id, template_id) VALUES (?, ?)",
          (coworker["id"], template_id),
        )

    for ev in seed.get("initial_events") or []:
      _insert_event(db, ev)

    for ev in seed.get("drift_events") or []:
      _insert_event(db, ev)

    sim_start = parse_sim_time(start_time)
    for task in seed.get("tasks") or []:
      if task.get("status") != "in_progress":
        continue
      duration = task.get("duration_minutes")
      if not duration:
        continue
      complete_at = sim_start + timedelta(minutes=int(duration))
      _insert_event(
        db,
        {
          "event_type": "task.complete",
          "start_ts": format_sim_time(complete_at),
          "source": f"scenario:seed:{task['id']}",
          "payload": {"task_id": task["id"]},
        },
      )


def reset_scenario(
  scenario_id: str,
  db_path: Path | str = DEFAULT_DB_PATH,
) -> SimDatabase:
  root = _repo_root()
  path = root / db_path if not Path(db_path).is_absolute() else Path(db_path)

  scenario_path = scenario_dir(scenario_id)
  if not scenario_path.exists():
    raise FileNotFoundError(f"Scenario not found: {scenario_id}")

  for warning in validate_scenario(scenario_id):
    print(warning, file=sys.stderr)

  scenario = load_yaml(scenario_path / "scenario.yaml")
  coworkers_data = load_yaml(scenario_path / "coworkers.yaml")
  templates_data = load_yaml(scenario_path / "policy_templates.yaml")

  coworkers = coworkers_data.get("coworkers") or []
  templates = templates_data.get("templates") or []

  sim_cfg = scenario.get("sim") or {}
  world_cfg = scenario.get("world") or {}
  company_cfg = scenario.get("company") or {}
  start_time = sim_cfg["start_time"]
  end_time = sim_cfg["end_time"]
  max_turns = str(sim_cfg.get("max_turns", 15000))
  seed = str(sim_cfg.get("seed", 42))
  wait_minutes = str(sim_cfg.get("wait_minutes", DEFAULT_WAIT_MINUTES))
  scenario_durations = sim_cfg.get("action_durations") or {}
  merged_durations = dict(DEFAULT_ACTION_DURATIONS)
  if isinstance(scenario_durations, dict):
    for key, value in scenario_durations.items():
      merged_durations[str(key)] = int(value)

  if path.exists():
    path.unlink()

  db = open_db(path)
  meta: dict[str, str] = {
    "sim_time": start_time,
    "scenario_id": scenario_id,
    "seed": seed,
    "start_time": start_time,
    "end_time": end_time,
    "max_turns": max_turns,
    "launch_slipped_days": "0",
    "world_vendor_id": world_cfg.get("vendor_id", "vendor_api"),
    "world_exec_id": world_cfg.get("exec_id", "exec"),
    "wait_minutes": wait_minutes,
    "action_durations": json.dumps(merged_durations),
  }
  if company_cfg.get("name"):
    meta["company_name"] = str(company_cfg["name"])
  if company_cfg.get("product"):
    meta["company_product"] = str(company_cfg["product"])
  if company_cfg.get("launch_target"):
    meta["company_launch_target"] = str(company_cfg["launch_target"])
  db.set_meta_batch(meta)

  _seed_agent_state(db)
  _seed_world(db, scenario, coworkers, templates, start_time=start_time)

  return db
