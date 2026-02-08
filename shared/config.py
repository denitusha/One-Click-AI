"""Ports, URLs, and constants shared across all services."""

# ---------------------------------------------------------------------------
# NANDA Lean Index
# ---------------------------------------------------------------------------
INDEX_HOST = "localhost"
INDEX_PORT = 6900
INDEX_URL = f"http://{INDEX_HOST}:{INDEX_PORT}"

# ---------------------------------------------------------------------------
# Agent ports
# ---------------------------------------------------------------------------
PROCUREMENT_PORT = 6010

SUPPLIER_PORTS: dict[str, int] = {
    "supplier_a": 6001,  # CrewAI - Carbon Fiber
    "supplier_b": 6002,  # Custom Python - Titanium & Ceramics
    "supplier_c": 6003,  # LangChain - Powertrain
    "supplier_d": 6005,  # CrewAI - Aluminum & Materials
    "supplier_f": 6007,  # CrewAI - Pirelli Tires
    "supplier_g": 6008,  # LangChain - Michelin Tires
    "supplier_h": 6009,  # Custom Python - Brakes
}

LOGISTICS_PORT = 6004

# ---------------------------------------------------------------------------
# Event Bus (WebSocket relay for the dashboard)
# ---------------------------------------------------------------------------
EVENT_BUS_PORT = 6020
EVENT_BUS_HTTP_URL = f"http://localhost:{EVENT_BUS_PORT}"
EVENT_BUS_WS_URL = f"ws://localhost:{EVENT_BUS_PORT}/ws"

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
OPENAI_MODEL = "gpt-4o"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_CURRENCY = "EUR"
DEFAULT_TTL_SECONDS = 3600  # 1 hour AgentAddr TTL
