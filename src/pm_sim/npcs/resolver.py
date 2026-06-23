"""NPC policy resolution — reset-time filtering and runtime matching."""

from __future__ import annotations

from typing import Any

from pm_sim.npcs.conditions import evaluate_npc_condition
from pm_sim.npcs.templates import load_policy_templates, template_by_id
from pm_sim.npcs.types import NpcContext, PolicyTemplate
from pm_sim.sim.db import SimDatabase


def resolve_policies(
  coworker: dict[str, Any],
  templates: list[dict[str, Any]],
) -> list[str]:
  effective: list[str] = []
  goals = set(coworker.get("goals") or [])
  constraints = set(coworker.get("constraints") or [])
  role = coworker.get("role")

  for template in templates:
    req_goal = template.get("requires_goal")
    if req_goal and req_goal not in goals:
      continue
    req_constraint = template.get("requires_constraint")
    if req_constraint and req_constraint not in constraints:
      continue
    req_role = template.get("requires_role")
    if req_role and req_role != role:
      continue
    effective.append(template["id"])
  return sorted(effective)


def effective_template_ids(db: SimDatabase, coworker_id: str) -> list[str]:
  rows = db.conn.execute(
    """
    SELECT template_id FROM coworker_policies
    WHERE coworker_id = ?
    ORDER BY template_id
    """,
    (coworker_id,),
  ).fetchall()
  return [row["template_id"] for row in rows]


def pick_matching_template(
  db: SimDatabase,
  coworker_id: str,
  trigger: str,
  ctx: NpcContext,
) -> PolicyTemplate | None:
  scenario_id = db.get_meta("scenario_id") or "first-week-pm"
  effective_ids = effective_template_ids(db, coworker_id)
  if not effective_ids:
    return None

  for template_id in effective_ids:
    template = template_by_id(scenario_id, template_id)
    if template is None or template.trigger != trigger:
      continue
    if evaluate_npc_condition(template.condition, ctx, db):
      return template
  return None


def pick_reactive_reply(
  db: SimDatabase,
  ctx: NpcContext,
) -> tuple[str, PolicyTemplate] | None:
  """Find first coworker + template matching a reactive message_received trigger."""
  candidates: list[str] = []
  if ctx.coworker_id:
    candidates.append(ctx.coworker_id)
  rows = db.conn.execute(
    "SELECT DISTINCT coworker_id FROM coworker_policies ORDER BY coworker_id"
  ).fetchall()
  for row in rows:
    cid = row["coworker_id"]
    if cid not in candidates:
      candidates.append(cid)

  for coworker_id in candidates:
    template = pick_matching_template(db, coworker_id, "message_received", ctx)
    if template is not None:
      return coworker_id, template
  return None


def pick_meeting_template(
  db: SimDatabase,
  ctx: NpcContext,
) -> PolicyTemplate | None:
  rows = db.conn.execute(
    "SELECT DISTINCT coworker_id FROM coworker_policies ORDER BY coworker_id"
  ).fetchall()
  for row in rows:
    template = pick_matching_template(
      db, row["coworker_id"], "meeting_attended", ctx,
    )
    if template is not None:
      return template
  return None
