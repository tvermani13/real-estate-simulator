from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    method: str
    path_pattern: re.Pattern[str]
    limit: int
    window_seconds: int


RULES = (
    RateLimitRule("login", "POST", re.compile(r"/api/auth/login"), 10, 60),
    RateLimitRule("register", "POST", re.compile(r"/api/auth/register"), 5, 3600),
    RateLimitRule("risk", "POST", re.compile(r"/api/risk"), 20, 60),
    RateLimitRule(
        "property_scan",
        "POST",
        re.compile(r"/api/searches/[^/]+/scan"),
        6,
        600,
    ),
)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        *,
        rule: RateLimitRule,
        client_key: str,
        now: float | None = None,
    ) -> tuple[bool, int, int]:
        current = time.monotonic() if now is None else now
        cutoff = current - rule.window_seconds
        key = (rule.name, client_key)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= rule.limit:
                retry_after = max(1, int(rule.window_seconds - (current - events[0])) + 1)
                return False, 0, retry_after
            events.append(current)
            return True, rule.limit - len(events), 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def _matching_rule(request: Request) -> RateLimitRule | None:
    return next(
        (
            rule
            for rule in RULES
            if request.method == rule.method and rule.path_pattern.fullmatch(request.url.path)
        ),
        None,
    )


def _client_key(request: Request) -> str:
    if settings.rate_limit_trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, limiter: InMemoryRateLimiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        rule = _matching_rule(request) if settings.rate_limit_enabled else None
        if rule is None:
            return await call_next(request)

        allowed, remaining, retry_after = self.limiter.check(
            rule=rule,
            client_key=_client_key(request),
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please retry later."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rule.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rule.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
