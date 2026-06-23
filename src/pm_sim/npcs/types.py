"""NPC policy types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class PolicyTemplate:
  id: str
  trigger: str
  condition: str
  action: str
  requires_role: str | None = None
  requires_goal: str | None = None
  requires_constraint: str | None = None


@dataclass(frozen=True)
class NpcContext:
  coworker_id: str
  channel: str = ""
  topic: str | None = None
  message_kind: Literal["dm", "channel", "email"] = "dm"
  meeting_type: str | None = None


@dataclass
class NpcReplyPlan:
  template_id: str
  action: str
  body: str
  disclose_blocker: bool = False
  side_effects: list[str] = field(default_factory=list)
