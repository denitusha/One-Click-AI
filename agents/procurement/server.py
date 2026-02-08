"""Procurement Agent — FastAPI server.

Exposes the procurement agent as an HTTP service that:
- Accepts user intents via ``POST /intent``
- Self-hosts AgentFacts at ``GET /agent-facts``
- Registers itself with the NANDA Index on startup
- Provides health and report endpoints

Port: 6010 (configurable via env ``PORT``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from dotenv import load_dotenv

# Load .env file so OPENAI_API_KEY (and other vars) are available
load_dotenv()

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import (  # noqa: E402
    EVENT_BUS_HTTP_URL,
    INDEX_URL,
    PROCUREMENT_PORT,
)
from shared.schemas import (  # noqa: E402
    AgentFacts,
    Certification,
    Endpoint,
    Evaluation,
    Policy,
    Skill,
)

try:
    from .agent import AGENT_ID, AGENT_NAME, ProcurementState, procurement_graph  # noqa: E402
except ImportError:
    from agents.procurement.agent import AGENT_ID, AGENT_NAME, ProcurementState, procurement_graph  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [procurement] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("procurement.server")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", PROCUREMENT_PORT))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# ---------------------------------------------------------------------------
# AgentFacts (self-hosted metadata)
# ---------------------------------------------------------------------------

AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Procurement",
    description=(
        "LangGraph-based procurement orchestrator that decomposes intents into a BOM, "
        "discovers suppliers via the NANDA Index, performs ZTAA verification, runs "
        "multi-round negotiation (RFQ/QUOTE/COUNTER/ACCEPT), and coordinates logistics."
    ),
    version="1.0.0",
    framework="langgraph",
    jurisdiction="EU",
    provider="OneClickAI",
    skills=[
        Skill(
            id="procurement:orchestration",
            description="End-to-end supply-chain procurement orchestration",
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU", "US"],
        ),
        Skill(
            id="procurement:bom_decomposition",
            description="LLM-powered Bill of Materials decomposition from natural language",
            input_modes=["text/plain", "application/json"],
            output_modes=["application/json"],
        ),
        Skill(
            id="procurement:negotiation",
            description="Multi-round RFQ negotiation with scoring and counter-offers",
            input_modes=["application/json"],
            output_modes=["application/json"],
        ),
    ],
    endpoints=[
        Endpoint(path="/intent", method="POST", description="Submit procurement intent"),
        Endpoint(path="/agent-facts", method="GET", description="Self-hosted AgentFacts"),
        Endpoint(path="/health", method="GET", description="Health check"),
        Endpoint(path="/report", method="GET", description="Latest coordination report"),
    ],
    evaluations=[
        Evaluation(
            evaluator="self",
            score=0.95,
            metric="reliability",
            details={"note": "Orchestrator uptime target 99.5%"},
        ),
    ],
    certifications=[
        Certification(name="ISO 27001", issuer="Internal Audit"),
    ],
    policies=[
        Policy(
            name="ztaa_verification",
            description="All suppliers must pass ZTAA checks before negotiation",
            value=True,
        ),
        Policy(
            name="counter_offer_discount",
            description="Counter-offer discount percentage",
            value=0.10,
        ),
    ],
    reliability_score=0.95,
    esg_rating="A",
    base_url=BASE_URL,
)

# ---------------------------------------------------------------------------
# State: latest report (for GET /report)
# ---------------------------------------------------------------------------

_latest_report: dict[str, Any] | None = None
_running = False


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IntentRequest(BaseModel):
    """Body for ``POST /intent``."""
    intent: str = Field(..., description="Natural-language procurement intent")
    run_id: str = Field(default="", description="Dashboard-generated UUID for tab isolation")


class IntentResponse(BaseModel):
    status: str = "accepted"
    message: str = ""
    run_id: str = ""
    report: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# NANDA Index registration
# ---------------------------------------------------------------------------

async def _register_with_index() -> None:
    """Register this agent with the NANDA Index."""
    payload = {
        "agent_id": AGENT_ID,
        "agent_name": AGENT_NAME,
        "facts_url": f"{BASE_URL}/agent-facts",
        "skills": [s.id for s in AGENT_FACTS.skills],
        "skill_descriptions": {s.id: s.description for s in AGENT_FACTS.skills},
        "region": "EU",
        "ttl": 3600,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{INDEX_URL}/register", json=payload)
            resp.raise_for_status()
            logger.info("Registered with NANDA Index: %s", resp.json())
    except Exception as exc:
        logger.warning("Failed to register with NANDA Index: %s", exc)


async def _emit_startup_event() -> None:
    """Notify the Event Bus that this agent is online."""
    event = {
        "event_type": "AGENT_REGISTERED",
        "agent_id": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "agent_name": AGENT_NAME,
            "framework": "langgraph",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{EVENT_BUS_HTTP_URL}/event", json=event)
    except Exception:
        logger.debug("Event Bus not reachable on startup (non-fatal).")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Procurement Agent starting on port %d ...", PORT)
    # Register with NANDA Index and Event Bus (best-effort)
    await _register_with_index()
    await _emit_startup_event()
    logger.info("Procurement Agent ready at %s", BASE_URL)
    yield
    logger.info("Procurement Agent shutting down.")


app = FastAPI(
    title="OneClickAI Procurement Agent",
    description="LangGraph-powered procurement orchestrator for supply-chain coordination.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/intent", response_model=IntentResponse)
async def submit_intent(body: IntentRequest):
    """Submit a natural-language procurement intent.

    Triggers the full coordination cascade:
    DECOMPOSE → DISCOVER → VERIFY → NEGOTIATE → PLAN
    """
    global _latest_report, _running

    if _running:
        raise HTTPException(
            status_code=409,
            detail="A procurement cascade is already running. Please wait.",
        )

    logger.info("Received intent: %s", body.intent)
    _running = True

    try:
        # Run the LangGraph procurement graph
        initial_state: ProcurementState = {
            "intent": body.intent,
            "run_id": body.run_id,
            "events": [],
            "errors": [],
        }
        result = await procurement_graph.ainvoke(initial_state)

        report = result.get("report", {})
        _latest_report = report

        return IntentResponse(
            status="completed",
            message="Procurement cascade completed successfully.",
            run_id=body.run_id,
            report=report,
        )
    except Exception as exc:
        logger.exception("Procurement cascade failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Procurement cascade failed: {exc}",
        )
    finally:
        _running = False


@app.get("/agent-facts")
async def agent_facts():
    """Self-hosted AgentFacts endpoint (NANDA protocol)."""
    return AGENT_FACTS.model_dump(mode="json")


@app.get("/report")
async def get_report():
    """Return the latest Network Coordination Report."""
    if _latest_report is None:
        raise HTTPException(
            status_code=404,
            detail="No report available yet. Submit an intent first.",
        )
    return _latest_report


@app.get("/health")
async def health():
    """Liveness / readiness probe."""
    return {
        "status": "ok",
        "service": "procurement-agent",
        "framework": "langgraph",
        "agent_id": AGENT_ID,
        "running_cascade": _running,
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
