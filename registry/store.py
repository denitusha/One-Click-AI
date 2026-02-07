"""NANDA Lean Index Store — stores AgentAddr records with TTL and two-step resolution."""

from __future__ import annotations

import time
from typing import Optional

from shared.agent_facts import AgentAddr


class CachedEntry:
    """AgentAddr with expiration tracking."""

    __slots__ = ("addr", "registered_at", "expires_at")

    def __init__(self, addr: AgentAddr) -> None:
        self.addr = addr
        self.registered_at = time.time()
        self.expires_at = self.registered_at + addr.ttl

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


class NandaIndexStore:
    """In-memory lean index — stores ONLY AgentAddr records (not full AgentFacts).

    Resolution flow per NANDA paper:
      1. Client queries index → receives AgentAddr (~120 bytes)
      2. Client fetches AgentFacts from primary_facts_url or private_facts_url
    """

    def __init__(self) -> None:
        self._entries: dict[str, CachedEntry] = {}  # agent_id -> CachedEntry
        self._name_index: dict[str, str] = {}  # agent_name -> agent_id

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, addr: AgentAddr) -> AgentAddr:
        """Register or update a lean AgentAddr record in the index."""
        self._entries[addr.agent_id] = CachedEntry(addr)
        self._name_index[addr.agent_name] = addr.agent_id
        return addr

    # ------------------------------------------------------------------
    # Resolution (analogous to DNS lookup)
    # ------------------------------------------------------------------

    def resolve_by_id(self, agent_id: str) -> Optional[AgentAddr]:
        """Resolve agent_id to AgentAddr (direct resolution path)."""
        entry = self._entries.get(agent_id)
        if entry and not entry.expired:
            return entry.addr
        return None

    def resolve_by_name(self, agent_name: str) -> Optional[AgentAddr]:
        """Resolve agent_name (URN) to AgentAddr."""
        agent_id = self._name_index.get(agent_name)
        if agent_id:
            return self.resolve_by_id(agent_id)
        return None

    # ------------------------------------------------------------------
    # Discovery (semantic search over index metadata)
    # ------------------------------------------------------------------

    def discover(
        self,
        role: Optional[str] = None,
        capability: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        query: Optional[str] = None,
    ) -> list[AgentAddr]:
        """Search the lean index. Because AgentAddr is minimal, discovery
        uses the agent_name URN structure and agent_id prefixes.

        For richer filtering (skills, evaluations, etc.), clients should
        fetch AgentFacts from the primary_facts_url after initial discovery.
        """
        results: list[AgentAddr] = []
        now = time.time()

        for entry in self._entries.values():
            if entry.expires_at < now:
                continue  # skip expired
            addr = entry.addr

            # Filter by role (encoded in agent_name URN or agent_id)
            if role:
                role_lower = role.lower()
                if (
                    role_lower not in addr.agent_id.lower()
                    and role_lower not in addr.agent_name.lower()
                ):
                    continue

            # Filter by capability (check in agent_name URN)
            if capability:
                cap_lower = capability.lower()
                if cap_lower not in addr.agent_name.lower() and cap_lower not in addr.agent_id.lower():
                    continue

            # Filter by jurisdiction (encoded in agent_name URN)
            if jurisdiction:
                jur_lower = jurisdiction.lower()
                if jur_lower not in addr.agent_name.lower():
                    continue

            # Free-text query
            if query:
                q = query.lower()
                if (
                    q not in addr.agent_id.lower()
                    and q not in addr.agent_name.lower()
                    and q not in (addr.primary_facts_url or "").lower()
                ):
                    continue

            results.append(addr)

        return results

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def list_all(self) -> list[AgentAddr]:
        """List all non-expired AgentAddr records."""
        now = time.time()
        return [
            e.addr for e in self._entries.values() if e.expires_at >= now
        ]

    def remove(self, agent_id: str) -> bool:
        entry = self._entries.pop(agent_id, None)
        if entry:
            self._name_index.pop(entry.addr.agent_name, None)
            return True
        return False

    def count(self) -> int:
        return len(self._entries)
