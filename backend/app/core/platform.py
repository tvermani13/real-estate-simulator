"""Platform request context (platform ADR 0007, 0008, 0012).

The session edge strips every inbound ``X-Platform-*`` header, rechecks the
portal session and the workspace membership, and sends one short-lived signed
context. This module takes identity from that header only, verified against
the edge's key set over loopback, never from another header, cookie or field.

Rules that keep the legacy session and the platform context separate worlds:

- A request that carries ``X-Platform-Context`` is a platform request and its
  result is final. A refused context is never retried against the legacy
  session, and the legacy cookie and bearer token are never read for it.
- While ``PLATFORM_CONTEXT`` is not ``on``, a request that carries a context is
  refused (403 ``context_not_accepted``) instead of being treated as signed
  out, so a half-configured deployment cannot silently downgrade.
- A platform write needs an ``Origin`` header (the browser always sends one on
  a cross-site write), and every response to a platform request is
  ``private, no-store``.

Replay protection for writes is the verifier's in-memory ``jti`` cache. It is
sufficient only while Hearthline runs one process behind private transport,
which the container does (``--workers 1``); a second worker needs a shared cache.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from platform_context import CONTEXT_HEADER, Decision, Verifier, denial_body, owner_of
from starlette.types import ASGIApp, Message, Receive, Scope as ASGIScope, Send

from app.core.config import settings

MODULE_ID = "hearthline"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "[::1]"})  # literal addresses only: a name could resolve elsewhere
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class PlatformIdentity:
    workspace_id: str
    owner_sub: str
    role: str
    acr: str


def carries_context(headers: Any) -> bool:
    """Whether the request presents a platform context at all, even an empty or unusable one."""
    return CONTEXT_HEADER in headers


def enabled() -> bool:
    return settings.platform_context.strip().lower() == "on"


def jwks_url() -> str | None:
    """The edge key set is read over loopback only. Anything else is a misconfiguration."""
    raw = (settings.platform_jwks_url or "").strip()
    try:
        url = urlsplit(raw)
        host = (url.hostname or "").lower()
        host = f"[{host}]" if ":" in host else host
        if url.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS or url.username or url.password:
            return None
        return raw
    except ValueError:
        return None


_verifier: tuple[str, Verifier] | None = None
_verifier_lock = threading.Lock()


def _configured_verifier() -> Verifier | None:
    """One verifier per key set URL, created under a lock so two first requests share one replay cache."""
    global _verifier
    url = jwks_url()
    if url is None:
        return None
    with _verifier_lock:
        if _verifier is None or _verifier[0] != url:
            _verifier = (url, Verifier(MODULE_ID, jwks_url=url, contract_version="1"))
        return _verifier[1]


def _deny(status: int, code: str) -> Decision:
    return Decision(False, status, code)


def resolve(headers: list[str], method: str, verifier: Verifier | None = None) -> tuple[PlatformIdentity | None, Decision | None]:
    """Verify the context a request carries and reduce it to the identity this app needs.

    The decision order is the contract's: signature and structure, lifetime,
    expiry, audience and replay, then entitlement. Only a user context is
    accepted: this app defines no service scopes.
    """
    if not enabled():
        return None, _deny(403, "context_not_accepted")
    if len(headers) != 1:
        # Two header fields could be read differently by the edge and by this app.
        return None, _deny(401, "context_invalid")
    active = verifier or _configured_verifier()
    if active is None:
        return None, _deny(503, "context_unavailable")
    decision, context = active.decide(headers[0], {"action": "hearthline", "method": method})
    if not decision.allow:
        # An unknown-resource 404 never applies to a request without a resource; keep it a refusal.
        status = 403 if decision.status == 404 else decision.status
        return None, _deny(status or 401, decision.code or "context_invalid")
    if context is None or context.get("typ") != "user":
        return None, _deny(403, "scope_insufficient")
    return PlatformIdentity(context["ws"]["id"], owner_of(context), context["ws"]["role"], context["acr"]), None


def _origin_allowed(origins: list[bytes]) -> bool:
    """A platform write carries exactly one Origin, equal to the configured app origin.

    With no ``PLATFORM_ORIGIN`` configured no origin matches, so platform writes stay refused until
    the deployment names the origin the edge serves.
    """
    expected = settings.platform_origin.strip().rstrip("/")
    return len(origins) == 1 and bool(expected) and origins[0].decode("latin-1").rstrip("/") == expected


class PlatformGuardMiddleware:
    """Exact Origin on platform writes, and no caching of anything a platform request returns.

    It wraps the whole application, outside Starlette's error handling, so an uncaught error
    response is private and uncacheable too."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {name.decode("latin-1").lower(): value for name, value in scope["headers"]}
        if CONTEXT_HEADER not in headers:
            await self.app(scope, receive, send)
            return
        origins = [value for name, value in scope["headers"] if name == b"origin"]
        if scope["method"] in UNSAFE_METHODS and not _origin_allowed(origins):
            body = json.dumps(denial_body(_deny(403, "origin_required"))).encode()
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"application/json"), (b"cache-control", b"private, no-store"),
                (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return

        async def guarded(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message = {**message, "headers": [*kept, (b"cache-control", b"private, no-store")]}
            await send(message)

        await self.app(scope, receive, guarded)
