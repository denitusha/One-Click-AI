#!/usr/bin/env python3
"""End-to-end test for the OneClickAI Supply-Chain Agent Network.

Validates the full coordination cascade:
  1. Check all services are healthy
  2. Verify agents are registered in the NANDA Index
  3. Verify Event Bus is receiving events
  4. Submit a procurement intent
  5. Validate the cascade completes with a report
  6. Check event history covers all cascade phases

Usage
-----
    # Start all services first:
    ./start_all.sh

    # Then run the test:
    python3 test_cascade.py

    # Or run with a custom intent:
    python3 test_cascade.py --intent "Build a high-performance electric sports car"

    # Run only health checks:
    python3 test_cascade.py --health-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

import httpx

# ── Configuration ─────────────────────────────────────────────────────────

INDEX_URL = "http://localhost:6900"
EVENT_BUS_URL = "http://localhost:6020"
PROCUREMENT_URL = "http://localhost:6010"
SUPPLIER_A_URL = "http://localhost:6001"
SUPPLIER_B_URL = "http://localhost:6002"
SUPPLIER_C_URL = "http://localhost:6003"
LOGISTICS_URL = "http://localhost:6004"

DEFAULT_INTENT = "Build a high-performance sports car with carbon fiber body, titanium chassis, and twin-turbo powertrain"

# Expected cascade event types in order
CASCADE_EVENT_TYPES = [
    "AGENT_REGISTERED",
    "INTENT_RECEIVED",
    "BOM_GENERATED",
    "DISCOVERY_QUERY",
    "DISCOVERY_RESULT",
    "AGENTFACTS_FETCHED",
    "VERIFICATION_RESULT",
    "RFQ_SENT",
    "QUOTE_RECEIVED",
    "ACCEPT_SENT",
    "ORDER_PLACED",
    "LOGISTICS_REQUESTED",
    "SHIP_PLAN_RECEIVED",
    "CASCADE_COMPLETE",
]

# ── Colours ───────────────────────────────────────────────────────────────

class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✓{C.END} {msg}")


def fail(msg: str) -> None:
    print(f"  {C.RED}✗{C.END} {msg}")


def info(msg: str) -> None:
    print(f"  {C.BLUE}ℹ{C.END} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠{C.END} {msg}")


def header(msg: str) -> None:
    print(f"\n{C.CYAN}{C.BOLD}{'═' * 60}{C.END}")
    print(f"{C.CYAN}{C.BOLD}  {msg}{C.END}")
    print(f"{C.CYAN}{C.BOLD}{'═' * 60}{C.END}\n")


# ── Health checks ─────────────────────────────────────────────────────────

SERVICES = [
    ("NANDA Index", f"{INDEX_URL}/health"),
    ("Event Bus", f"{EVENT_BUS_URL}/health"),
    ("Supplier A (CrewAI)", f"{SUPPLIER_A_URL}/health"),
    ("Supplier B (Custom)", f"{SUPPLIER_B_URL}/health"),
    ("Supplier C (LangChain)", f"{SUPPLIER_C_URL}/health"),
    ("Logistics Agent", f"{LOGISTICS_URL}/health"),
    ("Procurement Agent", f"{PROCUREMENT_URL}/health"),
]


async def check_health(client: httpx.AsyncClient) -> bool:
    """Check all services are healthy."""
    header("Phase 1: Health Checks")
    all_healthy = True

    for name, url in SERVICES:
        try:
            resp = await client.get(url, timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "unknown")
            extra = ""
            if "framework" in data:
                extra = f" (framework: {data['framework']})"
            if "catalog_parts" in data:
                extra = f" (parts: {data['catalog_parts']})"
            if "agents_loaded" in data:
                extra = f" (agents: {data['agents_loaded']})"
            ok(f"{name}: {status}{extra}")
        except Exception as exc:
            fail(f"{name}: UNREACHABLE — {exc}")
            all_healthy = False

    return all_healthy


# ── Index checks ──────────────────────────────────────────────────────────

async def check_index(client: httpx.AsyncClient) -> bool:
    """Verify agents are registered in the NANDA Index."""
    header("Phase 2: NANDA Index Registration")

    try:
        resp = await client.get(f"{INDEX_URL}/list", timeout=5.0)
        resp.raise_for_status()
        agents = resp.json()
    except Exception as exc:
        fail(f"Could not list agents: {exc}")
        return False

    if not agents:
        fail("No agents registered in the Index")
        return False

    ok(f"{len(agents)} agents registered in the Index")

    expected_agents = ["supplier-a", "supplier-b", "supplier-c", "logistics-agent", "procurement-agent"]
    registered_ids = {a.get("agent_id") for a in agents}

    all_found = True
    for agent_id in expected_agents:
        if agent_id in registered_ids:
            agent = next(a for a in agents if a.get("agent_id") == agent_id)
            skills = agent.get("skills", [])
            ok(f"  {agent_id}: skills={skills}")
        else:
            fail(f"  {agent_id}: NOT REGISTERED")
            all_found = False

    # Check skill search works
    print()
    for skill_keyword, expected_min in [("carbon_fiber", 1), ("titanium", 1), ("logistics", 1)]:
        try:
            resp = await client.get(f"{INDEX_URL}/search", params={"skills": skill_keyword}, timeout=5.0)
            results = resp.json()
            if len(results) >= expected_min:
                ok(f"  Search '{skill_keyword}': {len(results)} result(s)")
            else:
                warn(f"  Search '{skill_keyword}': {len(results)} result(s) (expected >= {expected_min})")
        except Exception as exc:
            fail(f"  Search '{skill_keyword}' failed: {exc}")

    return all_found


# ── AgentFacts checks ─────────────────────────────────────────────────────

async def check_agent_facts(client: httpx.AsyncClient) -> bool:
    """Verify each agent self-hosts AgentFacts correctly."""
    header("Phase 3: AgentFacts Self-Hosting")

    endpoints = [
        ("Supplier A", f"{SUPPLIER_A_URL}/agent-facts"),
        ("Supplier B", f"{SUPPLIER_B_URL}/agent-facts"),
        ("Supplier C", f"{SUPPLIER_C_URL}/agent-facts"),
        ("Logistics", f"{LOGISTICS_URL}/agent-facts"),
        ("Procurement", f"{PROCUREMENT_URL}/agent-facts"),
    ]

    all_ok = True
    for name, url in endpoints:
        try:
            resp = await client.get(url, timeout=5.0)
            resp.raise_for_status()
            facts = resp.json()
            framework = facts.get("framework", "?")
            skills_count = len(facts.get("skills", []))
            reliability = facts.get("reliability_score", "?")
            esg = facts.get("esg_rating", "?")
            ok(f"{name}: framework={framework}, skills={skills_count}, reliability={reliability}, esg={esg}")
        except Exception as exc:
            fail(f"{name}: {exc}")
            all_ok = False

    return all_ok


# ── Event Bus checks ─────────────────────────────────────────────────────

async def check_event_bus(client: httpx.AsyncClient) -> int:
    """Check the Event Bus has received registration events."""
    header("Phase 4: Event Bus")

    try:
        resp = await client.get(f"{EVENT_BUS_URL}/events", timeout=5.0)
        resp.raise_for_status()
        events = resp.json()
    except Exception as exc:
        fail(f"Could not fetch events: {exc}")
        return 0

    if not events:
        warn("No events in Event Bus history (agents may not have emitted startup events)")
        return 0

    # Count event types
    type_counts: dict[str, int] = {}
    for e in events:
        et = e.get("event_type", "?")
        type_counts[et] = type_counts.get(et, 0) + 1

    ok(f"{len(events)} events in history")
    for et, count in sorted(type_counts.items()):
        info(f"  {et}: {count}")

    # Check for registration events
    reg_count = type_counts.get("AGENT_REGISTERED", 0)
    if reg_count >= 5:
        ok(f"All 5 agents emitted AGENT_REGISTERED events ({reg_count} total)")
    else:
        warn(f"Only {reg_count} AGENT_REGISTERED events (expected >= 5)")

    return len(events)


# ── Full cascade test ─────────────────────────────────────────────────────

async def run_cascade(client: httpx.AsyncClient, intent: str) -> dict[str, Any] | None:
    """Submit an intent and wait for the cascade to complete."""
    header("Phase 5: Full Coordination Cascade")

    info(f"Submitting intent: \"{intent}\"")
    print()

    start_time = time.time()

    try:
        resp = await client.post(
            f"{PROCUREMENT_URL}/intent",
            json={"intent": intent},
            timeout=300.0,  # 5 minute timeout for full cascade
        )
        elapsed = time.time() - start_time

        if resp.status_code == 200:
            result = resp.json()
            status = result.get("status", "unknown")
            ok(f"Cascade completed in {elapsed:.1f}s (status: {status})")
            return result
        else:
            fail(f"Cascade failed with HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except httpx.TimeoutException:
        elapsed = time.time() - start_time
        fail(f"Cascade timed out after {elapsed:.1f}s")
        return None
    except Exception as exc:
        fail(f"Cascade error: {exc}")
        return None


# ── Validate cascade results ─────────────────────────────────────────────

def validate_report(result: dict[str, Any]) -> bool:
    """Validate the cascade produced a valid report."""
    header("Phase 6: Report Validation")

    report = result.get("report")
    if not report:
        fail("No report in cascade result")
        return False

    ok("Report generated successfully")

    # Check sections
    sections = [
        "report_id", "generated_at", "bom_summary",
        "discovery_paths", "trust_verification",
        "policy_enforcement", "message_exchanges", "execution_plan",
    ]
    for section in sections:
        if section in report:
            ok(f"  Section: {section}")
        else:
            fail(f"  Missing section: {section}")

    # BOM summary
    bom = report.get("bom_summary", {})
    total_parts = bom.get("total_parts", 0)
    systems = bom.get("systems", [])
    info(f"  BOM: {total_parts} parts across {len(systems)} systems ({', '.join(systems)})")

    # Trust verification
    trust = report.get("trust_verification", {})
    verified = trust.get("verified_count", 0)
    rejected = trust.get("rejected_count", 0)
    info(f"  Verification: {verified} verified, {rejected} rejected")

    # Execution plan
    plan = report.get("execution_plan", {})
    total_cost = plan.get("total_cost", 0)
    parts_ordered = plan.get("parts_ordered", 0)
    suppliers = plan.get("suppliers_engaged", 0)
    info(f"  Execution: {parts_ordered} parts ordered from {suppliers} suppliers")
    info(f"  Total cost: EUR {total_cost:,.2f}")

    # Orders
    orders = plan.get("orders", [])
    if orders:
        ok(f"  {len(orders)} orders placed:")
        for o in orders:
            info(f"    Order #{o.get('order_id', '?')[:8]}: "
                 f"{o.get('part', '?')} × {o.get('quantity', '?')} "
                 f"@ EUR {o.get('unit_price', 0):.2f} = EUR {o.get('total_price', 0):.2f} "
                 f"(from {o.get('supplier_id', '?')})")
    else:
        warn("  No orders placed")

    # Logistics plans
    logistics = plan.get("logistics_plans", [])
    if logistics:
        ok(f"  {len(logistics)} logistics plans:")
        for lp in logistics:
            route = lp.get("route", [])
            info(f"    {' → '.join(route)}: "
                 f"{lp.get('total_distance_km', 0):.0f} km, "
                 f"{lp.get('transit_time_days', 0)} days, "
                 f"EUR {lp.get('cost', 0):.2f} "
                 f"(carrier: {lp.get('carrier', '?')})")
    else:
        warn("  No logistics plans")

    # Message exchanges
    msg_ex = report.get("message_exchanges", {})
    total_msgs = msg_ex.get("total_messages", 0)
    rounds = msg_ex.get("negotiation_rounds", 0)
    info(f"  Messages exchanged: {total_msgs} across {rounds} negotiation rounds")

    return parts_ordered > 0


# ── Validate Event Bus history post-cascade ───────────────────────────────

async def validate_events(
    client: httpx.AsyncClient, pre_event_count: int
) -> bool:
    """Verify the Event Bus received the expected cascade events."""
    header("Phase 7: Event Bus Validation")

    try:
        resp = await client.get(f"{EVENT_BUS_URL}/events", params={"limit": 500}, timeout=5.0)
        resp.raise_for_status()
        events = resp.json()
    except Exception as exc:
        fail(f"Could not fetch events: {exc}")
        return False

    new_events = events[pre_event_count:]
    ok(f"{len(new_events)} new events generated during cascade (total: {len(events)})")

    # Count event types
    type_counts: dict[str, int] = {}
    for e in new_events:
        et = e.get("event_type", "?")
        type_counts[et] = type_counts.get(et, 0) + 1

    # Display summary
    for et in CASCADE_EVENT_TYPES:
        count = type_counts.get(et, 0)
        if count > 0:
            ok(f"  {et}: {count}")
        elif et == "AGENT_REGISTERED":
            # May not appear if agents were already registered
            info(f"  {et}: {count} (agents pre-registered)")
        else:
            warn(f"  {et}: {count} (MISSING)")

    # Check for counter-offer events (stretch)
    counter = type_counts.get("COUNTER_SENT", 0)
    revised = type_counts.get("REVISED_RECEIVED", 0)
    if counter > 0:
        ok(f"  Counter-offer negotiation: {counter} counter(s), {revised} revised quote(s)")

    # Check cascade complete
    if "CASCADE_COMPLETE" in type_counts:
        ok("CASCADE_COMPLETE event received — full cascade verified!")
        return True
    else:
        fail("CASCADE_COMPLETE event NOT received")
        return False


# ── Main ──────────────────────────────────────────────────────────────────

async def main(intent: str, health_only: bool = False) -> int:
    """Run the full end-to-end test."""
    print()
    print(f"{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════════════════╗{C.END}")
    print(f"{C.CYAN}{C.BOLD}║   OneClickAI Supply-Chain — End-to-End Integration Test     ║{C.END}")
    print(f"{C.CYAN}{C.BOLD}╚══════════════════════════════════════════════════════════════╝{C.END}")

    passed = 0
    failed = 0

    async with httpx.AsyncClient() as client:
        # Phase 1: Health
        if await check_health(client):
            passed += 1
        else:
            failed += 1
            if health_only:
                print(f"\n{C.RED}Some services are not healthy. Start them first with ./start_all.sh{C.END}\n")
                return 1

        if health_only:
            print(f"\n{C.GREEN}All services are healthy!{C.END}\n")
            return 0

        # Phase 2: Index
        if await check_index(client):
            passed += 1
        else:
            failed += 1

        # Phase 3: AgentFacts
        if await check_agent_facts(client):
            passed += 1
        else:
            failed += 1

        # Phase 4: Event Bus
        pre_count = await check_event_bus(client)
        passed += 1  # always passes (informational)

        # Phase 5: Full cascade
        result = await run_cascade(client, intent)
        if result:
            passed += 1
        else:
            failed += 1
            # Skip remaining phases
            print(f"\n{C.RED}Cascade failed — skipping report and event validation.{C.END}\n")
            return 1

        # Phase 6: Report validation
        if validate_report(result):
            passed += 1
        else:
            failed += 1

        # Phase 7: Event validation
        if await validate_events(client, pre_count):
            passed += 1
        else:
            failed += 1

    # ── Summary ───────────────────────────────────────────────────────
    header("Test Summary")
    print(f"  {C.GREEN}Passed: {passed}{C.END}")
    print(f"  {C.RED}Failed: {failed}{C.END}")

    if failed == 0:
        print(f"\n{C.GREEN}{C.BOLD}  ALL TESTS PASSED — Full cascade integration verified!{C.END}\n")
        return 0
    else:
        print(f"\n{C.YELLOW}  {failed} check(s) had issues. Review output above.{C.END}\n")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="End-to-end integration test for the OneClickAI supply-chain agent network."
    )
    parser.add_argument(
        "--intent",
        default=DEFAULT_INTENT,
        help="Procurement intent to test with",
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Only run health checks (skip cascade test)",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.intent, args.health_only))
    sys.exit(exit_code)
