# Supplier Agent Creation Guide

A step-by-step guide to creating new supplier agents for the OneClickAI supply chain network.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Reference Table](#quick-reference-table)
- [Step-by-Step Guide](#step-by-step-guide)
- [Framework Options](#framework-options)
- [Testing Your Supplier](#testing-your-supplier)
- [Minimal Template](#minimal-template)
- [Common Patterns](#common-patterns)
- [Troubleshooting](#troubleshooting)

---

## Overview

All supplier agents in the OneClickAI network follow a consistent pattern:

1. **Self-host AgentFacts** at `GET /agent-facts` (NANDA protocol)
2. **Register with NANDA Index** on startup
3. **Expose 5 standard endpoints**: `/agent-facts`, `/rfq`, `/counter`, `/order`, `/health`
4. **Maintain state** using in-memory dictionaries (`_rfq_store`, `_order_store`)
5. **Emit events** to the Event Bus for dashboard visibility
6. **Generate quotes** using CrewAI, LangChain, or rule-based logic

The main difference between suppliers is the **quote generation method** and the **parts catalog**.

---

## Prerequisites

- **Python 3.11+**
- **OpenAI API key** (set as `OPENAI_API_KEY` environment variable)
- **Access to shared modules** (`shared/`, `agents/supplier/inventory.py`)
- **Available port** in range 6001-6020
- **Basic FastAPI knowledge**

---

## Quick Reference Table

Existing suppliers for reference:

| Supplier | Framework | Port | File | Skills | Catalog Key |
|----------|-----------|------|------|--------|-------------|
| Supplier A | CrewAI | 6001 | `supplier_crewai.py` | Carbon fiber panels, raw carbon | `supplier_a` |
| Supplier B | Custom | 6002 | `supplier_custom.py` | Titanium alloy, fasteners, ceramic brakes | `supplier_b` |
| Supplier C | LangChain | 6003 | `supplier_langchain.py` | Aluminum engine blocks, turbochargers | `supplier_c` |
| Supplier D | CrewAI | 6005 | `supplier_aluminum.py` | Aluminum chassis, carbon composite, magnesium wheels | `supplier_d` |
| Supplier F | CrewAI | 6007 | `supplier_pirelli.py` | Pirelli P Zero tires, racing slicks | `supplier_f` |
| Supplier G | LangChain | 6008 | `supplier_michelin.py` | Michelin Pilot Sport, racing tires | `supplier_g` |
| Supplier H | Custom | 6009 | `supplier_brakes.py` | Carbon ceramic brakes, brake calipers | `supplier_h` |
| Logistics | AutoGen | 6004 | `logistics/agent.py` | Road freight, express delivery | N/A |

---

## Step-by-Step Guide

### Step 1: Allocate a Port

**File:** `shared/config.py`

Add your supplier to the `SUPPLIER_PORTS` dictionary:

```python
SUPPLIER_PORTS = {
    "supplier_a": 6001,
    "supplier_b": 6002,
    "supplier_c": 6003,
    "supplier_d": 6005,
    "supplier_f": 6007,
    "supplier_g": 6008,
    "supplier_h": 6009,
    "supplier_x": 6011,  # <-- Add your new supplier here
}
```

**Port allocation rules:**
- Ports 6001-6020 are reserved for agents
- Port 6900 is NANDA Index
- Port 6020 is Event Bus
- Port 6010 is Procurement
- Port 6004 is Logistics

### Step 2: Define Inventory Catalog

**File:** `agents/supplier/inventory.py`

Add your catalog dictionary using the `PartInfo` dataclass:

```python
from dataclasses import dataclass, field

@dataclass
class PartInfo:
    part_id: str
    part_name: str
    description: str
    base_price: float          # EUR per unit
    currency: str = "EUR"
    stock_quantity: int = 0
    lead_time_days: int = 7
    shipping_origin: str = ""
    certifications: list[str] = field(default_factory=list)
    min_order_qty: int = 1
    floor_price_pct: float = 0.80  # 80% of base_price
    specs: dict[str, Any] = field(default_factory=dict)
    
    @property
    def floor_price(self) -> float:
        """Minimum acceptable price (for counter-offers)."""
        return round(self.base_price * self.floor_price_pct, 2)
```

**Example catalog:**

```python
SUPPLIER_X_CATALOG: dict[str, PartInfo] = {
    "widget_pro": PartInfo(
        part_id="widget_pro",
        part_name="Professional Widget Assembly",
        description="High-performance widget with aerospace-grade materials",
        base_price=125.00,
        stock_quantity=500,
        lead_time_days=10,
        shipping_origin="Munich, Germany",
        certifications=["ISO 9001", "AS9100"],
        min_order_qty=5,
        floor_price_pct=0.85,  # Won't go below €106.25
        specs={
            "material": "Titanium Grade 5",
            "weight_kg": 2.5,
            "dimensions_mm": "200x150x80",
        },
    ),
    "widget_standard": PartInfo(
        part_id="widget_standard",
        part_name="Standard Widget",
        description="General-purpose widget for everyday use",
        base_price=45.00,
        stock_quantity=1200,
        lead_time_days=5,
        shipping_origin="Munich, Germany",
        certifications=["ISO 9001"],
        min_order_qty=10,
        floor_price_pct=0.80,
        specs={
            "material": "Aluminum 6061",
            "weight_kg": 1.2,
        },
    ),
}
```

Add your catalog to the `ALL_CATALOGS` dictionary:

```python
ALL_CATALOGS = {
    "supplier_a": SUPPLIER_A_CATALOG,
    "supplier_b": SUPPLIER_B_CATALOG,
    "supplier_c": SUPPLIER_C_CATALOG,
    "supplier_x": SUPPLIER_X_CATALOG,  # <-- Add here
}
```

### Step 3: Create Agent File

**File:** `agents/supplier/supplier_x.py`

**3.1 Import dependencies:**

```python
import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import (
    EVENT_BUS_HTTP_URL,
    INDEX_URL,
    OPENAI_MODEL,
    SUPPLIER_PORTS,
)
from shared.message_types import (
    Envelope,
    MessageType,
    QuotePayload,
    RejectPayload,
    RevisedQuotePayload,
    make_envelope,
)
from shared.schemas import (
    AgentFacts,
    Certification,
    Endpoint,
    Evaluation,
    Policy,
    Skill,
)

from agents.supplier.inventory import (
    SUPPLIER_X_CATALOG,
    compute_volume_discount,
    evaluate_counter_offer,
    lookup_part,
)
```

**3.2 Define constants:**

```python
AGENT_ID = "supplier-x"
AGENT_NAME = "Acme Widget Corporation"
PORT = int(os.environ.get("PORT", SUPPLIER_PORTS["supplier_x"]))
HOST = "0.0.0.0"
BASE_URL = f"http://localhost:{PORT}"

# In-memory state
_rfq_store: dict[str, dict[str, Any]] = {}
_order_store: dict[str, dict[str, Any]] = {}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supplier_x")
```

**3.3 Define AgentFacts:**

```python
AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Supplier X",
    description=(
        "Acme Widget Corporation supplies professional-grade and standard widgets "
        "for industrial applications. Specializes in aerospace-grade materials "
        "with fast lead times and flexible MOQ."
    ),
    version="1.0.0",
    framework="custom",  # or "crewai", "langchain"
    jurisdiction="EU",
    provider="Acme Widget Corp GmbH",
    skills=[
        Skill(
            id="supply:widget_pro",
            description="Professional widget assemblies with aerospace-grade titanium",
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=10,
        ),
        Skill(
            id="supply:widget_standard",
            description="Standard aluminum widgets for general applications",
            input_modes=["application/json"],
            output_modes=["application/json"],
            supported_regions=["EU"],
            max_lead_time_days=5,
        ),
    ],
    endpoints=[
        Endpoint(path="/agent-facts", method="GET", description="Self-hosted AgentFacts"),
        Endpoint(path="/rfq", method="POST", description="Request For Quotation"),
        Endpoint(path="/counter", method="POST", description="Counter-offer evaluation"),
        Endpoint(path="/order", method="POST", description="Confirm purchase order"),
        Endpoint(path="/health", method="GET", description="Health check"),
    ],
    evaluations=[
        Evaluation(evaluator="self", score=0.93, metric="reliability"),
        Evaluation(evaluator="customer_feedback", score=0.91, metric="quality"),
    ],
    certifications=[
        Certification(name="ISO 9001", issuer="TÜV SÜD"),
        Certification(name="AS9100", issuer="ANAB"),
    ],
    policies=[
        Policy(
            name="min_order_qty",
            description="Minimum order quantities vary by part",
            value={"widget_pro": 5, "widget_standard": 10},
        ),
        Policy(
            name="volume_discounts",
            description="Tiered discounts: 2% at 20 units, 3% at 50, 5% at 100",
            value="tiered",
        ),
    ],
    reliability_score=0.93,
    esg_rating="A",
    base_url=BASE_URL,
)
```

**3.4 Implement helper functions:**

```python
async def _emit_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    """POST an event to the Event Bus (best-effort, non-blocking)."""
    event = {
        "event_type": event_type,
        "agent_id": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{EVENT_BUS_HTTP_URL}/event", json=event)
    except Exception:
        logger.debug("Event Bus not reachable (non-fatal).")


async def _register_with_index() -> None:
    """Register this agent with the NANDA Lean Index."""
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
    await _emit_event(
        "AGENT_REGISTERED",
        {
            "agent_name": AGENT_NAME,
            "framework": "custom",
            "port": PORT,
            "skills": [s.id for s in AGENT_FACTS.skills],
        },
    )
```

**3.5 Implement FastAPI endpoints:**

See [Framework Options](#framework-options) section for `/rfq` and `/counter` implementations.

**3.6 Create FastAPI app:**

```python
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    logger.info("Supplier X starting on port %d …", PORT)
    await _register_with_index()
    await _emit_startup_event()
    logger.info("Supplier X ready at %s", BASE_URL)
    yield
    logger.info("Supplier X shutting down.")


app = FastAPI(
    title="Supplier X — Acme Widget Corporation",
    description="Widget supplier with aerospace-grade materials",
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


@app.get("/agent-facts")
async def agent_facts():
    """Self-hosted AgentFacts endpoint (NANDA protocol)."""
    return AGENT_FACTS.model_dump(mode="json")


@app.get("/health")
async def health():
    """Liveness / readiness probe."""
    return {
        "status": "ok",
        "service": "supplier-x",
        "agent_id": AGENT_ID,
        "catalog_size": len(SUPPLIER_X_CATALOG),
    }


if __name__ == "__main__":
    uvicorn.run(
        "supplier_x:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
```

### Step 4: Choose Quote Generation Framework

See [Framework Options](#framework-options) section below for `/rfq` and `/counter` implementations.

### Step 5: Register in Startup Script

**File:** `start_all.sh`

Add your supplier to the startup sequence:

```bash
# Start Supplier X (Widget supplier)
echo "Starting Supplier X (port $SUPPLIER_X_PORT)..."
python3 agents/supplier/supplier_x.py > logs/supplier_x.log 2>&1 &
SUPPLIER_X_PID=$!
echo $SUPPLIER_X_PID >> .service_pids
wait_for_health "http://localhost:$SUPPLIER_X_PORT/health" "Supplier X"
```

**Optional: Add to Docker Compose**

**File:** `docker-compose.yml`

```yaml
  supplier-x:
    build:
      context: .
      dockerfile: Dockerfile.agent
    environment:
      - PORT=6011
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - PYTHONPATH=/app
    ports:
      - "6011:6011"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6011/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    depends_on:
      event-bus:
        condition: service_healthy
```

### Step 6: Test Your Supplier

See [Testing Your Supplier](#testing-your-supplier) section below.

---

## Framework Options

Choose one of three approaches for quote generation:

### Option 1: Rule-Based (Simplest)

**Best for:** Fast deterministic quotes, no LLM required

**Example from Supplier B** (`supplier_custom.py`):

```python
@app.post("/rfq")
async def receive_rfq(envelope: Envelope):
    """Process RFQ with pure rule-based logic."""
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", str(uuid.uuid4()))
    part_name = payload.get("part", "")
    quantity = int(payload.get("quantity", 1))
    
    # Store RFQ
    _rfq_store[rfq_id] = {
        "part": part_name,
        "quantity": quantity,
        "from_agent": envelope.from_agent,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # Look up part
    part_info = lookup_part("supplier_x", part_name)
    if part_info is None:
        # Reject if not in catalog
        reject_payload = RejectPayload(
            rfq_id=rfq_id,
            rejection_reason=f"Part '{part_name}' not in catalog",
        )
        await _emit_event("RFQ_REJECTED", {"rfq_id": rfq_id, "part": part_name})
        return make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=reject_payload,
            correlation_id=rfq_id,
        ).model_dump(mode="json")
    
    # Calculate price with volume discount
    discount_pct = compute_volume_discount(quantity)
    unit_price = part_info.base_price * (1.0 - discount_pct)
    
    # Build quote
    quote_payload = QuotePayload(
        rfq_id=rfq_id,
        unit_price=round(unit_price, 2),
        currency=part_info.currency,
        qty_available=part_info.stock_quantity,
        lead_time_days=part_info.lead_time_days,
        shipping_origin=part_info.shipping_origin,
        certifications=part_info.certifications,
        valid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        notes=f"{discount_pct*100:.0f}% volume discount applied" if discount_pct > 0 else "",
    )
    
    # Store quoted price
    _rfq_store[rfq_id]["quoted_price"] = quote_payload.unit_price
    
    await _emit_event("QUOTE_GENERATED", {
        "rfq_id": rfq_id,
        "part": part_name,
        "unit_price": quote_payload.unit_price,
        "lead_time": quote_payload.lead_time_days,
    })
    
    return make_envelope(
        MessageType.QUOTE,
        from_agent=AGENT_ID,
        to_agent=envelope.from_agent,
        payload=quote_payload,
        correlation_id=rfq_id,
    ).model_dump(mode="json")


@app.post("/counter")
async def receive_counter_offer(envelope: Envelope):
    """Evaluate counter-offer against floor price."""
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", "")
    target_price = float(payload.get("target_price", 0.0))
    
    rfq_data = _rfq_store.get(rfq_id, {})
    part_name = rfq_data.get("part", "")
    
    # Use helper function from inventory.py
    decision = evaluate_counter_offer("supplier_x", part_name, target_price)
    
    await _emit_event("COUNTER_EVALUATED", {
        "rfq_id": rfq_id,
        "decision": decision["decision"],
        "target_price": target_price,
    })
    
    if decision["decision"] == "accept":
        revised_payload = RevisedQuotePayload(
            rfq_id=rfq_id,
            revised_price=target_price,
            conditions="Accepted at requested price",
        )
        return make_envelope(
            MessageType.REVISED_QUOTE,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=revised_payload,
            correlation_id=rfq_id,
        ).model_dump(mode="json")
    else:
        reject_payload = RejectPayload(
            rfq_id=rfq_id,
            rejection_reason=decision["reason"],
        )
        return make_envelope(
            MessageType.REJECT,
            from_agent=AGENT_ID,
            to_agent=envelope.from_agent,
            payload=reject_payload,
            correlation_id=rfq_id,
        ).model_dump(mode="json")
```

### Option 2: CrewAI (AI-Powered)

**Best for:** Multi-agent reasoning, complex quote logic

**Example from Supplier A** (`supplier_crewai.py`):

```python
from crewai import Agent, Crew, Process, Task
from crewai.tools import tool as crewai_tool

# Define tools
@crewai_tool
def check_inventory_tool(part_query: str) -> str:
    """Check inventory for a part."""
    part_info = lookup_part("supplier_x", part_query)
    if part_info is None:
        return f"Part '{part_query}' not found in catalog."
    return json.dumps({
        "part_id": part_info.part_id,
        "stock": part_info.stock_quantity,
        "base_price": part_info.base_price,
        "lead_time": part_info.lead_time_days,
    })

@crewai_tool
def calculate_discount_tool(quantity: int) -> str:
    """Calculate volume discount."""
    discount = compute_volume_discount(quantity)
    return f"{discount * 100:.1f}% discount for {quantity} units"

# Create agents
inventory_checker = Agent(
    role="Inventory Checker",
    goal="Verify part availability and stock levels",
    backstory="You manage inventory and check stock availability.",
    tools=[check_inventory_tool],
    verbose=False,
)

pricing_analyst = Agent(
    role="Pricing Analyst",
    goal="Generate competitive quotes with appropriate discounts",
    backstory="You analyze pricing and apply volume discounts.",
    tools=[calculate_discount_tool],
    verbose=False,
)

@app.post("/rfq")
async def receive_rfq(envelope: Envelope):
    """Process RFQ using CrewAI crew."""
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", str(uuid.uuid4()))
    part_name = payload.get("part", "")
    quantity = int(payload.get("quantity", 1))
    
    # Store RFQ
    _rfq_store[rfq_id] = {...}
    
    # Look up part (fallback)
    part_info = lookup_part("supplier_x", part_name)
    if part_info is None:
        # Return REJECT
        ...
    
    # Create tasks
    inventory_task = Task(
        description=f"Check inventory for {part_name}",
        agent=inventory_checker,
        expected_output="Part availability status",
    )
    
    pricing_task = Task(
        description=f"Generate quote for {quantity} units of {part_name}",
        agent=pricing_analyst,
        expected_output="Quoted unit price",
    )
    
    # Run crew
    crew = Crew(
        agents=[inventory_checker, pricing_analyst],
        tasks=[inventory_task, pricing_task],
        process=Process.sequential,
        verbose=False,
    )
    
    try:
        result = await asyncio.to_thread(crew.kickoff)
        # Parse result and extract price
        # ... (implementation details)
        unit_price = part_info.base_price  # Fallback
    except Exception as exc:
        logger.warning("CrewAI failed, using fallback: %s", exc)
        unit_price = part_info.base_price
    
    # Build and return QUOTE
    quote_payload = QuotePayload(...)
    ...
```

### Option 3: LangChain (Prompt-Based)

**Best for:** Custom prompts, tool integration

**Example from Supplier C** (`supplier_langchain.py`):

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain.tools import Tool
from langchain_openai import ChatOpenAI

# Create tools
def check_inventory(part_query: str) -> str:
    part_info = lookup_part("supplier_x", part_query)
    if part_info is None:
        return "Part not found"
    return json.dumps({
        "stock": part_info.stock_quantity,
        "base_price": part_info.base_price,
        "lead_time": part_info.lead_time_days,
    })

tools = [
    Tool(
        name="check_inventory",
        func=check_inventory,
        description="Check inventory for a part by name or ID",
    ),
]

# Create agent
llm = ChatOpenAI(model="gpt-4o", temperature=0.1)
prompt = PromptTemplate.from_template("""
You are a supplier generating a quote for automotive parts.

Part requested: {part_name}
Quantity: {quantity}

Use the check_inventory tool to verify availability, then generate a competitive quote.

{agent_scratchpad}
""")

agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

@app.post("/rfq")
async def receive_rfq(envelope: Envelope):
    """Process RFQ using LangChain agent."""
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", str(uuid.uuid4()))
    part_name = payload.get("part", "")
    quantity = int(payload.get("quantity", 1))
    
    # Store RFQ
    _rfq_store[rfq_id] = {...}
    
    # Run LangChain agent
    try:
        result = await asyncio.to_thread(
            agent_executor.invoke,
            {"part_name": part_name, "quantity": quantity}
        )
        # Parse result
        unit_price = ...  # Extract from result
    except Exception as exc:
        logger.warning("LangChain failed, using fallback: %s", exc)
        part_info = lookup_part("supplier_x", part_name)
        unit_price = part_info.base_price if part_info else 0.0
    
    # Build and return QUOTE
    ...
```

---

## Testing Your Supplier

### Manual Testing with curl

**1. Check health:**
```bash
curl http://localhost:6011/health
```

**2. Verify registration:**
```bash
curl http://localhost:6900/list | jq '.[] | select(.agent_id == "supplier-x")'
```

**3. Fetch AgentFacts:**
```bash
curl http://localhost:6011/agent-facts | jq
```

**4. Send test RFQ:**
```bash
curl -X POST http://localhost:6011/rfq \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "test-123",
    "type": "RFQ",
    "from_agent": "test-agent",
    "to_agent": "supplier-x",
    "correlation_id": "rfq-test-001",
    "payload": {
      "rfq_id": "rfq-test-001",
      "part": "widget_pro",
      "quantity": 10,
      "required_by": "2026-03-01",
      "delivery_location": "Stuttgart, Germany"
    }
  }' | jq
```

**Expected response:**
```json
{
  "type": "QUOTE",
  "from_agent": "supplier-x",
  "payload": {
    "rfq_id": "rfq-test-001",
    "unit_price": 125.00,
    "qty_available": 500,
    "lead_time_days": 10,
    ...
  }
}
```

**5. Test counter-offer:**
```bash
curl -X POST http://localhost:6011/counter \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "counter-123",
    "type": "COUNTER_OFFER",
    "from_agent": "test-agent",
    "to_agent": "supplier-x",
    "correlation_id": "rfq-test-001",
    "payload": {
      "rfq_id": "rfq-test-001",
      "target_price": 110.00,
      "justification": "Volume discount request"
    }
  }' | jq
```

### Integration Testing

**Run the full cascade:**
```bash
# Start all services
./start_all.sh

# Run test script
python3 test_cascade.py

# Check dashboard
open http://localhost:5173
```

### Verify in Dashboard

1. Submit intent that includes your part (e.g., "Buy widgets")
2. Check that your supplier appears in the graph
3. Verify RFQ → QUOTE → ORDER flow
4. Check message log for your supplier's events

---

## Minimal Template

A bare-bones ~200-line supplier template:

**File:** `agents/supplier/supplier_template.py`

```python
"""Supplier Template — Minimal boilerplate for new suppliers."""

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import EVENT_BUS_HTTP_URL, INDEX_URL, SUPPLIER_PORTS
from shared.message_types import (
    Envelope,
    MessageType,
    QuotePayload,
    RejectPayload,
    RevisedQuotePayload,
    make_envelope,
)
from shared.schemas import AgentFacts, Endpoint, Skill

from agents.supplier.inventory import lookup_part, evaluate_counter_offer

# ============================================================================
# Configuration
# ============================================================================

AGENT_ID = "supplier-template"
AGENT_NAME = "Template Supplier"
PORT = int(os.environ.get("PORT", 6011))
BASE_URL = f"http://localhost:{PORT}"

_rfq_store: dict[str, dict[str, Any]] = {}
_order_store: dict[str, dict[str, Any]] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("supplier_template")

# ============================================================================
# AgentFacts
# ============================================================================

AGENT_FACTS = AgentFacts(
    id=AGENT_ID,
    agent_name=AGENT_NAME,
    label="Template",
    description="Minimal supplier template for demonstration",
    version="1.0.0",
    framework="custom",
    jurisdiction="EU",
    provider="Template Corp",
    skills=[
        Skill(
            id="supply:template_part",
            description="Template part for testing",
            supported_regions=["EU"],
            max_lead_time_days=7,
        ),
    ],
    endpoints=[
        Endpoint(path="/agent-facts", method="GET"),
        Endpoint(path="/rfq", method="POST"),
        Endpoint(path="/counter", method="POST"),
        Endpoint(path="/order", method="POST"),
        Endpoint(path="/health", method="GET"),
    ],
    reliability_score=0.90,
    esg_rating="A",
    base_url=BASE_URL,
)

# ============================================================================
# Helpers
# ============================================================================

async def _emit_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    event = {
        "event_type": event_type,
        "agent_id": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{EVENT_BUS_HTTP_URL}/event", json=event)
    except Exception:
        pass

async def _register_with_index() -> None:
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
            await client.post(f"{INDEX_URL}/register", json=payload)
    except Exception as exc:
        logger.warning("Failed to register: %s", exc)

# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s on port %d", AGENT_NAME, PORT)
    await _register_with_index()
    await _emit_event("AGENT_REGISTERED", {"agent_name": AGENT_NAME, "port": PORT})
    yield
    logger.info("Shutting down %s", AGENT_NAME)

app = FastAPI(title=AGENT_NAME, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

@app.get("/agent-facts")
async def agent_facts():
    return AGENT_FACTS.model_dump(mode="json")

@app.post("/rfq")
async def receive_rfq(envelope: Envelope):
    payload = envelope.payload
    rfq_id = payload.get("rfq_id", str(uuid.uuid4()))
    part_name = payload.get("part", "")
    quantity = int(payload.get("quantity", 1))
    
    _rfq_store[rfq_id] = {"part": part_name, "quantity": quantity}
    
    # TODO: Implement quote generation
    quote_payload = QuotePayload(
        rfq_id=rfq_id,
        unit_price=100.0,  # Placeholder
        qty_available=1000,
        lead_time_days=7,
    )
    
    await _emit_event("QUOTE_GENERATED", {"rfq_id": rfq_id})
    
    return make_envelope(
        MessageType.QUOTE,
        from_agent=AGENT_ID,
        to_agent=envelope.from_agent,
        payload=quote_payload,
        correlation_id=rfq_id,
    ).model_dump(mode="json")

@app.post("/counter")
async def receive_counter_offer(envelope: Envelope):
    # TODO: Implement counter-offer logic
    return make_envelope(
        MessageType.REJECT,
        from_agent=AGENT_ID,
        to_agent=envelope.from_agent,
        payload=RejectPayload(rfq_id="", rejection_reason="Not implemented"),
    ).model_dump(mode="json")

@app.post("/order")
async def receive_order(envelope: Envelope):
    payload = envelope.payload
    order_id = payload.get("order_id", str(uuid.uuid4()))
    _order_store[order_id] = payload
    await _emit_event("ORDER_CONFIRMED", {"order_id": order_id})
    return {"status": "confirmed", "order_id": order_id}

@app.get("/health")
async def health():
    return {"status": "ok", "service": AGENT_ID}

if __name__ == "__main__":
    uvicorn.run("supplier_template:app", host="0.0.0.0", port=PORT, log_level="info")
```

---

## Common Patterns

### Pattern 1: Fuzzy Part Matching

```python
from agents.supplier.inventory import lookup_part

part_info = lookup_part("supplier_x", part_name)
# Matches: "widget_pro", "widget pro", "Professional Widget", "widget-pro"
```

### Pattern 2: Volume Discounts

```python
from agents.supplier.inventory import compute_volume_discount

discount_pct = compute_volume_discount(quantity)
# Returns: 0.02 (2%) for qty >= 20, 0.03 for >= 50, 0.05 for >= 100
discounted_price = base_price * (1.0 - discount_pct)
```

### Pattern 3: Counter-Offer Evaluation

```python
from agents.supplier.inventory import evaluate_counter_offer

decision = evaluate_counter_offer("supplier_x", "widget_pro", target_price=110.00)
# Returns: {"decision": "accept"|"reject", "reason": "..."}
```

### Pattern 4: Event Emission

```python
await _emit_event("QUOTE_GENERATED", {
    "rfq_id": rfq_id,
    "part": part_name,
    "unit_price": quote_payload.unit_price,
    "lead_time": quote_payload.lead_time_days,
})
```

### Pattern 5: Error Handling

```python
try:
    # Attempt LLM-based quote generation
    result = await llm_generate_quote(...)
except Exception as exc:
    logger.warning("LLM failed (%s), using fallback", exc)
    # Fallback to rule-based logic
    result = fallback_quote(...)
```

---

## Troubleshooting

### Issue: Supplier not appearing in NANDA Index

**Solution:**
1. Check registration logs: `tail logs/supplier_x.log | grep "register"`
2. Verify NANDA Index is running: `curl http://localhost:6900/health`
3. Check registration payload has valid `skills` and `skill_descriptions`
4. Verify port is not in use: `lsof -i :6011`

### Issue: RFQ receives no response

**Solution:**
1. Check supplier health: `curl http://localhost:6011/health`
2. Verify envelope structure matches `shared/message_types.py`
3. Check supplier logs for errors: `tail -f logs/supplier_x.log`
4. Ensure part name matches catalog (case-insensitive, fuzzy matching enabled)

### Issue: Counter-offer always rejected

**Solution:**
1. Check floor price: `part_info.floor_price` (default 80% of base price)
2. Verify `floor_price_pct` in your catalog (can be 0.70-0.90)
3. Log the decision: `logger.info("Floor: %.2f, Target: %.2f", floor, target)`

### Issue: Dashboard not showing supplier

**Solution:**
1. Check Event Bus connectivity: `curl http://localhost:6020/health`
2. Verify `AGENT_REGISTERED` event was emitted: `curl http://localhost:6020/events | jq`
3. Check WebSocket connection in browser console: `Dashboard → Network → WS`
4. Refresh dashboard after all services start

### Issue: LLM framework not working

**Solution:**
1. Check `OPENAI_API_KEY` is set: `echo $OPENAI_API_KEY`
2. Verify framework is installed: `pip list | grep crewai` (or langchain/autogen)
3. Check API quota/rate limits
4. Use fallback logic: Always have rule-based backup

---

## Next Steps

1. **Review existing suppliers** for implementation patterns
2. **Create your catalog** with realistic pricing and specs
3. **Choose framework** based on complexity needs
4. **Implement endpoints** following the template
5. **Test thoroughly** with manual curl commands
6. **Run integration test** with full cascade
7. **Monitor dashboard** for visualization

For more details, see:
- [Architecture Guide](ARCHITECTURE.md) — System design and protocols
- [Feature Reference](FEATURES.md) — Hero feature documentation
- [Semantic Resolver](../SEMANTIC_RESOLVER_IMPLEMENTATION.md) — Discovery mechanism
