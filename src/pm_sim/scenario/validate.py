"""Scenario package validation."""

from __future__ import annotations

from pm_sim.npcs.resolver import resolve_policies
from pm_sim.scenario.load import load_yaml, scenario_dir

REQUIRED_FILES = (
  "scenario.yaml",
  "coworkers.yaml",
  "policy_templates.yaml",
  "message_templates.yaml",
  "eval_rubric.yaml",
)

CRITICAL_TASK_IDS = ("PROJ-17", "PROJ-22", "PROJ-30")
CRITICAL_MILESTONE_ID = "launch"


class ScenarioValidationError(Exception):
  """Raised when scenario validation fails with hard errors."""


def validate_scenario(scenario_id: str) -> list[str]:
  """Validate scenario package. Returns warnings; raises on hard errors."""
  path = scenario_dir(scenario_id)
  if not path.is_dir():
    raise ScenarioValidationError(f"Scenario not found: {scenario_id}")

  warnings: list[str] = []
  for filename in REQUIRED_FILES:
    if not (path / filename).exists():
      raise ScenarioValidationError(f"Missing required file: {filename}")

  scenario = load_yaml(path / "scenario.yaml")
  coworkers_data = load_yaml(path / "coworkers.yaml")
  templates_data = load_yaml(path / "policy_templates.yaml")

  sim_cfg = scenario.get("sim") or {}
  for key in ("start_time", "end_time", "max_turns"):
    if key not in sim_cfg:
      raise ScenarioValidationError(f"sim.{key} is required in scenario.yaml")

  coworkers = coworkers_data.get("coworkers") or []
  coworker_ids = {c["id"] for c in coworkers}
  templates = templates_data.get("templates") or []
  template_ids = {t["id"] for t in templates}

  assigned: set[str] = set()
  for coworker in coworkers:
    for template_id in resolve_policies(coworker, templates):
      if template_id not in template_ids:
        raise ScenarioValidationError(
          f"Unknown template id {template_id!r} assigned to {coworker['id']}"
        )
      assigned.add(template_id)

  for template_id in sorted(template_ids - assigned):
    warnings.append(f"Orphan policy template (no coworker): {template_id}")

  seed = scenario.get("seed") or {}
  task_ids = {t["id"] for t in (seed.get("tasks") or [])}
  for task_id in CRITICAL_TASK_IDS:
    if task_id not in task_ids:
      raise ScenarioValidationError(f"Missing critical-path task: {task_id}")

  milestone_ids = {m["id"] for m in (seed.get("milestones") or [])}
  if CRITICAL_MILESTONE_ID not in milestone_ids:
    raise ScenarioValidationError(f"Missing milestone: {CRITICAL_MILESTONE_ID}")

  _validate_coworker_refs(seed, coworker_ids)

  return warnings


def _validate_coworker_refs(seed: dict, coworker_ids: set[str]) -> None:
  for msg in seed.get("chat_messages") or []:
    sender = msg.get("sender_id")
    if sender and sender not in coworker_ids and sender != "agent":
      raise ScenarioValidationError(f"Unknown chat sender_id: {sender}")

  for email in seed.get("emails") or []:
    for field in ("sender_id", "recipient_id"):
      party = email.get(field)
      if party and party not in coworker_ids and party != "agent":
        raise ScenarioValidationError(f"Unknown email {field}: {party}")

  for task in seed.get("tasks") or []:
    owner = task.get("owner_id")
    if owner and owner not in coworker_ids:
      raise ScenarioValidationError(f"Unknown task owner_id: {owner}")

  for cal in seed.get("calendar_events") or []:
    organizer = cal.get("organizer_id")
    if organizer and organizer not in coworker_ids and organizer != "agent":
      raise ScenarioValidationError(f"Unknown calendar organizer_id: {organizer}")
    for attendee in cal.get("attendee_ids") or []:
      if attendee not in coworker_ids and attendee != "agent":
        raise ScenarioValidationError(f"Unknown calendar attendee: {attendee}")
