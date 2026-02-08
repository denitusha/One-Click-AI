"""BOM (Bill of Materials) decomposition for the Procurement Agent.

Takes a high-level user intent (e.g. "Build a high-performance electric vehicle")
and decomposes it into a structured Bill of Materials with ~8 parts across 5 systems.

Uses an LLM call with an automotive template seed, plus a validation pass.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger("procurement.bom")

# ---------------------------------------------------------------------------
# BOM data models
# ---------------------------------------------------------------------------

class BOMPart(BaseModel):
    """A single part in the Bill of Materials."""

    part_id: str = Field(..., description="Short identifier, e.g. 'carbon_fiber_panels'")
    part_name: str = Field(..., description="Human-readable part name")
    description: str = Field(
        default="",
        description="Natural language description of what this part is and what it's used for"
    )
    system: str = Field(
        ..., description="Vehicle system this part belongs to (e.g. 'Chassis', 'Powertrain')"
    )
    quantity: int = Field(..., gt=0, description="Number of units needed")
    skill_query: str = Field(
        ...,
        description="NANDA skill keyword to search for (e.g. 'supply:carbon_fiber_panels')",
    )
    compliance_requirements: list[str] = Field(
        default_factory=list,
        description="Required certifications (e.g. ['ISO 9001', 'IATF 16949'])",
    )
    specs: dict[str, Any] = Field(
        default_factory=dict,
        description="Technical specifications (material, grade, dimensions, etc.)",
    )


class BOM(BaseModel):
    """Complete Bill of Materials for the procurement intent."""

    intent: str = Field(..., description="Original user intent")
    vehicle_type: str = Field(default="", description="Derived vehicle type")
    parts: list[BOMPart] = Field(default_factory=list, description="All parts needed")
    total_parts: int = Field(default=0, description="Total number of unique parts")
    systems: list[str] = Field(default_factory=list, description="Vehicle systems covered")


# ---------------------------------------------------------------------------
# Automotive template seed (fallback / structure hint for the LLM)
# ---------------------------------------------------------------------------

AUTOMOTIVE_TEMPLATE: list[dict[str, Any]] = [
    {
        "part_id": "carbon_fiber_panels",
        "part_name": "Carbon Fiber Body Panels",
        "description": "Lightweight aerospace-grade carbon fiber composite panels for vehicle body construction",
        "system": "Chassis",
        "quantity": 12,
        "skill_query": "supply:carbon_fiber_panels",
        "compliance_requirements": ["ISO 9001", "IATF 16949"],
        "specs": {"material": "carbon fiber composite", "grade": "aerospace", "thickness_mm": 3.5},
    },
    {
        "part_id": "aluminum_chassis",
        "part_name": "Aluminum Chassis Frame",
        "description": "Lightweight aluminum space-frame chassis, CNC machined and welded, ready for suspension attachment",
        "system": "Chassis",
        "quantity": 1,
        "skill_query": "supply:aluminum_chassis",
        "compliance_requirements": ["ISO 9001", "IATF 16949"],
        "specs": {"material": "6061-T6 aluminum alloy", "type": "space-frame", "weight_kg": 45.0},
    },
    {
        "part_id": "titanium_fasteners",
        "part_name": "Titanium Structural Fasteners",
        "description": "High-strength titanium bolts for structural connections in chassis assembly",
        "system": "Chassis",
        "quantity": 500,
        "skill_query": "supply:titanium_fasteners",
        "compliance_requirements": ["ISO 9001"],
        "specs": {"material": "Ti-6Al-4V", "type": "hex_bolt", "size_mm": "M8x30"},
    },
    {
        "part_id": "aluminum_engine_block",
        "part_name": "Aluminum Engine Block",
        "system": "Powertrain",
        "quantity": 1,
        "skill_query": "supply:aluminum_engine_block",
        "compliance_requirements": ["ISO 9001", "IATF 16949"],
        "specs": {"material": "A356 aluminum alloy", "cylinders": 6, "displacement_L": 3.0},
    },
    {
        "part_id": "turbocharger_assembly",
        "part_name": "Twin-Scroll Turbocharger Assembly",
        "system": "Powertrain",
        "quantity": 2,
        "skill_query": "supply:turbocharger_assembly",
        "compliance_requirements": ["ISO 9001"],
        "specs": {"type": "twin-scroll", "max_boost_bar": 1.8, "material": "inconel"},
    },
    {
        "part_id": "pirelli_p_zero",
        "part_name": "Pirelli P Zero High-Performance Tires",
        "description": "P Zero ultra-high performance tires for sports cars and track use",
        "system": "Tires",
        "quantity": 4,
        "skill_query": "supply:pirelli_p_zero",
        "compliance_requirements": ["ISO 9001", "ECE R30", "EU Tire Label"],
        "specs": {"type": "performance", "size": "225/45R18", "speed_index": "Y"},
    },
    {
        "part_id": "brake_system",
        "part_name": "Complete Brake System Assembly",
        "description": "Integrated brake system with master cylinder, calipers, discs, pads, ABS module, and hydraulic lines",
        "system": "Braking",
        "quantity": 1,
        "skill_query": "supply:brake_system",
        "compliance_requirements": ["ISO 9001", "ECE R90", "IATF 16949"],
        "specs": {"type": "complete-system", "master_cylinder_bore_mm": 25, "abs_equipped": True},
    },
    {
        "part_id": "titanium_alloy",
        "part_name": "Titanium Alloy Suspension Arms",
        "system": "Suspension",
        "quantity": 4,
        "skill_query": "supply:titanium_alloy",
        "compliance_requirements": ["ISO 9001"],
        "specs": {"material": "Ti-6Al-4V", "type": "double_wishbone", "weight_kg": 2.8},
    },
]

# ---------------------------------------------------------------------------
# LLM-based BOM decomposition
# ---------------------------------------------------------------------------

BOM_SYSTEM_PROMPT = """\
You are a procurement specialist. Given a user's intent (e.g., "build a Ferrari", 
"supply Red Bull", "create a smartphone"), decompose it into a Bill of Materials (BOM) 
with 6-10 parts appropriate for that specific product or project.

IMPORTANT: Be context-aware! Understand what the user is asking for:
- If they say "Ferrari" or "high-performance vehicle" → generate automotive parts
- If they say "Red Bull" or "energy drink" → generate beverage supply chain parts
- If they say "smartphone" → generate electronics parts
- Adapt your categories to match the actual product type, NOT always to automotive

AVAILABLE SUPPLIERS & PARTS (for automotive/vehicle builds):
- Tires: supply:pirelli_p_zero, supply:pirelli_scorpion, supply:pirelli_cinturato, 
         supply:michelin_pilot_sport, supply:michelin_primacy, supply:michelin_crossclimate
- Brakes: supply:brake_discs, supply:brake_pads_ceramic, supply:brake_pads_semi_metallic, 
          supply:brake_calipers_performance, supply:brake_system
- Chassis: supply:aluminum_chassis, supply:carbon_fiber_panels
- Powertrain: supply:aluminum_engine_block, supply:turbocharger_assembly
- Materials: supply:titanium_alloy, supply:titanium_fasteners, supply:aluminum_engine_block, 
             supply:aluminum_sheet_stock

When generating BOMs for automotive/high-performance vehicles, PREFER using these 
available part IDs from real suppliers. Use generic alternatives only if none match the intent.

Return ONLY a valid JSON array of parts. Each part must have:
- part_id: short snake_case identifier (e.g., 'pirelli_p_zero', 'brake_system')
- part_name: human-readable name (e.g., 'Pirelli P Zero Tires', 'Brake System')
- description: brief natural language description of what this part is and what it's used for
- system: logical category/system for this product (e.g., 'Braking', 'Suspension', 'Tires', etc.)
- quantity: integer > 0
- skill_query: NANDA skill keyword in format "supply:<part_id>" 
  (e.g., "supply:pirelli_p_zero", "supply:brake_system")
- compliance_requirements: list of required certifications (e.g., ['ISO 9001', 'ECE R90'])
- specs: dict of technical specifications relevant to the part

Guidelines:
1. Match parts to available suppliers when possible to maximize supply chain connectivity
2. For automotive builds, prefer tire and brake parts from the available suppliers
3. Generate contextually relevant parts for the specific product type
4. For any part_id you create, generate a corresponding "supply:<part_id>" skill_query
5. Include realistic compliance requirements for each product type

Return ONLY the JSON array, no markdown fences, no explanation."""


async def decompose_bom_llm(intent: str, model: str = "gpt-4o") -> list[dict[str, Any]]:
    """Use LLM to decompose intent into BOM parts.

    Falls back to the automotive template if the LLM call fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — skipping LLM, using template fallback.")
        return AUTOMOTIVE_TEMPLATE

    logger.info("Calling OpenAI (%s) to decompose BOM for: %s", model, intent[:80])
    try:
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": BOM_SYSTEM_PROMPT},
                {"role": "user", "content": f"Vehicle intent: {intent}"},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content or "[]"
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        parts = json.loads(raw)
        if isinstance(parts, list) and len(parts) > 0:
            logger.info("LLM successfully generated %d BOM parts (dynamic decomposition)", len(parts))
            return parts
        else:
            logger.warning("LLM returned empty or invalid parts list, using template fallback.")
    except Exception as exc:
        logger.warning("LLM BOM decomposition failed (%s), using template fallback.", exc)

    return AUTOMOTIVE_TEMPLATE


def validate_bom_parts(raw_parts: list[dict[str, Any]]) -> list[BOMPart]:
    """Validate and normalise raw part dicts into typed BOMPart models.

    Drops parts that don't parse and ensures required fields are present.
    """
    validated: list[BOMPart] = []
    for raw in raw_parts:
        try:
            # Ensure skill_query has the supply: prefix
            sq = raw.get("skill_query", "")
            if sq and not sq.startswith("supply:"):
                raw["skill_query"] = f"supply:{sq}"
            part = BOMPart(**raw)
            validated.append(part)
        except Exception as exc:
            logger.warning("Skipping invalid BOM part %s: %s", raw.get("part_id", "?"), exc)
    return validated


async def decompose_bom(intent: str, model: str = "gpt-4o") -> BOM:
    """Full BOM decomposition pipeline: LLM call → validation → structured BOM.

    Parameters
    ----------
    intent : str
        The user's high-level procurement intent.
    model : str
        OpenAI model to use for decomposition.

    Returns
    -------
    BOM
        A validated, structured Bill of Materials.
    """
    logger.info("Decomposing BOM for intent: %s", intent)

    raw_parts = await decompose_bom_llm(intent, model=model)
    parts = validate_bom_parts(raw_parts)

    if not parts:
        # Last-resort fallback to template
        logger.warning("No valid parts from LLM; using full template fallback.")
        parts = validate_bom_parts(AUTOMOTIVE_TEMPLATE)

    systems = sorted(set(p.system for p in parts))

    bom = BOM(
        intent=intent,
        vehicle_type=_infer_vehicle_type(intent),
        parts=parts,
        total_parts=len(parts),
        systems=systems,
    )
    logger.info(
        "BOM ready: %d parts across %d systems (%s)",
        bom.total_parts,
        len(bom.systems),
        ", ".join(bom.systems),
    )
    return bom


def _infer_vehicle_type(intent: str) -> str:
    """Simple heuristic to extract vehicle type from intent text."""
    intent_lower = intent.lower()
    for vtype in [
        "electric vehicle",
        "sports car",
        "hypercar",
        "supercar",
        "sedan",
        "SUV",
        "truck",
        "race car",
        "luxury vehicle",
        "EV",
    ]:
        if vtype.lower() in intent_lower:
            return vtype.title()
    return "High-Performance Vehicle"
