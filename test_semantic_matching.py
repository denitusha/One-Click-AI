#!/usr/bin/env python3
"""Test script for semantic matching in the NANDA Index resolver.

Tests that semantically equivalent but differently named skills can match.
For example, "composite materials" should match "carbon_fiber_panels".
"""

import asyncio
import httpx
import sys
from typing import Any


INDEX_URL = "http://localhost:6900"


async def test_resolve_endpoint(query: str, expected_match: str | None = None) -> dict[str, Any]:
    """Test the /resolve endpoint with a semantic query."""
    print(f"\n{'='*70}")
    print(f"Testing query: '{query}'")
    print(f"Expected match skill: {expected_match or 'any'}")
    print(f"{'='*70}")
    
    resolve_body = {
        "query": query,
        "skill_hint": "",
        "context": {
            "region": "EU",
            "compliance_requirements": [],
            "urgency": "standard",
        },
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{INDEX_URL}/resolve", json=resolve_body)
            resp.raise_for_status()
            results = resp.json()
            
            print(f"\nFound {len(results)} suppliers:")
            for i, result in enumerate(results[:5], 1):  # Show top 5
                print(f"  {i}. {result['agent_name']}")
                print(f"     Agent ID: {result['agent_id']}")
                print(f"     Matched skill: {result['matched_skill']}")
                print(f"     Match reason: {result['match_reason']}")
                print(f"     Relevance: {result['relevance_score']:.3f}")
                print(f"     Context: {result['context_score']:.3f}")
                print(f"     Combined: {result['combined_score']:.3f}")
                print()
            
            # Check if expected match is present
            if expected_match and results:
                matched_skills = [r['matched_skill'] for r in results]
                if expected_match in matched_skills:
                    print(f"✅ SUCCESS: Expected skill '{expected_match}' was matched!")
                    return {"success": True, "results": results}
                else:
                    print(f"❌ WARNING: Expected skill '{expected_match}' not found in results")
                    print(f"   Matched skills were: {matched_skills[:5]}")
                    return {"success": False, "results": results}
            
            return {"success": len(results) > 0, "results": results}
    
    except Exception as exc:
        print(f"❌ ERROR: {exc}")
        return {"success": False, "error": str(exc)}


async def test_substring_fallback(query: str) -> dict[str, Any]:
    """Test that substring matching still works as fallback."""
    print(f"\n{'='*70}")
    print(f"Testing substring fallback: '{query}'")
    print(f"{'='*70}")
    
    # Test with skill_hint for exact match
    resolve_body = {
        "query": "",  # Empty query to trigger substring path
        "skill_hint": query,
        "context": {},
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{INDEX_URL}/resolve", json=resolve_body)
            resp.raise_for_status()
            results = resp.json()
            
            print(f"\nFound {len(results)} exact matches")
            if results:
                print(f"  Matched: {results[0]['agent_name']}")
                print(f"  Match reason: {results[0]['match_reason']}")
                print(f"✅ Exact match works")
            
            return {"success": len(results) > 0, "results": results}
    
    except Exception as exc:
        print(f"❌ ERROR: {exc}")
        return {"success": False, "error": str(exc)}


async def main():
    """Run all semantic matching tests."""
    print("="*70)
    print("SEMANTIC MATCHING TEST SUITE")
    print("="*70)
    print("\nThis test suite verifies that the Adaptive Resolver can:")
    print("  1. Match semantically equivalent terms")
    print("  2. Handle natural language queries")
    print("  3. Fall back to substring matching when needed")
    print()
    
    # Check if the index is available
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{INDEX_URL}/health")
            resp.raise_for_status()
            health = resp.json()
            print(f"✅ NANDA Index is healthy: {health}")
    except Exception as exc:
        print(f"❌ ERROR: Cannot connect to NANDA Index at {INDEX_URL}")
        print(f"   Make sure the services are running: ./start_services.sh")
        print(f"   Error: {exc}")
        return 1
    
    # Test cases
    test_cases = [
        {
            "name": "Semantic: composite materials → carbon_fiber",
            "query": "composite materials for lightweight body construction",
            "expected": "supply:carbon_fiber_panels",
        },
        {
            "name": "Semantic: CFRP panels → carbon_fiber",
            "query": "CFRP aerospace-grade panels",
            "expected": "supply:carbon_fiber_panels",
        },
        {
            "name": "Semantic: titanium structural components → titanium_alloy",
            "query": "titanium structural components for suspension",
            "expected": "supply:titanium_alloy",
        },
        {
            "name": "Semantic: aluminum engine parts → aluminum_engine_block",
            "query": "aluminum engine components for powertrain",
            "expected": "supply:aluminum_engine_block",
        },
        {
            "name": "Semantic: beverage containers → aluminum_cans",
            "query": "beverage containers for energy drinks",
            "expected": "supply:aluminum_cans",
        },
    ]
    
    results = []
    for i, test in enumerate(test_cases, 1):
        print(f"\n\n{'#'*70}")
        print(f"TEST {i}/{len(test_cases)}: {test['name']}")
        print(f"{'#'*70}")
        result = await test_resolve_endpoint(test["query"], test["expected"])
        results.append({"name": test["name"], "result": result})
        await asyncio.sleep(0.5)  # Rate limiting
    
    # Test exact match (fast path)
    print(f"\n\n{'#'*70}")
    print(f"TEST {len(test_cases)+1}: Exact skill_hint match (fast path)")
    print(f"{'#'*70}")
    exact_result = await test_substring_fallback("supply:carbon_fiber_panels")
    results.append({"name": "Exact match", "result": exact_result})
    
    # Summary
    print("\n\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(1 for r in results if r["result"]["success"])
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    
    for r in results:
        status = "✅ PASS" if r["result"]["success"] else "❌ FAIL"
        print(f"  {status}: {r['name']}")
    
    if passed == total:
        print("\n🎉 All tests passed! Semantic matching is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the logs above for details.")
        print("\nNote: Semantic matching requires:")
        print("  - OpenAI API key set as OPENAI_API_KEY environment variable")
        print("  - All agents registered with skill_descriptions")
        print("  - Embeddings computed during registration")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
