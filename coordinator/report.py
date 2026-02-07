"""Generates the Network Coordination Report from cascade events."""

from __future__ import annotations

from datetime import datetime

from shared.schemas import (
    CoordinationStep,
    MessageType,
    NetworkCoordinationReport,
)


class ReportBuilder:
    """Accumulates events and produces a NetworkCoordinationReport."""

    def __init__(self, intent: str) -> None:
        self.intent = intent
        self.started_at = datetime.utcnow().isoformat()
        self._step_counter = 0
        self.steps: list[CoordinationStep] = []
        self.discovery_paths: list[dict] = []
        self.trust_verification: list[dict] = []
        self.policy_enforcement: list[dict] = []
        self.final_plan: dict = {}
        self.total_cost: float = 0.0
        self.total_lead_time_days: int = 0

    def add_step(
        self,
        from_agent: str,
        to_agent: str,
        action: str,
        message_type: MessageType,
        explanation: str,
        duration_ms: int | None = None,
    ) -> CoordinationStep:
        self._step_counter += 1
        step = CoordinationStep(
            step_number=self._step_counter,
            timestamp=datetime.utcnow().isoformat(),
            from_agent=from_agent,
            to_agent=to_agent,
            action=action,
            message_type=message_type,
            explanation=explanation,
            duration_ms=duration_ms,
        )
        self.steps.append(step)
        return step

    def add_discovery_path(self, query: dict, results: list[str]) -> None:
        self.discovery_paths.append({"query": query, "matched_agents": results})

    def add_trust_record(self, agent_id: str, score: float, verified: bool) -> None:
        self.trust_verification.append(
            {"agent_id": agent_id, "reputation_score": score, "verified": verified}
        )

    def add_policy_record(
        self, order_id: str, compliant: bool, issues: list[str]
    ) -> None:
        self.policy_enforcement.append(
            {"order_id": order_id, "compliant": compliant, "issues": issues}
        )

    def build(self) -> NetworkCoordinationReport:
        return NetworkCoordinationReport(
            intent=self.intent,
            started_at=self.started_at,
            completed_at=datetime.utcnow().isoformat(),
            cascade_steps=self.steps,
            discovery_paths=self.discovery_paths,
            trust_verification=self.trust_verification,
            policy_enforcement=self.policy_enforcement,
            final_execution_plan=self.final_plan,
            total_cost=self.total_cost,
            total_lead_time_days=self.total_lead_time_days,
            status="completed",
        )
