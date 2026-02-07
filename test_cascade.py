"""
Standalone test: trigger a full NANDA-compliant coordination cascade.

Verifies:
  - NANDA Lean Index (AgentAddr registration)
  - Two-step resolution (AgentAddr → AgentFacts via /.well-known/agent-facts)
  - Ed25519 signatures on AgentAddr
  - Full procurement cascade
  - Network Coordination Report

Prerequisites: all backend services must be running (python run.py).
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx

BASE = "http://localhost"


async def check_health():
    """Verify all services are up."""
    services = {
        "NANDA Index":  8000,
        "Coordinator":  8001,
        "Procurement":  8010,
        "Supplier-1":   8011,
        "Supplier-2":   8012,
        "Manufacturer": 8013,
        "Logistics":    8014,
        "Compliance":   8015,
        "Resolver":     8016,
    }
    async with httpx.AsyncClient(timeout=5) as client:
        for name, port in services.items():
            try:
                r = await client.get(f"{BASE}:{port}/health")
                data = r.json()
                nanda = " [NANDA]" if data.get("nanda") else ""
                print(f"  {name:15s} :{port} -> {data.get('status', '?')}{nanda}")
            except Exception as e:
                print(f"  {name:15s} :{port} -> FAILED ({e})")
                return False
    return True


async def check_nanda_index():
    """Verify NANDA Lean Index stores AgentAddr records."""
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{BASE}:8000/agents")
        addrs = r.json()
        print(f"\n  NANDA Index contains {len(addrs)} AgentAddr records:")
        for a in addrs:
            sig_status = "signed" if a.get("signature") else "unsigned"
            print(f"    - {a['agent_id']}")
            print(f"      name: {a['agent_name']}")
            print(f"      facts: {a['primary_facts_url']}")
            print(f"      ttl: {a.get('ttl', '?')}s | {sig_status}")
        return addrs


async def test_nanda_resolution():
    """Test NANDA two-step resolution: AgentAddr → AgentFacts."""
    print("\n  --- Two-Step Resolution Test ---")
    async with httpx.AsyncClient(timeout=10) as client:
        # Step 1: Resolve AgentAddr from index
        r = await client.get(f"{BASE}:8000/resolve/nanda:supplier-agent-1")
        if r.status_code != 200:
            print(f"  Resolution failed: {r.status_code}")
            return
        addr = r.json()
        print(f"  Step 1 - AgentAddr resolved:")
        print(f"    agent_id: {addr['agent_id']}")
        print(f"    facts_url: {addr['primary_facts_url']}")
        print(f"    ttl: {addr.get('ttl')}s")

        # Step 2: Fetch AgentFacts from agent's self-hosted endpoint
        facts_url = addr["primary_facts_url"]
        r2 = await client.get(facts_url)
        if r2.status_code != 200:
            print(f"  AgentFacts fetch failed: {r2.status_code}")
            return
        facts = r2.json()
        print(f"\n  Step 2 - AgentFacts fetched from {facts_url}:")
        print(f"    label: {facts.get('label')}")
        print(f"    version: {facts.get('version')}")
        print(f"    jurisdiction: {facts.get('jurisdiction')}")
        print(f"    provider: {facts.get('provider', {}).get('name')}")
        print(f"    endpoints: {facts.get('endpoints', {}).get('static', [])}")
        print(f"    skills: {[s.get('id') for s in facts.get('skills', [])]}")
        print(f"    certification: {facts.get('certification', {}).get('level')} by {facts.get('certification', {}).get('issuer')}")
        print(f"    evaluations: score={facts.get('evaluations', {}).get('performance_score')}")
        print(f"    facts_ttl: {facts.get('facts_ttl')}s")
        print(f"    signature: {facts.get('signature', '')[:20]}...")


async def test_nanda_discovery():
    """Test NANDA discovery with lean index."""
    async with httpx.AsyncClient(timeout=5) as client:
        # Find suppliers
        r = await client.post(f"{BASE}:8000/discover", json={"role": "supplier"})
        suppliers = r.json()
        print(f"\n  Discovery (role=supplier): {len(suppliers)} AgentAddr records")

        # Find EU logistics
        r = await client.post(f"{BASE}:8000/discover", json={"role": "logistics"})
        logistics = r.json()
        print(f"  Discovery (role=logistics): {len(logistics)} AgentAddr records")

        # Verify signature
        if suppliers:
            r = await client.post(f"{BASE}:8000/verify", json={"agent_addr": suppliers[0]})
            verify = r.json()
            print(f"  Signature verification for {suppliers[0].get('agent_id')}: valid={verify.get('valid')}")


async def test_wellknown_endpoints():
    """Verify each agent serves /.well-known/agent-facts."""
    ports = {
        "Procurement":  8010,
        "Supplier-1":   8011,
        "Supplier-2":   8012,
        "Manufacturer": 8013,
        "Logistics":    8014,
        "Compliance":   8015,
    }
    async with httpx.AsyncClient(timeout=5) as client:
        for name, port in ports.items():
            try:
                r = await client.get(f"{BASE}:{port}/.well-known/agent-facts")
                facts = r.json()
                print(f"  {name:15s} :{port} -> {facts.get('label', '?')} v{facts.get('version', '?')} [{facts.get('certification', {}).get('level', '?')}]")
            except Exception as e:
                print(f"  {name:15s} :{port} -> FAILED ({e})")


async def test_adaptive_resolver():
    """Test NANDA Adaptive Resolver — context-aware tailored responses."""
    print("\n  --- Adaptive Resolver Test ---")
    async with httpx.AsyncClient(timeout=10) as client:
        # Test 1: Resolve with Maranello context (should prefer EU endpoints)
        r = await client.post(f"{BASE}:8016/resolve", json={
            "agent_name": "urn:agent:oneclickai:supplier:eu:supplier-agent-1",
            "context": {
                "requester_id": "nanda:procurement-agent",
                "geo_location": "Maranello, Italy",
                "geo_lat": 44.53,
                "geo_lon": 10.86,
                "security_level": "authenticated",
                "session_type": "request-response",
            },
        })
        if r.status_code == 200:
            result = r.json()
            rtype = result.get("type", "unknown")
            print(f"  Maranello requester -> {rtype}")
            if rtype == "tailored_response":
                print(f"    endpoint: {result.get('endpoint')}")
                print(f"    transport: {result.get('transport')}")
                print(f"    context_used: {json.dumps(result.get('context_used', {}), indent=2)[:200]}")
                print(f"    ttl: {result.get('ttl')}s")
            elif rtype == "negotiation_invitation":
                print(f"    reason: {result.get('reason')}")
                print(f"    required_context: {result.get('required_context')}")
        else:
            print(f"  Resolution failed: {r.status_code} {r.text[:100]}")

        # Test 2: Check deployment records
        r2 = await client.get(f"{BASE}:8016/health")
        if r2.status_code == 200:
            health = r2.json()
            print(f"\n  Resolver health: {health.get('deployments')} deployments, {health.get('zones')} zones, {health.get('cached_addrs')} cached addrs")

        # Test 3: Context-aware resolution via registry
        r3 = await client.post(f"{BASE}:8000/resolve/adaptive", json={
            "agent_name": "urn:agent:oneclickai:manufacturer:eu:manufacturer-agent",
            "context": {
                "requester_id": "nanda:procurement-agent",
                "geo_location": "Maranello, Italy",
            },
        })
        if r3.status_code == 200:
            result3 = r3.json()
            print(f"\n  Registry adaptive resolve: path={result3.get('resolution_path')}")
        else:
            print(f"  Registry adaptive resolve failed: {r3.status_code}")

        # Test 4: Negotiation endpoint
        r4 = await client.post(f"{BASE}:8016/negotiate", json={
            "agent_id": "nanda:supplier-agent-1",
            "requester_context": {
                "requester_id": "nanda:procurement-agent",
                "geo_location": "Maranello, Italy",
                "security_level": "authenticated",
            },
            "proposed_qos": {"max_latency_ms": 500},
        })
        if r4.status_code == 200:
            neg = r4.json()
            print(f"\n  Negotiation: status={neg.get('status')}, comms_spec={json.dumps(neg.get('comms_spec', {}))[:120]}")

        # Test 5: Check context_requirements in AgentFacts
        r5 = await client.get(f"{BASE}:8013/.well-known/agent-facts")
        if r5.status_code == 200:
            facts = r5.json()
            print(f"\n  Manufacturer context_requirements: {facts.get('context_requirements', [])}")
            deploy = facts.get("deployment")
            if deploy:
                print(f"  Deployment: mode={deploy.get('deployment_mode')}, resources={len(deploy.get('resources', []))}")


async def run_full_cascade():
    """Trigger the full NANDA-compliant procurement cascade."""
    intent = "Buy all the parts required to assemble a Ferrari"
    print(f"\n  Intent: \"{intent}\"")
    print("  Executing cascade (this may take 30-60 seconds)...\n")

    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{BASE}:8010/intent",
            json={"intent": intent},
        )
        result = r.json()

    print("  === CASCADE RESULT ===")
    print(f"  Status:          {result.get('status')}")
    print(f"  Correlation ID:  {result.get('correlation_id')}")
    print(f"  Quotes received: {result.get('quotes_received')}")

    best = result.get("best_quote", {})
    print(f"  Best supplier:   {best.get('supplier_id', 'N/A')}")
    print(f"  Best price:      ${best.get('total_price', 0):,.2f}")
    print(f"  Lead time:       {best.get('lead_time_days', 'N/A')} days")

    order = result.get("order", {})
    print(f"  Order ID:        {order.get('order_id', 'N/A')}")
    print(f"  Agreed price:    ${order.get('agreed_price', 0):,.2f}")

    mfg = result.get("manufacturing_result", {})
    print(f"  Mfg confirmed:   {mfg.get('confirmed', 'N/A')}")
    print(f"  Completion date: {mfg.get('estimated_completion', 'N/A')}")

    return result


async def check_events():
    """Verify events were logged in the coordinator."""
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(f"{BASE}:8001/events")
        events = r.json()
        print(f"\n  Coordinator logged {len(events)} events")

        r2 = await client.get(f"{BASE}:8001/reports")
        reports = r2.json()
        print(f"  Reports generated: {len(reports)}")


async def main():
    print("=" * 65)
    print("  One Click AI — NANDA-Compliant End-to-End Test")
    print("  (with Adaptive Resolver)")
    print("=" * 65)

    print("\n[1/8] Health checks...")
    ok = await check_health()
    if not ok:
        print("\n  Some services are down. Run 'python run.py' first.")
        sys.exit(1)

    print("\n[2/8] NANDA Lean Index verification...")
    await check_nanda_index()

    print("\n[3/8] NANDA two-step resolution test...")
    await test_nanda_resolution()

    print("\n[4/8] NANDA discovery test...")
    await test_nanda_discovery()

    print("\n[5/8] Self-hosted AgentFacts endpoints...")
    await test_wellknown_endpoints()

    print("\n[6/8] Adaptive Resolver test...")
    await test_adaptive_resolver()

    print("\n[7/8] Full cascade execution (with adaptive resolution)...")
    await run_full_cascade()

    print("\n[8/8] Event log verification...")
    await check_events()

    print("\n" + "=" * 65)
    print("  NANDA + ADAPTIVE RESOLVER COMPLIANCE TEST COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
