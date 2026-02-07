# One Click AI — Supply Chain Agents

> NANDA-Native "Internet of Agents" Simulation

**"Buy all the parts required to assemble a Ferrari — in one click."**

A multi-agent supply chain orchestration system where independent AI agents discover, negotiate, and coordinate across an open agent network. Built for the VC Track hackathon challenge.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Dashboard (:3000)                     │
│  Supply Graph │ Message Flow │ Timeline │ Risk │ Cost │ Report  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket
┌──────────────────────────┴──────────────────────────────────────┐
│                   Coordinator Hub (:8001)                        │
│              Event aggregation + report generation               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
    ┌──────────────────────┼──────────────────────────────┐
    │                      │                              │
┌───┴───┐  ┌───────────┐  │  ┌─────────────┐  ┌─────────┴──┐
│Procure│→ │ Supplier 1 │  │  │Manufacturer │→ │  Logistics  │
│ment   │→ │ Supplier 2 │  │  │             │→ │             │
│(Lang  │  │ (AutoGen)  │  │  │ (LangGraph) │  │  (AutoGen)  │
│Graph) │  └────────────┘  │  └──────┬──────┘  └─────────────┘
└───┬───┘                  │         │
    │                      │  ┌──────┴──────┐
    │                      │  │ Compliance   │
    │                      │  │ (LangGraph)  │
    │                      │  └──────────────┘
    │                      │
    │      ┌───────────────┴───────────────┐
    │      │   NANDA Lean Index (:8000)    │
    │      │  AgentAddr registry + resolve  │
    │      └───────────────┬───────────────┘
    │                      │ delegate
    │      ┌───────────────┴───────────────┐
    └─────►│  Adaptive Resolver (:8016)    │
           │  Context-aware tailored       │
           │  endpoint selection           │
           │  + Negotiation + Deployment   │
           └───────────────────────────────┘
```

## Key Features

### Hero Feature 1 — Agent Registry (Discovery & Identity)
- **NANDA Lean Index**: DNS-like discovery returning minimal AgentAddr records (~120 bytes)
- **Two-step resolution**: Index → AgentAddr → self-hosted AgentFacts (via `/.well-known/agent-facts`)
- **Adaptive Resolver**: Context-aware endpoint selection based on requester location, load, QoS, and security
- **Negotiation flow**: Agents can require trust negotiation before establishing communication channels
- **Deployment records**: Physical resource metadata for geo-aware routing
- **Ed25519 signatures** on AgentAddr + **W3C VC v2** on AgentFacts
- **Context requirements**: Agents declare what context they need from requesters
- Dynamic registration — agents self-register AgentAddr on startup, self-host AgentFacts

### Hero Feature 2 — Coordination Cascade
- Full procurement cascade: Intent → Discovery → RFQ → Negotiate → Order → Manufacture → Ship
- **Cross-framework interoperability**: LangGraph agents (Procurement, Manufacturer, Compliance) communicate with AutoGen agents (Supplier, Logistics) via HTTP/JSON
- MCP-style message schemas with Pydantic
- LLM-powered reasoning at every decision point

### Hero Feature 3 — Supply Graph & Visualization
- Interactive React Flow graph with live agent activity
- Real-time message flow via WebSocket
- Coordination timeline with step-by-step cascade visualization
- Risk heatmap and cost breakdown analytics
- Network Coordination Report generation

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Agent Framework A** | LangGraph | Procurement, Manufacturer, Compliance agents |
| **Agent Framework B** | AutoGen | Supplier, Logistics agents (cross-framework interop) |
| **LLM** | OpenAI GPT-4o | Agent reasoning, negotiation, decision-making |
| **Discovery** | NANDA Lean Index + Adaptive Resolver | Two-step + context-aware resolution |
| **Services** | FastAPI | Each agent runs as independent HTTP service |
| **Messaging** | Pydantic MCP-style schemas | Structured inter-agent communication |
| **Real-time** | WebSocket | Live event streaming to dashboard |
| **Frontend** | React 18 + Vite | Modern SPA |
| **Visualization** | React Flow + Recharts | Graph, charts, analytics |
| **Styling** | Tailwind CSS | Responsive dark-themed UI |
| **Infrastructure** | Docker Compose | Containerized microservices |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API key

### 1. Setup Environment

```bash
# Clone and enter the project
cd One-Click-AI

# Create .env file
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Start Backend Services

```bash
# Launch all 9 backend services
python run.py
```

This starts:
| Service | Port | Framework |
|---------|------|-----------|
| NANDA Lean Index | :8000 | FastAPI (AgentAddr registry) |
| Coordinator | :8001 | FastAPI + WebSocket |
| Procurement Agent | :8010 | LangGraph |
| Supplier Agent 1 | :8011 | AutoGen |
| Supplier Agent 2 | :8012 | AutoGen |
| Manufacturer Agent | :8013 | LangGraph |
| Logistics Agent | :8014 | AutoGen |
| Compliance Agent | :8015 | LangGraph |
| Adaptive Resolver | :8016 | FastAPI (context-aware routing) |

### 3. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**

### 4. Trigger a Cascade

Click **"One Click Buy"** in the dashboard, or use the API directly:

```bash
curl -X POST http://localhost:8010/intent \
  -H "Content-Type: application/json" \
  -d '{"intent": "Buy all the parts required to assemble a Ferrari"}'
```

### Docker (Alternative)

```bash
docker-compose up --build
```

All services + frontend available at `http://localhost:3000`.

## Running Tests

```bash
# Start services first
python run.py

# In another terminal, run the end-to-end test
python test_cascade.py
```

## Coordination Cascade Flow

```
User Intent: "Buy all parts for a Ferrari"
     │
     ▼
[1] Procurement Agent parses intent, maps to Ferrari BOM (10 component categories)
     │
     ▼
[2] Procurement queries NANDA Lean Index: discover(role="supplier")
     │  + sends RequesterContext {geo: "Maranello", security: "authenticated"}
     ▼
[3] For each supplier: Adaptive Resolver returns tailored endpoint
     │  (geo-proximity scoring, deployment-aware routing)
     ▼
[4] Procurement sends RFQ to both suppliers via tailored endpoints
     │
     ├──► Supplier 1 (AutoGen, Stuttgart): checks inventory, returns quote
     └──► Supplier 2 (AutoGen, Shenzhen): checks inventory, returns quote
     │
     ▼
[5] Procurement evaluates quotes using LLM + NANDA trust metadata
     │  (certification level, reputation score, deployment mode)
     ▼
[6] Procurement negotiates 10% volume discount with chosen supplier
     │
     ▼
[7] Procurement places order, adaptive-resolves Manufacturer endpoint
     │
     ▼
[8] Manufacturer validates BOM
     │
     ├──► Compliance Agent (adaptive resolve): jurisdiction + policy + ESG checks
     └──► Logistics Agent (adaptive resolve): geo-nearest route planning
     │
     ▼
[9] Manufacturer creates assembly schedule
     │
     ▼
[10] Network Coordination Report with full NANDA resolution audit trail
```

## Project Structure

```
One-Click-AI/
├── shared/                 # Shared schemas and config
│   ├── schemas.py          # MCP-style message schemas
│   ├── agent_facts.py      # AgentAddr, AgentFacts, RequesterContext, DeploymentRecord
│   ├── agent_base.py       # Agent helpers (register, resolve, adaptive resolve)
│   ├── nanda_crypto.py     # Ed25519-style signatures (sign/verify)
│   └── config.py           # Ports, URLs, settings
├── registry/               # NANDA Lean Index (DNS-like)
│   ├── main.py             # FastAPI: /register, /resolve, /resolve/adaptive, /discover
│   └── store.py            # In-memory AgentAddr store with TTL
├── resolver/               # NANDA Adaptive Resolver (NEW)
│   └── main.py             # Context-aware endpoint resolution, negotiation, deployment records
├── coordinator/            # WebSocket hub + report generator
│   ├── main.py             # Event aggregation service
│   └── report.py           # Report builder
├── agents/
│   ├── procurement/        # LangGraph — cascade entry point (adaptive resolution)
│   ├── supplier/           # AutoGen — inventory + quoting (deployment records)
│   ├── manufacturer/       # LangGraph — assembly scheduling (multi-region deployment)
│   ├── logistics/          # AutoGen — route planning (geo-aware routing)
│   └── compliance/         # LangGraph — policy validation
├── frontend/               # React + Vite dashboard
│   └── src/components/     # SupplyGraph, MessageFlow, Timeline, etc.
├── docker-compose.yml      # Full containerized deployment (9 services + frontend)
├── run.py                  # Local development launcher
└── test_cascade.py         # End-to-end test script (with adaptive resolver tests)
```

## Cross-Framework Interoperability

The system proves that agents built on different frameworks can interoperate:

- **LangGraph agents** (Procurement, Manufacturer, Compliance) use stateful graphs with typed state dictionaries
- **AutoGen agents** (Supplier, Logistics) use conversational agent patterns
- **Communication**: All agents use the same HTTP/JSON + Pydantic schemas, regardless of framework
- The Procurement Agent (LangGraph) sends RFQs to Supplier Agents (AutoGen) via HTTP — proving framework independence

## License

MIT
