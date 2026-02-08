"""NANDA Lean Index -- Customised for the OneClickAI Supply-Chain Agent Network.

Forked from projnanda/nanda-index and rewritten on top of **FastAPI** so that
it integrates natively with the project's Pydantic v2 schemas (``AgentAddr``).

Endpoints
---------
POST /register          Register (or re-register / heartbeat) an agent.
GET  /search            Search agents by skill keywords and/or region.
GET  /lookup/{agent_id} Retrieve a single AgentAddr record.
GET  /list              List all registered agents.
GET  /health            Health-check (includes Mongo connectivity flag).
GET  /stats             Basic registry statistics.
DELETE /agents/{agent_id}  Remove an agent from the registry.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so ``shared`` is importable.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.schemas import AgentAddr  # noqa: E402
from shared.config import INDEX_PORT  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [nanda-index] %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nanda-index")

# ---------------------------------------------------------------------------
# MongoDB (optional -- falls back to in-memory dict)
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGODB_DB", "nanda_index")

USE_MONGO = False
_mongo_col = None  # will hold the pymongo Collection if available

try:
    from pymongo import MongoClient  # type: ignore[import-untyped]

    _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")
    _db = _client[MONGO_DB]
    _mongo_col = _db["agents"]
    # Create indexes for fast skill / region queries
    _mongo_col.create_index("agent_id", unique=True)
    _mongo_col.create_index("skills")
    _mongo_col.create_index("region")
    USE_MONGO = True
    log.info("Connected to MongoDB at %s (db=%s)", MONGO_URI, MONGO_DB)
except Exception as exc:
    log.warning("MongoDB unavailable (%s) -- running in-memory mode.", exc)
    USE_MONGO = False

# ---------------------------------------------------------------------------
# In-memory registry (also serves as cache when Mongo is available)
# ---------------------------------------------------------------------------
_registry: dict[str, dict[str, Any]] = {}


def _agent_to_dict(agent: AgentAddr) -> dict[str, Any]:
    """Serialise an AgentAddr to a plain dict suitable for Mongo / cache."""
    d = agent.model_dump(mode="json")
    # Ensure ``registered_at`` is a string for JSON serialisation
    if isinstance(d.get("registered_at"), datetime):
        d["registered_at"] = d["registered_at"].isoformat()
    return d


def _dict_to_agent(d: dict[str, Any]) -> AgentAddr:
    """Reconstruct an AgentAddr from a stored dict."""
    # Drop Mongo's internal ``_id`` if present
    d = {k: v for k, v in d.items() if k != "_id"}
    return AgentAddr(**d)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_from_mongo() -> None:
    """Hydrate the in-memory cache from MongoDB on startup."""
    if not USE_MONGO or _mongo_col is None:
        return
    try:
        for doc in _mongo_col.find():
            aid = doc.get("agent_id")
            if aid:
                _registry[aid] = {k: v for k, v in doc.items() if k != "_id"}
        log.info("Loaded %d agents from MongoDB.", len(_registry))
    except Exception as exc:
        log.error("Failed to load agents from MongoDB: %s", exc)


def _save_agent(agent_dict: dict[str, Any]) -> None:
    """Upsert a single agent record into MongoDB (no-op if Mongo unavailable)."""
    if not USE_MONGO or _mongo_col is None:
        return
    try:
        _mongo_col.update_one(
            {"agent_id": agent_dict["agent_id"]},
            {"$set": agent_dict},
            upsert=True,
        )
    except Exception as exc:
        log.error("MongoDB upsert failed for %s: %s", agent_dict.get("agent_id"), exc)


def _delete_agent_from_mongo(agent_id: str) -> None:
    """Remove an agent from MongoDB."""
    if not USE_MONGO or _mongo_col is None:
        return
    try:
        _mongo_col.delete_one({"agent_id": agent_id})
    except Exception as exc:
        log.error("MongoDB delete failed for %s: %s", agent_id, exc)


def _clear_mongo() -> None:
    """Drop all agent records from MongoDB on fresh startup.

    Prevents stale entries from previous runs (which may have used different
    agent IDs or names) from polluting search results and creating duplicate
    nodes on the dashboard.
    """
    if not USE_MONGO or _mongo_col is None:
        return
    try:
        result = _mongo_col.delete_many({})
        log.info("Cleared %d stale agents from MongoDB.", result.deleted_count)
    except Exception as exc:
        log.error("Failed to clear MongoDB: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI application (with lifespan)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    _clear_mongo()          # purge stale entries from previous runs
    _registry.clear()       # also reset in-memory cache
    _load_from_mongo()      # will be empty after the purge
    log.info(
        "NANDA Index ready  --  port=%s  mongo=%s  agents_loaded=%d",
        INDEX_PORT,
        USE_MONGO,
        len(_registry),
    )
    yield  # application runs here
    log.info("NANDA Index shutting down.")


app = FastAPI(
    title="NANDA Lean Index",
    description="Supply-chain agent discovery registry (forked from projnanda/nanda-index).",
    version="1.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Body accepted by ``POST /register``.

    Matches the ``AgentAddr`` schema with all fields except ``registered_at``
    (which is set server-side).
    """

    agent_id: str
    agent_name: str
    facts_url: str
    skills: list[str] = Field(default_factory=list)
    region: str | None = None
    ttl: int = 3600
    signature: str | None = None


class RegisterResponse(BaseModel):
    status: str = "ok"
    agent_id: str
    message: str = ""


class StatsResponse(BaseModel):
    total_agents: int
    agents_by_region: dict[str, int]
    unique_skills: int
    mongo_connected: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/register", response_model=RegisterResponse)
async def register_agent(body: RegisterRequest):
    """Register or re-register an agent (heartbeat).

    Stores a lean ``AgentAddr`` record.  If the agent_id already exists the
    record is updated (upsert semantics).
    """
    agent = AgentAddr(
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        facts_url=body.facts_url,
        skills=body.skills,
        region=body.region,
        ttl=body.ttl,
        signature=body.signature,
        registered_at=datetime.now(timezone.utc),
    )
    agent_dict = _agent_to_dict(agent)

    # Upsert into cache + Mongo
    _registry[agent.agent_id] = agent_dict
    _save_agent(agent_dict)

    verb = "updated" if body.agent_id in _registry else "registered"
    log.info("Agent %s %s  (skills=%s, region=%s)", body.agent_id, verb, body.skills, body.region)

    return RegisterResponse(
        agent_id=agent.agent_id,
        message=f"Agent {agent.agent_id} {verb} successfully.",
    )


@app.get("/search")
async def search_agents(
    skills: str | None = Query(
        default=None,
        description="Comma-separated skill keywords to match (substring match). E.g. 'carbon_fiber,titanium'",
    ),
    region: str | None = Query(
        default=None,
        description="Region tag filter (exact, case-insensitive). E.g. 'EU'",
    ),
    q: str | None = Query(
        default=None,
        description="Free-text substring search across agent_id and agent_name.",
    ),
):
    """Search the registry by skill keywords, region, and/or free-text query.

    Filtering logic
    ---------------
    - **skills**: If provided, an agent must have *at least one* skill whose ID
      contains one of the supplied keywords (substring match, case-insensitive).
    - **region**: If provided, the agent's ``region`` must match (case-insensitive).
    - **q**: If provided, the agent_id or agent_name must contain the substring.

    All filters are AND-combined.  Returns a list of ``AgentAddr`` dicts.
    """
    skill_keywords: list[str] = []
    if skills:
        skill_keywords = [kw.strip().lower() for kw in skills.split(",") if kw.strip()]

    region_filter = region.strip().upper() if region else None
    q_lower = q.strip().lower() if q else None

    results: list[dict[str, Any]] = []

    for agent_dict in _registry.values():
        # --- skill filter ---
        if skill_keywords:
            agent_skills = [s.lower() for s in agent_dict.get("skills", [])]
            # Agent must match at least one keyword
            if not any(
                any(kw in skill for skill in agent_skills)
                for kw in skill_keywords
            ):
                continue

        # --- region filter ---
        if region_filter:
            agent_region = (agent_dict.get("region") or "").upper()
            if agent_region != region_filter:
                continue

        # --- free-text filter ---
        if q_lower:
            aid = agent_dict.get("agent_id", "").lower()
            aname = agent_dict.get("agent_name", "").lower()
            if q_lower not in aid and q_lower not in aname:
                continue

        results.append(agent_dict)

    return results


@app.get("/lookup/{agent_id}")
async def lookup_agent(agent_id: str):
    """Return the ``AgentAddr`` record for a single agent."""
    agent_dict = _registry.get(agent_id)
    if not agent_dict:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    return agent_dict


@app.get("/list")
async def list_agents():
    """Return all registered ``AgentAddr`` records."""
    return list(_registry.values())


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Remove an agent from the registry."""
    if agent_id not in _registry:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    del _registry[agent_id]
    _delete_agent_from_mongo(agent_id)
    log.info("Agent %s deleted.", agent_id)
    return {"status": "deleted", "agent_id": agent_id}


@app.get("/health")
async def health():
    """Liveness / readiness probe."""
    mongo_ok = False
    if USE_MONGO:
        try:
            _client.admin.command("ping")  # type: ignore[name-defined]
            mongo_ok = True
        except Exception:
            mongo_ok = False
    return {"status": "ok", "mongo_connected": mongo_ok, "agents_loaded": len(_registry)}


@app.get("/stats", response_model=StatsResponse)
async def stats():
    """Return basic registry statistics."""
    agents_by_region: dict[str, int] = {}
    all_skills: set[str] = set()
    for agent_dict in _registry.values():
        r = agent_dict.get("region") or "unknown"
        agents_by_region[r] = agents_by_region.get(r, 0) + 1
        for s in agent_dict.get("skills", []):
            all_skills.add(s)
    return StatsResponse(
        total_agents=len(_registry),
        agents_by_region=agents_by_region,
        unique_skills=len(all_skills),
        mongo_connected=USE_MONGO,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", INDEX_PORT))
    log.info("Starting NANDA Lean Index on port %d ...", port)
    uvicorn.run(
        "registry:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
