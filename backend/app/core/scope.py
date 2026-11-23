"""Whose records a request may touch (platform ADR 0008 and 0012).

Every private query in Hearthline is built from a ``Scope`` and never from a
request body, query string or path. A scope is one of two separate worlds:

- legacy: a Hearthline account signed in with its own session. It sees rows
  that carry its ``user_id`` and no platform scope.
- platform: a person with a verified platform context. It sees rows of its own
  workspace and owner subject, and nothing else: not another subject's rows in
  the same workspace, not the same subject's rows in another workspace, and
  not a legacy account's rows.

A record that belongs to another scope is indistinguishable from one that does
not exist (404, never 403).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    user_id: str | None = None
    workspace_id: str | None = None
    owner_sub: str | None = None

    def __post_init__(self) -> None:
        legacy = self.user_id is not None
        platform = self.workspace_id is not None or self.owner_sub is not None
        if legacy == platform or (platform and (self.workspace_id is None or self.owner_sub is None)):
            raise ValueError("a scope is either a legacy account or a workspace with an owner subject")

    @classmethod
    def legacy(cls, user_id: str) -> "Scope":
        return cls(user_id=user_id)

    @classmethod
    def platform(cls, workspace_id: str, owner_sub: str) -> "Scope":
        return cls(workspace_id=workspace_id, owner_sub=owner_sub)

    @property
    def is_platform(self) -> bool:
        return self.user_id is None

    def match(self, alias: str = "") -> tuple[str, tuple[str, ...]]:
        """A WHERE fragment and its parameters selecting exactly this scope's rows."""
        prefix = f"{alias}." if alias else ""
        if self.is_platform:
            return f"{prefix}workspace_id = ? AND {prefix}owner_sub = ?", (self.workspace_id, self.owner_sub)  # type: ignore[return-value]
        return f"{prefix}user_id = ? AND {prefix}workspace_id IS NULL", (self.user_id,)  # type: ignore[return-value]

    def columns(self) -> tuple[str, ...]:
        """The owner columns an INSERT must set, in the order ``values`` returns them."""
        return ("workspace_id", "owner_sub") if self.is_platform else ("user_id",)

    def values(self) -> tuple[str, ...]:
        return (self.workspace_id, self.owner_sub) if self.is_platform else (self.user_id,)  # type: ignore[return-value]

    def conflict_target(self, *keys: str) -> str:
        """The ON CONFLICT column list for a key that includes this scope."""
        return ", ".join((*self.columns(), *keys))
