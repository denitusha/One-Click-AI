"""Centralized configuration for all services."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

# --- Service Ports ---
REGISTRY_PORT = 8000
COORDINATOR_PORT = 8001
PROCUREMENT_PORT = 8010
SUPPLIER1_PORT = 8011
SUPPLIER2_PORT = 8012
MANUFACTURER_PORT = 8013
LOGISTICS_PORT = 8014
COMPLIANCE_PORT = 8015
RESOLVER_PORT = 8016

# --- Service URLs (Docker-friendly names with localhost fallback) ---
_HOST = os.getenv("SERVICE_HOST", "localhost")

REGISTRY_URL = os.getenv("REGISTRY_URL", f"http://{_HOST}:{REGISTRY_PORT}")
RESOLVER_URL = os.getenv("RESOLVER_URL", f"http://{_HOST}:{RESOLVER_PORT}")
COORDINATOR_URL = os.getenv("COORDINATOR_URL", f"http://{_HOST}:{COORDINATOR_PORT}")
PROCUREMENT_URL = os.getenv("PROCUREMENT_URL", f"http://{_HOST}:{PROCUREMENT_PORT}")
SUPPLIER1_URL = os.getenv("SUPPLIER1_URL", f"http://{_HOST}:{SUPPLIER1_PORT}")
SUPPLIER2_URL = os.getenv("SUPPLIER2_URL", f"http://{_HOST}:{SUPPLIER2_PORT}")
MANUFACTURER_URL = os.getenv("MANUFACTURER_URL", f"http://{_HOST}:{MANUFACTURER_PORT}")
LOGISTICS_URL = os.getenv("LOGISTICS_URL", f"http://{_HOST}:{LOGISTICS_PORT}")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", f"http://{_HOST}:{COMPLIANCE_PORT}")

COORDINATOR_WS_URL = os.getenv(
    "COORDINATOR_WS_URL", f"ws://{_HOST}:{COORDINATOR_PORT}/ws"
)
