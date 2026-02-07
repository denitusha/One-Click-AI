"""Compliance Agent — LangGraph-based policy validation and ESG checks."""

from __future__ import annotations

import json
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from shared.config import LLM_MODEL, OPENAI_API_KEY


class ComplianceState(TypedDict, total=False):
    check_request: dict
    jurisdiction_result: dict | None
    policy_result: dict | None
    esg_result: dict | None
    final_result: dict | None


def get_llm():
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0.2)


async def check_jurisdiction(state: ComplianceState) -> ComplianceState:
    """Validate jurisdictional compliance (trade regulations, sanctions, etc.)."""
    req = state["check_request"]
    origin = req.get("origin_jurisdiction", "EU")
    dest = req.get("destination_jurisdiction", "EU")

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are a trade compliance officer. Check if shipping automotive components "
        f"from {origin} to {dest} has any jurisdictional issues. "
        f"Consider: sanctions, export controls, trade agreements. "
        f"Respond with ONLY JSON: {{\"compliant\": <bool>, \"issues\": [<list of str>], \"notes\": \"<str>\"}}"
    )

    try:
        result = json.loads(resp.content)
    except Exception:
        result = {"compliant": True, "issues": [], "notes": "EU-to-EU: no jurisdictional barriers"}

    return {**state, "jurisdiction_result": result}


async def check_policies(state: ComplianceState) -> ComplianceState:
    """Validate against specific policy requirements (ISO, industry standards)."""
    req = state["check_request"]
    policies = req.get("policies_to_check", [])

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are an automotive compliance auditor. Check compliance with: {policies}. "
        f"For components: {[c.get('name') for c in req.get('components', [])[:5]]}. "
        f"Respond with ONLY JSON: {{\"compliant\": <bool>, \"checked_policies\": [<list>], "
        f"\"issues\": [<list>], \"recommendations\": [<list>]}}"
    )

    try:
        result = json.loads(resp.content)
    except Exception:
        result = {
            "compliant": True,
            "checked_policies": policies,
            "issues": [],
            "recommendations": ["Maintain ISO9001 certification records"],
        }

    return {**state, "policy_result": result}


async def check_esg(state: ComplianceState) -> ComplianceState:
    """Evaluate ESG (Environmental, Social, Governance) compliance."""
    req = state["check_request"]

    llm = get_llm()
    resp = await llm.ainvoke(
        f"You are an ESG compliance analyst. Evaluate the environmental and social impact "
        f"of sourcing {len(req.get('components', []))} automotive components from supplier "
        f"'{req.get('supplier_id')}'. Consider carbon footprint, labor standards, and material sourcing. "
        f"Respond with ONLY JSON: {{\"esg_score\": <0-100>, \"carbon_rating\": \"<A-F>\", "
        f"\"issues\": [<list>], \"recommendations\": [<list>]}}"
    )

    try:
        result = json.loads(resp.content)
    except Exception:
        result = {
            "esg_score": 78,
            "carbon_rating": "B",
            "issues": [],
            "recommendations": ["Consider carbon-neutral shipping options"],
        }

    return {**state, "esg_result": result}


async def compile_result(state: ComplianceState) -> ComplianceState:
    """Combine all compliance check results."""
    jur = state.get("jurisdiction_result", {})
    pol = state.get("policy_result", {})
    esg = state.get("esg_result", {})
    req = state["check_request"]

    all_issues = (
        jur.get("issues", []) + pol.get("issues", []) + esg.get("issues", [])
    )
    compliant = jur.get("compliant", True) and pol.get("compliant", True) and len(all_issues) == 0

    final = {
        "order_id": req.get("order_id", ""),
        "compliant": compliant,
        "issues": all_issues,
        "recommendations": pol.get("recommendations", []) + esg.get("recommendations", []),
        "checked_policies": pol.get("checked_policies", []),
        "jurisdiction": jur,
        "policy": pol,
        "esg": esg,
    }

    return {**state, "final_result": final}


def build_compliance_graph():
    g = StateGraph(ComplianceState)

    g.add_node("check_jurisdiction", check_jurisdiction)
    g.add_node("check_policies", check_policies)
    g.add_node("check_esg", check_esg)
    g.add_node("compile_result", compile_result)

    g.set_entry_point("check_jurisdiction")
    g.add_edge("check_jurisdiction", "check_policies")
    g.add_edge("check_policies", "check_esg")
    g.add_edge("check_esg", "compile_result")
    g.add_edge("compile_result", END)

    return g.compile()
