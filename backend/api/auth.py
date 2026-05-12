"""
auth.py — minimal JWT-based auth scaffold for multi-tenant Lumare.

What this layer is responsible for:

  * Verifying a bearer JWT on protected endpoints
  * Exposing a ``current_user`` dependency that returns the user id
  * Routing per-user bot instances via ``get_user_autobot(user_id)``

What it is NOT responsible for:

  * User registration / password hashing (use an external IdP — Clerk,
    Auth0, Supabase Auth, or your own /api/auth/* endpoints) — this
    file just verifies the resulting JWT
  * Authorisation rules beyond "authenticated user owns their bot"

How to wire in:

  1. Set ``LUMARE_JWT_SECRET`` in env (any long random string).
  2. Protect bot endpoints with ``Depends(current_user)``.
  3. Replace the global ``autobot`` import with ``get_user_autobot(uid)``.

Single-tenant mode (no auth) stays the default: when LUMARE_JWT_SECRET
is unset, current_user returns a fixed "default" user id and every
caller shares the same bot instance — i.e. the existing behaviour.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger


_JWT_SECRET = os.getenv("LUMARE_JWT_SECRET", "")
_JWT_ALGO = os.getenv("LUMARE_JWT_ALGO", "HS256")
_SINGLE_TENANT = _JWT_SECRET == ""

_bearer = HTTPBearer(auto_error=False)


def is_multi_tenant() -> bool:
    return not _SINGLE_TENANT


def _decode_token(token: str) -> dict:
    """Decode a JWT and return its claims. Raises HTTPException(401) on
    any failure. PyJWT is optional — install with ``pip install pyjwt``."""
    try:
        import jwt  # PyJWT
    except ImportError as exc:
        raise HTTPException(
            500,
            "Multi-tenant mode enabled (LUMARE_JWT_SECRET set) but "
            "PyJWT is not installed. Run: pip install pyjwt",
        ) from exc
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, f"invalid token: {exc}")


def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Return the authenticated user id (sub claim).

    In single-tenant mode (LUMARE_JWT_SECRET unset) this returns
    "default" without inspecting the request — preserving the existing
    no-auth dev experience.

    In multi-tenant mode, the request must include
    ``Authorization: Bearer <jwt>`` with a ``sub`` claim. We accept the
    sub as the user id.
    """
    if _SINGLE_TENANT:
        return "default"

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Bearer token required")

    claims = _decode_token(credentials.credentials)
    sub = claims.get("sub") or claims.get("user_id") or claims.get("uid")
    if not sub:
        raise HTTPException(401, "token missing sub claim")
    return str(sub)


# ---------------------------------------------------------------------------
# Per-user bot routing
# ---------------------------------------------------------------------------

# When multi-tenant, each authenticated user gets their own AutoBot
# instance. We keep a tiny LRU-ish dict here so concurrent users don't
# fight over the same singleton.

_bot_registry: dict[str, "AutoBot"] = {}


def get_user_autobot(user_id: str):
    """Return the AutoBot instance for ``user_id``, creating it lazily.

    In single-tenant mode every caller gets the same instance (the
    pre-existing module-level singleton). In multi-tenant mode each
    user_id gets a fresh AutoBot.
    """
    from backend.orchestrator.autobot import AutoBot, autobot as _singleton

    if _SINGLE_TENANT:
        return _singleton
    if user_id not in _bot_registry:
        _bot_registry[user_id] = AutoBot()
        logger.info(f"Spawned new AutoBot for user_id={user_id}")
    return _bot_registry[user_id]


def shutdown_user_autobot(user_id: str) -> None:
    """Cleanly stop and discard a user's bot. Useful on logout."""
    bot = _bot_registry.pop(user_id, None)
    if bot is not None:
        try:
            bot.stop()
        except Exception as exc:
            logger.warning(f"Error stopping bot for {user_id}: {exc}")


def active_user_count() -> int:
    """How many users currently have a bot instance in memory."""
    return len(_bot_registry)
