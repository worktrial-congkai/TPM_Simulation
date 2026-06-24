"""Agent decision-layer types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class PendingReply:
  actor_id: str
  channel: str


@dataclass(frozen=True)
class StakeholderConflict:
  sender_id: str
  name: str
  role: str
  subject: str


@dataclass(frozen=True)
class Observation:
  sim_time: datetime
  blocker_owner: str | None
  blocker_task_id: str | None
  tasks_checked: bool
  vendor_escalated: bool
  requirements_meeting_held: bool
  tradeoff_documented: bool
  blockers_known: tuple[str, ...]
  stakeholders_informed: tuple[str, ...]
  waiting_on_reply: bool
  pending_replies: tuple[PendingReply, ...]
  unread_channels: tuple[str, ...]
  unread_chat_by_channel: tuple[tuple[str, int], ...]
  unread_email_ids: tuple[str, ...]
  blocked_tasks: tuple[str, ...]
  health: str
  stakeholder_conflicts: tuple[StakeholderConflict, ...] = ()


@dataclass(frozen=True)
class AgentAction:
  type: Literal["tool", "wait", "done"]
  name: str
  event_type: str | None = None
  payload: dict | None = None
  policy_condition: str | None = None


@dataclass(frozen=True)
class PolicyRule:
  condition: str
  action: str


@dataclass(frozen=True)
class AgentSpec:
  id: str
  policies: tuple[PolicyRule, ...]


@dataclass(frozen=True)
class WorldConfig:
  vendor_id: str
  exec_id: str
