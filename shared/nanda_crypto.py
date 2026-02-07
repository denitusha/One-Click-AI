"""Ed25519 signature utilities for NANDA AgentAddr and AgentFacts."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from typing import Optional

# ---------------------------------------------------------------------------
# Lightweight Ed25519-compatible signing using HMAC (demo-grade).
# In production this would use nacl/cryptography Ed25519 keys.
# The abstraction is the same: sign(payload, key) -> hex, verify(payload, sig, key) -> bool
# ---------------------------------------------------------------------------

_REGISTRY_SECRET = os.getenv("NANDA_SIGNING_KEY", secrets.token_hex(32))


def _canonical(obj: dict) -> bytes:
    """Deterministic JSON serialisation for signing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign_document(payload: dict, signing_key: str | None = None) -> str:
    """Return an Ed25519-style hex signature over the payload."""
    key = (signing_key or _REGISTRY_SECRET).encode()
    data = _canonical(payload)
    return hashlib.blake2b(data, key=key, digest_size=32).hexdigest()


def verify_signature(payload: dict, signature: str, signing_key: str | None = None) -> bool:
    """Verify a signature produced by sign_document."""
    expected = sign_document(payload, signing_key)
    return secrets.compare_digest(expected, signature)


def generate_agent_keypair() -> tuple[str, str]:
    """Generate a (private_key, public_key_id) pair for an agent."""
    private = secrets.token_hex(32)
    pub_id = f"key-{hashlib.sha256(private.encode()).hexdigest()[:16]}"
    return private, pub_id
