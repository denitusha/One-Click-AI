"""Logistics Agent — FastAPI server entry point (alternative).

This is a thin wrapper around ``agent.py`` for consistency with the
project plan.  The primary entry point is::

    cd agents/logistics && python3 agent.py    # Port 6004

But you can also run::

    cd agents/logistics && python3 server.py   # Same thing
"""

from __future__ import annotations

import os
import sys

# Ensure project root is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Re-export the FastAPI app from agent.py
try:
    from .agent import app, PORT, HOST  # noqa: E402, F401
except ImportError:
    from agents.logistics.agent import app, PORT, HOST  # noqa: E402, F401

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
