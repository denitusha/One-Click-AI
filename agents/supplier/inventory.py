"""Simulated inventory and pricing data for all supplier agents.

Each supplier has a catalogue of parts with stock levels, base prices,
floor prices (minimum acceptable during negotiation), lead times, and
certifications.

Suppliers
---------
- **A** (CrewAI) — carbon fibre components
- **B** (Custom Python) — titanium alloys, fasteners, ceramic brakes
- **C** (LangChain) — powertrain components
- **D** (CrewAI) — aluminum & materials (multi-industry)
- **F** (CrewAI) — Pirelli tires (performance/racing)
- **G** (LangChain) — Michelin tires (touring/all-season)
- **H** (Custom Python) — brake components & systems
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
# Supplier D — Aluminum & Materials (CrewAI · port 6005)
# Skills: supply:aluminum_cans, supply:aluminum_engine_block, supply:aluminum_sheet_stock
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_D_CATALOG: dict[str, PartInfo] = {
    "aluminum_cans": PartInfo(
        part_id="aluminum_cans",
        part_name="Aluminum Beverage Cans",
        description="Food-grade aluminum beverage cans for beverages, available in 330ml and 500ml sizes",
        base_price=0.20,
        stock_quantity=50000,
        lead_time_days=4,
        shipping_origin="Amsterdam, Netherlands",
        certifications=["FDA", "ISO 22000", "REACH"],
        min_order_qty=1000,
        floor_price_pct=0.85,
        specs={
            "material": "food-grade aluminum",
            "sizes_ml": [330, 500],
            "weight_g_per_can": 15.5,
            "coating": "food-safe epoxy",
        },
    ),
    "aluminum_engine_block": PartInfo(
        part_id="aluminum_engine_block",
        part_name="Aluminum Engine Block",
        description="A356 aluminum alloy engine block, 6-cylinder, 3.0L displacement",
        base_price=3200.00,
        stock_quantity=30,
        lead_time_days=35,
        shipping_origin="Amsterdam, Netherlands",
        certifications=["ISO 9001", "IATF 16949"],
        min_order_qty=1,
        floor_price_pct=0.85,
        specs={"material": "A356 aluminum alloy", "cylinders": 6, "displacement_L": 3.0},
    ),
    "aluminum_sheet_stock": PartInfo(
        part_id="aluminum_sheet_stock",
        part_name="Aluminum Sheet Stock",
        description="Raw aluminum sheets in various grades and thicknesses for manufacturing applications",
        base_price=15.00,
        stock_quantity=10000,
        lead_time_days=8,
        shipping_origin="Amsterdam, Netherlands",
        certifications=["ISO 9001", "REACH"],
        min_order_qty=100,
        floor_price_pct=0.80,
        specs={
            "material": "aluminum alloy",
            "grades": ["1050", "3003", "5052", "6061"],
            "thickness_mm": [0.5, 1.0, 2.0, 3.0, 5.0],
            "width_m": 1.2,
            "length_m": 2.4,
        },
    ),
    "aluminum_chassis": PartInfo(
        part_id="aluminum_chassis",
        part_name="Aluminum Chassis Frame",
        description="Lightweight aluminum space-frame chassis, CNC machined and welded, ready for suspension attachment",
        base_price=4500.00,
        stock_quantity=80,
        lead_time_days=25,
        shipping_origin="Amsterdam, Netherlands",
        certifications=["ISO 9001", "IATF 16949"],
        min_order_qty=1,
        floor_price_pct=0.83,
        specs={
            "material": "6061-T6 aluminum alloy",
            "type": "space-frame",
            "weight_kg": 45.0,
            "wheelbase_mm": 2750,
            "track_width_mm": 1600,
            "finish": "anodized",
        },
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# Supplier F — Pirelli Tires (CrewAI · port 6007)
# Skills: supply:pirelli_p_zero, supply:pirelli_scorpion, supply:pirelli_cinturato
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_F_CATALOG: dict[str, PartInfo] = {
    "pirelli_p_zero": PartInfo(
        part_id="pirelli_p_zero",
        part_name="Pirelli P Zero High-Performance Tires",
        description="P Zero ultra-high performance tires for sports cars and track use",
        base_price=350.00,
        stock_quantity=400,
        lead_time_days=10,
        shipping_origin="Milan, Italy",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.82,
        specs={
            "type": "performance",
            "size": "225/45R18",
            "speed_index": "Y",
            "load_index": "95",
            "wet_grip": "A",
        },
    ),
    "pirelli_scorpion": PartInfo(
        part_id="pirelli_scorpion",
        part_name="Pirelli Scorpion SUV Tires",
        description="Scorpion tires designed for SUVs and crossover vehicles",
        base_price=280.00,
        stock_quantity=300,
        lead_time_days=12,
        shipping_origin="Milan, Italy",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.83,
        specs={
            "type": "suv",
            "size": "255/55R18",
            "speed_index": "H",
            "load_index": "109",
            "wet_grip": "B",
        },
    ),
    "pirelli_cinturato": PartInfo(
        part_id="pirelli_cinturato",
        part_name="Pirelli Cinturato Eco-Performance Tires",
        description="Cinturato eco-performance tires with excellent fuel efficiency",
        base_price=180.00,
        stock_quantity=600,
        lead_time_days=7,
        shipping_origin="Milan, Italy",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.85,
        specs={
            "type": "eco-performance",
            "size": "205/55R16",
            "speed_index": "V",
            "load_index": "91",
            "wet_grip": "B",
            "fuel_efficiency": "A",
        },
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# Supplier G — Michelin Tires (LangChain · port 6008)
# Skills: supply:michelin_pilot_sport, supply:michelin_primacy, supply:michelin_crossclimate
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_G_CATALOG: dict[str, PartInfo] = {
    "michelin_pilot_sport": PartInfo(
        part_id="michelin_pilot_sport",
        part_name="Michelin Pilot Sport 4S Ultra-High Performance Tires",
        description="Pilot Sport 4S premium performance tires for high-end sports cars",
        base_price=320.00,
        stock_quantity=350,
        lead_time_days=10,
        shipping_origin="Lyon, France",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.83,
        specs={
            "type": "performance",
            "size": "235/40R18",
            "speed_index": "Y",
            "load_index": "95",
            "wet_grip": "A",
        },
    ),
    "michelin_primacy": PartInfo(
        part_id="michelin_primacy",
        part_name="Michelin Primacy 4 Touring Tires",
        description="Primacy 4 touring tires for comfortable long-distance driving",
        base_price=200.00,
        stock_quantity=500,
        lead_time_days=8,
        shipping_origin="Lyon, France",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.85,
        specs={
            "type": "touring",
            "size": "215/55R17",
            "speed_index": "V",
            "load_index": "98",
            "wet_grip": "A",
            "rolling_resistance": "B",
        },
    ),
    "michelin_crossclimate": PartInfo(
        part_id="michelin_crossclimate",
        part_name="Michelin CrossClimate All-Season Tires",
        description="CrossClimate all-season tires for year-round versatility",
        base_price=220.00,
        stock_quantity=450,
        lead_time_days=9,
        shipping_origin="Lyon, France",
        certifications=["ISO 9001", "ECE R30", "EU Tire Label"],
        min_order_qty=4,
        floor_price_pct=0.84,
        specs={
            "type": "all-season",
            "size": "225/50R17",
            "speed_index": "V",
            "load_index": "98",
            "wet_grip": "A",
            "winter_grip": "3PMSF",
        },
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# Supplier H — Brake Components (Custom Python · port 6009)
# Skills: supply:brake_discs, supply:brake_pads_ceramic, supply:brake_pads_semi_metallic,
#         supply:brake_calipers_performance
# ═══════════════════════════════════════════════════════════════════════════

SUPPLIER_H_CATALOG: dict[str, PartInfo] = {
    "brake_discs": PartInfo(
        part_id="brake_discs",
        part_name="Ventilated Brake Discs",
        description="High-performance ventilated brake discs with cast iron construction",
        base_price=120.00,
        stock_quantity=800,
        lead_time_days=7,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=2,
        floor_price_pct=0.85,
        specs={
            "material": "cast iron",
            "type": "ventilated",
            "diameter_mm": 330,
            "thickness_mm": 30,
            "weight_kg": 3.2,
        },
    ),
    "brake_pads_ceramic": PartInfo(
        part_id="brake_pads_ceramic",
        part_name="Ceramic Brake Pads",
        description="Low-dust ceramic brake pads for street and performance driving",
        base_price=85.00,
        stock_quantity=1000,
        lead_time_days=5,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=4,
        floor_price_pct=0.80,
        specs={
            "material": "ceramic",
            "dust_level": "low",
            "friction_coefficient": 0.45,
            "temperature_range_c": "-40 to 400",
        },
    ),
    "brake_pads_semi_metallic": PartInfo(
        part_id="brake_pads_semi_metallic",
        part_name="Semi-Metallic Brake Pads",
        description="High-performance semi-metallic brake pads for aggressive driving",
        base_price=55.00,
        stock_quantity=1200,
        lead_time_days=4,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=4,
        floor_price_pct=0.82,
        specs={
            "material": "semi-metallic",
            "dust_level": "high",
            "friction_coefficient": 0.55,
            "temperature_range_c": "-40 to 600",
        },
    ),
    "brake_calipers_performance": PartInfo(
        part_id="brake_calipers_performance",
        part_name="Performance 4-Piston Brake Calipers",
        description="High-performance aluminum 4-piston brake calipers for track use",
        base_price=450.00,
        stock_quantity=200,
        lead_time_days=14,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=1,
        floor_price_pct=0.80,
        specs={
            "material": "aluminum",
            "pistons": 4,
            "bore_diameter_mm": 38,
            "rotor_diameter_mm": 330,
            "weight_kg": 2.1,
        },
    ),
    "brake_system": PartInfo(
        part_id="brake_system",
        part_name="Complete Brake System Assembly",
        description="Integrated brake system with master cylinder, calipers, discs, pads, ABS module, and hydraulic lines, ready for vehicle integration",
        base_price=3200.00,
        stock_quantity=120,
        lead_time_days=20,
        shipping_origin="Stuttgart, Germany",
        certifications=["ISO 9001", "ECE R90", "IATF 16949"],
        min_order_qty=1,
        floor_price_pct=0.81,
        specs={
            "type": "complete-system",
            "master_cylinder_bore_mm": 25,
            "num_calipers": 4,
            "num_discs": 2,
            "abs_equipped": True,
            "max_brake_force_kn": 45.0,
            "weight_kg": 28.5,
            "integration": "plug-and-play",
        },
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# All catalogues indexed by supplier key
# ═══════════════════════════════════════════════════════════════════════════

ALL_CATALOGS: dict[str, dict[str, PartInfo]] = {
    "supplier_a": SUPPLIER_A_CATALOG,
    "supplier_b": SUPPLIER_B_CATALOG,
    "supplier_c": SUPPLIER_C_CATALOG,
    "supplier_d": SUPPLIER_D_CATALOG,
    "supplier_f": SUPPLIER_F_CATALOG,
    "supplier_g": SUPPLIER_G_CATALOG,
    "supplier_h": SUPPLIER_H_CATALOG,
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
