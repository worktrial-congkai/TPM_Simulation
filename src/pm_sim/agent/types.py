"""Agent decision-layer types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Observation:
  sim_time: datetime
  blocker_owner: str | None
  tasks_checked: bool
  vendor_escalated: bool
  requirements_meeting_held: bool
  tradeoff_documented: bool
  blockers_known: tuple[str, ...]
  stakeholders_informed: tuple[str, ...]
  waiting_on_reply: bool
  unread_channels: tuple[str, ...]
  unread_email_ids: tuple[str, ...]


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
