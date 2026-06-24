"""NPC policy action executors."""

from __future__ import annotations

from pm_sim.agent.state import add_to_set, get_flag
from pm_sim.npcs.templates import load_message_templates
from pm_sim.npcs.types import NpcContext, NpcReplyPlan, PolicyTemplate
from pm_sim.sim.db import SimDatabase

OAUTH_BLOCKER_KEY = "PROJ-17_oauth_scope"

ACTION_ACK = "ack"


def _message_body(scenario_id: str, action: str) -> str:
  messages = load_message_templates(scenario_id)
  return messages.get(action, messages.get(ACTION_ACK, "Got it, thanks."))


def apply_sam_cooperation_gate(db: SimDatabase, template: PolicyTemplate) -> str:
  action = template.action
  if template.id != "protect_launch_date_pushback":
    return action
  informed = get_flag(db, "stakeholders_informed", [])
  if isinstance(informed, list) and "sam" in informed:
    return "push_back_soft"
  return action


def plan_reply(
  db: SimDatabase,
  template: PolicyTemplate,
  ctx: NpcContext,
) -> NpcReplyPlan:
  scenario_id = db.get_meta("scenario_id") or "first-week-pm"
  action = apply_sam_cooperation_gate(db, template)
  body = _message_body(scenario_id, action)
  disclose = action == "reply_with_full_blocker_details"
  return NpcReplyPlan(
    template_id=template.id,
    action=action,
    body=body,
    disclose_blocker=disclose,
  )


PROJ22_UNBLOCKED_LABEL = "PROJ-22 (Design sign-off) unblocked"


def execute_world_action(db: SimDatabase, action: str) -> bool:
  """Apply a scenario world action. Returns True when the action changed state."""
  if action == "unblock_proj_22":
    cursor = db.conn.execute(
      """
      UPDATE tasks
      SET status = 'todo', blocker_reason = NULL
      WHERE id = 'PROJ-22' AND status = 'blocked'
        AND blocker_reason = 'requirements meeting not held'
      """
    )
    return cursor.rowcount > 0
  return False


def apply_reply_side_effects(db: SimDatabase, plan: NpcReplyPlan) -> None:
  if plan.disclose_blocker:
    add_to_set(db, "blockers_known", OAUTH_BLOCKER_KEY)
