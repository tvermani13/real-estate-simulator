from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_context.fastapi import install_exception_handler

from app.core.config import settings
from app.core.database import init_database
from app.core.platform import PlatformGuardMiddleware
from app.core.rate_limit import InMemoryRateLimiter, RateLimitMiddleware
from app.routes.api import router as api_router
from app.routes.product import router as product_router
from app.routes.str import router as str_router
from app.routes.str_evidence import router as str_evidence_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    if settings.environment == "production" and not settings.session_cookie_secure:
        logging.getLogger(__name__).warning(
            "Production is running with SESSION_COOKIE_SECURE disabled"
        )
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

rate_limiter = InMemoryRateLimiter()
app.state.rate_limiter = rate_limiter
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_exception_handler(app)

# Outermost: wraps ServerErrorMiddleware too, so even an uncaught 500 to a platform request is not cacheable.
_build_middleware_stack = app.build_middleware_stack
app.build_middleware_stack = lambda: PlatformGuardMiddleware(_build_middleware_stack())

app.include_router(api_router)
app.include_router(product_router)
app.include_router(str_router)
app.include_router(str_evidence_router)
