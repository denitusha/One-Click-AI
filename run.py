"""
Launch all services for One Click AI Supply Chain Agents.

Usage:
    python run.py          # Start all backend services
    python run.py --test   # Run a test cascade after starting services
"""

import asyncio
import os
import signal
import subprocess
import sys
import time

# Ensure project root is on PYTHONPATH
ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ["PYTHONPATH"] = ROOT
sys.path.insert(0, ROOT)

SERVICES = [
    ("Registry",     "registry.main:app",              8000, {}),
    ("Coordinator",  "coordinator.main:app",            8001, {}),
    ("Procurement",  "agents.procurement.main:app",     8010, {}),
    ("Supplier-1",   "agents.supplier.main:app",        8011, {"SUPPLIER_INSTANCE": "1"}),
    ("Supplier-2",   "agents.supplier.main:app",        8012, {"SUPPLIER_INSTANCE": "2"}),
    ("Manufacturer", "agents.manufacturer.main:app",    8013, {}),
    ("Logistics",    "agents.logistics.main:app",       8014, {}),
    ("Compliance",   "agents.compliance.main:app",      8015, {}),
    ("Resolver",     "resolver.main:app",               8016, {}),
]


LOG_DIR = os.path.join(ROOT, "logs")


def start_services():
    """Start all backend services as subprocesses."""
    os.makedirs(LOG_DIR, exist_ok=True)
    processes = []
    log_files = []
    for name, module, port, env_extra in SERVICES:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(env_extra)
        cmd = [
            sys.executable, "-m", "uvicorn", module,
            "--host", "0.0.0.0",
            "--port", str(port),
        ]
        log_path = os.path.join(LOG_DIR, f"{name.lower()}.log")
        log_f = open(log_path, "w", encoding="utf-8", errors="replace")
        print(f"  Starting {name} on :{port}... (log: logs/{name.lower()}.log)")
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log_f,
            stderr=log_f,
        )
        processes.append((name, port, proc))
        log_files.append(log_f)
    return processes, log_files


def wait_for_services(processes, timeout_per_service=30):
    """Wait until all services respond to health checks."""
    import httpx

    for name, port, proc in processes:
        url = f"http://localhost:{port}/health"
        start = time.time()
        ready = False
        while time.time() - start < timeout_per_service:
            # Check if process has crashed
            if proc.poll() is not None:
                print(f"  ERROR: {name} :{port} crashed (exit code {proc.returncode})")
                log_path = os.path.join(LOG_DIR, f"{name.lower()}.log")
                try:
                    with open(log_path, "r") as f:
                        lines = f.read().strip().split("\n")
                        for line in lines[-20:]:
                            print(f"    {line}")
                except Exception:
                    pass
                break
            try:
                r = httpx.get(url, timeout=2)
                if r.status_code == 200:
                    print(f"  {name} :{port} - ready")
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ready and proc.poll() is None:
            print(f"  WARNING: {name} :{port} did not become ready in {timeout_per_service}s")


async def run_test_cascade():
    """Trigger a test procurement cascade."""
    import httpx

    print("\n--- Triggering test cascade ---")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "http://localhost:8010/intent",
            json={"intent": "Buy all the parts required to assemble a Ferrari"},
        )
        data = resp.json()
        print(f"\nCascade result:")
        print(f"  Status:    {data.get('status')}")
        print(f"  Order:     {data.get('order', {}).get('order_id', 'N/A')}")
        print(f"  Quotes:    {data.get('quotes_received', 0)} received")
        print(f"  Best from: {data.get('best_quote', {}).get('supplier_id', 'N/A')}")
        mfg = data.get("manufacturing_result", {})
        print(f"  Mfg:       confirmed={mfg.get('confirmed')}, completion={mfg.get('estimated_completion')}")
        return data


def main():
    test_mode = "--test" in sys.argv

    print("=" * 60)
    print("  One Click AI - Supply Chain Agents")
    print("  NANDA-Native Agent Network")
    print("=" * 60)
    print()

    print("[1/3] Starting services...")
    processes, log_files = start_services()

    print("\n[2/3] Waiting for health checks...")
    time.sleep(3)  # Initial startup grace period
    wait_for_services(processes)

    print("\n[3/3] All services running!")
    print()
    print("  Dashboard:    http://localhost:3000  (run: cd frontend && npm run dev)")
    print("  Registry:     http://localhost:8000/agents")
    print("  Coordinator:  http://localhost:8001/events")
    print("  Resolver:     http://localhost:8016/health")
    print("  Procurement:  http://localhost:8010/intent")
    print(f"  Logs:         {LOG_DIR}")
    print()

    if test_mode:
        asyncio.run(run_test_cascade())

    print("\nPress Ctrl+C to stop all services.\n")
    try:
        for name, port, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        for name, port, proc in processes:
            proc.terminate()
        for name, port, proc in processes:
            proc.wait()
        for lf in log_files:
            lf.close()
        print("All services stopped.")


if __name__ == "__main__":
    main()
