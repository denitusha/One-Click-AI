#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# OneClickAI Supply-Chain Agent Network — Full Stack Startup Script
# ═══════════════════════════════════════════════════════════════════════════
#
# Starts all services in the correct order:
#   1. NANDA Index        (port 6900)
#   2. Event Bus          (port 6020)
#   3. Supplier A (CrewAI)  (port 6001)
#   4. Supplier B (Custom)  (port 6002)
#   5. Supplier C (LangChain) (port 6003)
#   6. Logistics Agent    (port 6004)
#   7. Procurement Agent  (port 6010)
#   8. Supplier D (CrewAI - Aluminum)  (port 6005)
#   9. Supplier E (LangChain - Packaging)  (port 6006)
#  10. Dashboard (React)  (port 5173)
#
# Usage:
#   ./start_all.sh          Start all services (background)
#   ./start_all.sh --no-dashboard   Skip the React dashboard
#   ./start_all.sh --stop   Kill all running services
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PIDS_FILE="$SCRIPT_DIR/.service_pids"
LOG_DIR="$SCRIPT_DIR/logs"
NO_DASHBOARD=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --stop)
            echo "Stopping all services..."
            if [ -f "$PIDS_FILE" ]; then
                while read -r pid name; do
                    if kill -0 "$pid" 2>/dev/null; then
                        echo "  Stopping $name (PID $pid)"
                        kill "$pid" 2>/dev/null || true
                    fi
                done < "$PIDS_FILE"
                rm -f "$PIDS_FILE"
            fi
            # Also kill by port as a safety net
            for port in 6900 6020 6001 6002 6003 6004 6005 6007 6008 6009 6010; do
                lsof -ti ":$port" 2>/dev/null | xargs kill 2>/dev/null || true
            done
            echo "All services stopped."
            exit 0
            ;;
        --no-dashboard)
            NO_DASHBOARD=true
            ;;
    esac
done

# Create log directory
mkdir -p "$LOG_DIR"

# Clean up old PID file
rm -f "$PIDS_FILE"

# ── Kill any leftover processes on our ports ─────────────────────────────
ALL_PORTS=(6900 6020 6001 6002 6003 6004 6005 6007 6008 6009 6010)
stale_found=false
for port in "${ALL_PORTS[@]}"; do
    pids=$(lsof -ti ":$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        stale_found=true
        echo "$pids" | xargs kill 2>/dev/null || true
    fi
done
if [ "$stale_found" = true ]; then
    echo -e "${YELLOW}[ WARN ]${NC} Killed leftover processes on service ports. Waiting for cleanup..."
    sleep 2
fi

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Colour

log() { echo -e "${BLUE}[startup]${NC} $1"; }
success() { echo -e "${GREEN}[  OK  ]${NC} $1"; }
warn() { echo -e "${YELLOW}[ WARN ]${NC} $1"; }
fail() { echo -e "${RED}[FAILED]${NC} $1"; }

# ── Wait for a service to become healthy ──────────────────────────────────
wait_for_health() {
    local url="$1"
    local name="$2"
    local max_wait="${3:-30}"
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            success "$name is healthy ($url)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    warn "$name did not respond within ${max_wait}s (may still be starting)"
    return 1
}

# ── Start a Python service ────────────────────────────────────────────────
# Runs `python3 <script>` from <working_dir> so uvicorn module refs resolve.
start_service() {
    local name="$1"
    local script="$2"         # Python script to run (e.g. "registry.py")
    local working_dir="$3"    # Directory to cd into before running
    local health_url="$4"
    local colour="$5"
    local log_file="$LOG_DIR/${name}.log"

    echo -e "${colour}▶ Starting ${name}...${NC}"

    (cd "$working_dir" && python3 "$script") > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid $name" >> "$PIDS_FILE"

    sleep 1

    if ! kill -0 "$pid" 2>/dev/null; then
        fail "$name failed to start. Check $log_file"
        return 1
    fi

    if [ -n "$health_url" ]; then
        wait_for_health "$health_url" "$name" 15
    else
        success "$name started (PID $pid)"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     OneClickAI Supply-Chain Agent Network — Starting...     ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. NANDA Lean Index ───────────────────────────────────────────────────
start_service \
    "nanda-index" \
    "registry.py" \
    "$SCRIPT_DIR/nanda-index" \
    "http://localhost:6900/health" \
    "$MAGENTA"

# ── 2. Event Bus ──────────────────────────────────────────────────────────
start_service \
    "event-bus" \
    "server.py" \
    "$SCRIPT_DIR/event-bus" \
    "http://localhost:6020/health" \
    "$YELLOW"

# ── 3. Supplier A (CrewAI) ────────────────────────────────────────────────
start_service \
    "supplier-a" \
    "supplier_crewai.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6001/health" \
    "$GREEN"

# ── 4. Supplier B (Custom Python) ────────────────────────────────────────
start_service \
    "supplier-b" \
    "supplier_custom.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6002/health" \
    "$GREEN"

# ── 5. Supplier C (LangChain) ────────────────────────────────────────────
start_service \
    "supplier-c" \
    "supplier_langchain.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6003/health" \
    "$GREEN"

# ── 6. Logistics Agent (AutoGen) ─────────────────────────────────────────
start_service \
    "logistics" \
    "agent.py" \
    "$SCRIPT_DIR/agents/logistics" \
    "http://localhost:6004/health" \
    "$CYAN"

# ── 7. Procurement Agent (LangGraph) ─────────────────────────────────────
start_service \
    "procurement" \
    "server.py" \
    "$SCRIPT_DIR/agents/procurement" \
    "http://localhost:6010/health" \
    "$BLUE"

# ── 8. Supplier D (Aluminum & Materials - CrewAI) ─────────────────────────
start_service \
    "supplier-d" \
    "supplier_aluminum.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6005/health" \
    "$GREEN"

# ── 9. Supplier F (Pirelli Tires - CrewAI) ───────────────────────────────
start_service \
    "supplier-f" \
    "supplier_pirelli.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6007/health" \
    "$GREEN"

# ── 10. Supplier G (Michelin Tires - LangChain) ───────────────────────────
start_service \
    "supplier-g" \
    "supplier_michelin.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6008/health" \
    "$GREEN"

# ── 11. Supplier H (Brakes - Custom Python) ───────────────────────────────
start_service \
    "supplier-h" \
    "supplier_brakes.py" \
    "$SCRIPT_DIR/agents/supplier" \
    "http://localhost:6009/health" \
    "$GREEN"

# ── 12. Dashboard (React + Vite) ──────────────────────────────────────────
if [ "$NO_DASHBOARD" = false ]; then
    echo -e "${MAGENTA}▶ Starting dashboard...${NC}"
    cd "$SCRIPT_DIR/dashboard"
    if [ -d "node_modules" ]; then
        npm run dev > "$LOG_DIR/dashboard.log" 2>&1 &
        dashboard_pid=$!
        echo "$dashboard_pid dashboard" >> "$PIDS_FILE"
        cd "$SCRIPT_DIR"
        sleep 3
        if kill -0 "$dashboard_pid" 2>/dev/null; then
            success "Dashboard started (PID $dashboard_pid) — http://localhost:3000"
        else
            warn "Dashboard may have failed. Check $LOG_DIR/dashboard.log"
        fi
    else
        warn "Dashboard node_modules not found. Run: cd dashboard && npm install"
        cd "$SCRIPT_DIR"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              All Services Started Successfully              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Services:"
echo "    NANDA Index .............. http://localhost:6900"
echo "    Event Bus ............... http://localhost:6020 (WS: ws://localhost:6020/ws)"
echo "    Supplier A (CrewAI) ..... http://localhost:6001"
echo "    Supplier B (Custom) ..... http://localhost:6002"
echo "    Supplier C (LangChain) .. http://localhost:6003"
echo "    Logistics (AutoGen) ..... http://localhost:6004"
echo "    Supplier D (CrewAI) ..... http://localhost:6005"
echo "    Supplier F (CrewAI) ..... http://localhost:6007"
echo "    Supplier G (LangChain) .. http://localhost:6008"
echo "    Supplier H (Custom) ..... http://localhost:6009"
echo "    Procurement (LangGraph) . http://localhost:6010"
if [ "$NO_DASHBOARD" = false ]; then
echo "    Dashboard ............... http://localhost:3000"
fi
echo ""
echo "  Logs: $LOG_DIR/"
echo "  PIDs: $PIDS_FILE"
echo ""
echo "  To stop all services:  ./start_all.sh --stop"
echo "  To test the cascade:   python3 test_cascade.py"
echo ""
