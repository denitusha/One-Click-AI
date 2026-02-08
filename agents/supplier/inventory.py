"""Simulated inventory and pricing data for all supplier agents.

Each supplier has a catalogue of parts with stock levels, base prices,
floor prices (minimum acceptable during negotiation), lead times, and
certifications.

Suppliers
---------
- **A** (CrewAI) — carbon fibre components
- **B** (Custom Python) — titanium alloys, fasteners, ceramic brakes
- **C** (LangChain) — powertrain components
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Part data model
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PartInfo:
    """Inventory record for a single part."""

    part_id: str
    part_name: str
    description: str
    base_price: float  # EUR per unit
    currency: str = "EUR"
    stock_quantity: int = 0
    lead_time_days: int = 7
    shipping_origin: str = ""
    certifications: list[str] = field(default_factory=list)
    min_order_qty: int = 1
    floor_price_pct: float = 0.80  # floor = base_price × pct
    specs: dict[str, Any] = field(default_factory=dict)

    @property
    def floor_price(self) -> float:
        """Minimum acceptable price per unit."""
        return round(self.base_price * self.floor_price_pct, 2)


# ═══════════════════════════════════════════════════════════════════════════
# Supplier A — Carbon Fiber Specialists (CrewAI · port 6001)
# Skills: supply:carbon_fiber_panels, supply:carbon_fiber_raw
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_A_CATALOG: dict[str, PartInfo] = {
    "carbon_fiber_panels": PartInfo(
        part_id="carbon_fiber_panels",
        part_name="Carbon Fiber Body Panels",
        description="High-strength CFRP body panels for automotive applications, aerospace-grade",
        base_price=450.00,
        stock_quantity=200,
        lead_time_days=14,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "IATF 16949", "REACH"],
        min_order_qty=4,
        floor_price_pct=0.80,
        specs={
            "material": "carbon fiber composite",
            "grade": "aerospace",
            "thickness_mm": 3.5,
            "weight_kg_per_panel": 1.8,
        },
    ),
    "carbon_fiber_raw": PartInfo(
        part_id="carbon_fiber_raw",
        part_name="Carbon Fiber Raw Sheet Stock",
        description="3K twill weave carbon fiber sheets for custom fabrication and interior trim",
        base_price=280.00,
        stock_quantity=500,
        lead_time_days=7,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "REACH"],
        min_order_qty=10,
        floor_price_pct=0.80,
        specs={
            "material": "3K twill weave carbon fiber",
            "thickness_mm": 1.5,
            "size_m2": 1.2,
            "weight_kg_per_sheet": 0.6,
        },
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# Supplier B — Precision Metals & Ceramics (Custom Python · port 6002)
# Skills: supply:titanium_alloy, supply:titanium_fasteners,
#         supply:ceramic_brake_calipers
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_B_CATALOG: dict[str, PartInfo] = {
    "titanium_alloy": PartInfo(
        part_id="titanium_alloy",
        part_name="Titanium Alloy Suspension Arms",
        description="Ti-6Al-4V double wishbone suspension arms, CNC machined",
        base_price=820.00,
        stock_quantity=80,
        lead_time_days=21,
        shipping_origin="Munich, Germany",
        certifications=["ISO 9001", "NADCAP"],
        min_order_qty=2,
        floor_price_pct=0.85,
        specs={"material": "Ti-6Al-4V", "type": "double_wishbone", "weight_kg": 2.8},
    ),
    "titanium_fasteners": PartInfo(
        part_id="titanium_fasteners",
        part_name="Titanium Structural Fasteners",
        description="High-strength titanium hex bolts for structural applications",
        base_price=12.50,
        stock_quantity=5000,
        lead_time_days=5,
        shipping_origin="Munich, Germany",
        certifications=["ISO 9001", "DIN EN ISO 3506"],
        min_order_qty=50,
        floor_price_pct=0.90,
        specs={"material": "Ti-6Al-4V", "type": "hex_bolt", "size_mm": "M8x30"},
    ),
    "ceramic_brake_calipers": PartInfo(
        part_id="ceramic_brake_calipers",
        part_name="Ceramic Brake Calipers",
        description="Carbon-ceramic composite brake calipers, 6-piston, track-ready",
        base_price=1850.00,
        stock_quantity=40,
        lead_time_days=28,
        shipping_origin="Munich, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=2,
        floor_price_pct=0.82,
        specs={"material": "carbon-ceramic composite", "pistons": 6, "diameter_mm": 400},
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# Supplier C — Powertrain Components (LangChain · port 6003)
# Skills: supply:aluminum_engine_block, supply:turbocharger_assembly
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_C_CATALOG: dict[str, PartInfo] = {
    "aluminum_engine_block": PartInfo(
        part_id="aluminum_engine_block",
        part_name="Aluminum Engine Block",
        description="A356 aluminum alloy engine block, 6-cylinder, 3.0L displacement",
        base_price=3200.00,
        stock_quantity=25,
        lead_time_days=35,
        shipping_origin="Milan, Italy",
        certifications=["ISO 9001", "IATF 16949"],
        min_order_qty=1,
        floor_price_pct=0.85,
        specs={"material": "A356 aluminum alloy", "cylinders": 6, "displacement_L": 3.0},
    ),
    "turbocharger_assembly": PartInfo(
        part_id="turbocharger_assembly",
        part_name="Twin-Scroll Turbocharger Assembly",
        description="High-performance twin-scroll turbocharger with Inconel turbine wheel",
        base_price=2100.00,
        stock_quantity=50,
        lead_time_days=18,
        shipping_origin="Milan, Italy",
        certifications=["ISO 9001"],
        min_order_qty=1,
        floor_price_pct=0.80,
        specs={"type": "twin-scroll", "max_boost_bar": 1.8, "material": "inconel"},
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# All catalogues indexed by supplier key
# ═══════════════════════════════════════════════════════════════════════════

ALL_CATALOGS: dict[str, dict[str, PartInfo]] = {
    "supplier_a": SUPPLIER_A_CATALOG,
    "supplier_b": SUPPLIER_B_CATALOG,
    "supplier_c": SUPPLIER_C_CATALOG,
}


# ═══════════════════════════════════════════════════════════════════════════
# Lookup helpers
# ═══════════════════════════════════════════════════════════════════════════

def get_catalog(supplier_key: str) -> dict[str, PartInfo]:
    """Return the catalogue for a given supplier key."""
    return ALL_CATALOGS.get(supplier_key, {})


def lookup_part(supplier_key: str, part_query: str) -> PartInfo | None:
    """Look up a part in a supplier's catalogue.

    Supports:
    - Exact match by ``part_id`` (e.g. ``"carbon_fiber_panels"``)
    - Prefixed match (e.g. ``"supply:carbon_fiber_panels"``)
    - Fuzzy keyword match against ``part_id`` and ``part_name``
    """
    catalog = get_catalog(supplier_key)

    # Exact match
    if part_query in catalog:
        return catalog[part_query]

    # Strip "supply:" prefix
    clean = part_query.replace("supply:", "").strip().lower()
    if clean in catalog:
        return catalog[clean]

    # Fuzzy: check if query keywords appear in part_id or part_name
    for part_id, info in catalog.items():
        if clean in part_id.lower() or clean in info.part_name.lower():
            return info

    return None


def compute_volume_discount(quantity: int) -> float:
    """Return a discount fraction based on order quantity."""
    if quantity >= 100:
        return 0.05  # 5 %
    if quantity >= 50:
        return 0.03  # 3 %
    if quantity >= 20:
        return 0.02  # 2 %
    return 0.0


def evaluate_counter_offer(
    supplier_key: str,
    part_query: str,
    target_price: float,
) -> dict[str, Any]:
    """Evaluate a counter-offer against the part's floor price.

    Returns
    -------
    dict with keys ``accepted`` (bool), ``revised_price`` (float),
    ``floor_price`` (float), ``reason`` (str).
    """
    part = lookup_part(supplier_key, part_query)
    if part is None:
        return {
            "accepted": False,
            "revised_price": 0.0,
            "floor_price": 0.0,
            "reason": f"Part '{part_query}' not found in catalogue",
        }

    floor = part.floor_price

    if target_price >= floor:
        # Accept at the target (or floor, whichever is higher)
        revised = max(target_price, floor)
        return {
            "accepted": True,
            "revised_price": round(revised, 2),
            "floor_price": floor,
            "reason": (
                f"Accepted: target €{target_price:.2f} is at or above "
                f"floor €{floor:.2f} ({part.floor_price_pct * 100:.0f}% of base €{part.base_price:.2f})"
            ),
        }

    return {
        "accepted": False,
        "revised_price": 0.0,
        "floor_price": floor,
        "reason": (
            f"Rejected: target €{target_price:.2f} is below floor €{floor:.2f} "
            f"({part.floor_price_pct * 100:.0f}% of base €{part.base_price:.2f})"
        ),
    }
