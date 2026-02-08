# OneClickAI — Supply Chain Agents

Multi-agent supply-chain coordination network built on a NANDA-inspired architecture. Five autonomous agents discover each other via a shared registry, negotiate procurement deals through structured A2A messaging, and coordinate logistics — all visualised in real-time through a React dashboard.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    React Dashboard (port 3000)                    │
│   ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐   │
│   │ Supply     │ │ Message  │ │ Timeline │ │ Execution Plan │   │
│   │ Graph      │ │ Flow     │ │          │ │ + Report       │   │
│   │ Cytoscape  │ │          │ │          │ │                │   │
│   └────────────┘ └──────────┘ └──────────┘ └────────────────┘   │
│              ▲ WebSocket (ws://localhost:6020/ws)                 │
└──────────────┼───────────────────────────────────────────────────┘
               │
┌──────────────┴───────────────────────────────────────────────────┐
│                    Event Bus (port 6020)                          │
│              POST /event  ──  WS /ws  ──  GET /events            │
└──────────────┬───────────────────────────────────────────────────┘
               │
    ┌──────────┼──────────────────────────────────────┐
    │          │          Agent Network                │
    │  ┌───────┴──────────────────────────────┐       │
    │  │  Procurement Agent (LangGraph:6010)  │       │
    │  │  DECOMPOSE → DISCOVER → VERIFY →     │       │
    │  │  NEGOTIATE → PLAN                    │       │
    │  └──┬────────────────────────────────┬──┘       │
    │     │ search/register                │ RFQ/QUOTE│
    │  ┌──┴──────────────┐    ┌────────────┴────────┐ │
    │  │ NANDA Index     │    │ Supplier A (CrewAI) │ │
    │  │ (port 6900)     │    │ (port 6001)         │ │
    │  │ register/search │    ├─────────────────────┤ │
    │  │ /lookup /list   │    │ Supplier B (Custom) │ │
    │  └─────────────────┘    │ (port 6002)         │ │
    │                         ├─────────────────────┤ │
    │                         │ Supplier C (LangCh) │ │
    │                         │ (port 6003)         │ │
    │                         ├─────────────────────┤ │
    │                         │ Logistics (AutoGen) │ │
    │                         │ (port 6004)         │ │
    │                         └─────────────────────┘ │
    └─────────────────────────────────────────────────┘
```

## Hero Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Discovery & Identity** | NANDA Lean Index with AgentAddr/AgentFacts schema, semantic skill search, ZTAA verification |
| 2 | **Coordination Cascade** | Full RFQ→QUOTE→COUNTER→ACCEPT→ORDER→SHIP_PLAN across 4 frameworks (LangGraph, CrewAI, Custom Python, LangChain/AutoGen) |
| 3 | **Visualization** | Real-time Cytoscape.js supply graph, message flow log, coordination timeline, execution summary with report download |

## Agent Framework Map

| Agent | Framework | Port | Skills |
|-------|-----------|------|--------|
| Procurement Orchestrator | **LangGraph** | 6010 | BOM decomposition, negotiation, orchestration |
| Supplier A — Carbon Fiber | **CrewAI** | 6001 | `supply:carbon_fiber_panels`, `supply:carbon_fiber_raw` |
| Supplier B — Precision Metals | **Custom Python** | 6002 | `supply:titanium_alloy`, `supply:titanium_fasteners`, `supply:ceramic_brake_calipers` |
| Supplier C — Powertrain | **LangChain** | 6003 | `supply:aluminum_engine_block`, `supply:turbocharger_assembly` |
| Logistics — EU Freight | **AutoGen** | 6004 | `logistics:road_freight_eu`, `logistics:express_delivery` |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key (set as `OPENAI_API_KEY` environment variable)
- MongoDB (optional — falls back to in-memory)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install dashboard dependencies

```bash
cd dashboard && npm install && cd ..
```

### 3. Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

### 4. Start everything

```bash
chmod +x start_all.sh
./start_all.sh
```

This starts all 7 backend services + the React dashboard. Services:

| Service | URL |
|---------|-----|
| NANDA Index | http://localhost:6900 |
| Event Bus | http://localhost:6020 (WS: ws://localhost:6020/ws) |
| Supplier A (CrewAI) | http://localhost:6001 |
| Supplier B (Custom) | http://localhost:6002 |
| Supplier C (LangChain) | http://localhost:6003 |
| Logistics (AutoGen) | http://localhost:6004 |
| Procurement (LangGraph) | http://localhost:6010 |
| Dashboard | http://localhost:5173 |

### 5. Run the cascade

Open the dashboard at http://localhost:5173 and type a procurement intent, or use the test script:

```bash
python3 test_cascade.py
```

### 6. Stop all services

```bash
./start_all.sh --stop
```

## Docker Compose (alternative)

```bash
export OPENAI_API_KEY="sk-..."
docker compose up --build
```

## Project Structure

```
hackathon/
├── shared/                 # Pydantic schemas, message types, config
│   ├── schemas.py          # AgentAddr, AgentFacts, Skill, etc.
│   ├── message_types.py    # Envelope, RFQ, QUOTE, ORDER, etc.
│   └── config.py           # Ports, URLs, constants
├── nanda-index/            # NANDA Lean Index (FastAPI + MongoDB)
│   └── registry.py         # register, search, lookup, list, stats
├── event-bus/              # WebSocket relay for dashboard
│   └── server.py           # POST /event → broadcast to WS /ws
├── agents/
│   ├── procurement/        # LangGraph orchestrator
│   │   ├── agent.py        # 5-node state machine
│   │   ├── bom.py          # LLM-powered BOM decomposition
│   │   ├── negotiation.py  # Scoring, counter-offers, selection
│   │   └── server.py       # FastAPI server + NANDA registration
│   ├── supplier/           # 3 supplier agents (different frameworks)
│   │   ├── inventory.py    # Simulated catalogues for all suppliers
│   │   ├── supplier_crewai.py      # CrewAI (port 6001)
│   │   ├── supplier_custom.py      # Custom Python (port 6002)
│   │   └── supplier_langchain.py   # LangChain (port 6003)
│   └── logistics/          # AutoGen route planner
│       └── agent.py        # Dijkstra routing + LLM reasoning
├── dashboard/              # React + Cytoscape.js + Tailwind CSS
│   └── src/
│       ├── App.tsx
│       ├── components/     # SupplyGraph, MessageFlow, Timeline, etc.
│       ├── hooks/          # useWebSocket, useDashboardState
│       └── types.ts
├── docker-compose.yml      # Full Docker orchestration
├── Dockerfile.agent        # Shared Python agent image
├── start_all.sh            # Local startup script
├── test_cascade.py         # End-to-end integration test
└── requirements.txt        # Python dependencies
```

## Coordination Cascade Flow

1. **DECOMPOSE** — User submits intent → LLM decomposes into Bill of Materials (~8 parts)
2. **DISCOVER** — Query NANDA Index `/search?skills=...` per part → get AgentAddr list
3. **VERIFY** — Fetch AgentFacts from each supplier → ZTAA checks (reliability, ESG, jurisdiction, certifications)
4. **NEGOTIATE** — Send RFQs → collect QUOTEs → rank with weighted scoring → COUNTER_OFFER to top supplier → ACCEPT/REJECT → place ORDERs
5. **PLAN** — Send LOGISTICS_REQUESTs → receive SHIP_PLANs → generate Network Coordination Report

## Scoring Weights (Negotiation)

| Factor | Weight |
|--------|--------|
| Price | 30% |
| Lead Time | 25% |
| Reliability | 20% |
| ESG Rating | 15% |
| Proximity | 10% |

## NANDA Protocol

Each agent implements the NANDA protocol:
- **Self-hosts AgentFacts** at `GET /agent-facts` (rich metadata: skills, certifications, evaluations, policies)
- **Registers** with the NANDA Lean Index at startup (lightweight AgentAddr record)
- **Communicates** via typed A2A message envelopes (RFQ, QUOTE, COUNTER_OFFER, etc.)

## Tech Stack

**Backend**: Python 3.11, FastAPI, Pydantic v2, httpx, OpenAI GPT-4o
**Agent Frameworks**: LangGraph, CrewAI, LangChain, AutoGen (pyautogen)
**Frontend**: React 19, TypeScript, Vite, Cytoscape.js, Tailwind CSS 4
**Infrastructure**: MongoDB (optional), WebSocket event bus, Docker Compose
