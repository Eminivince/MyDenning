from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException, app_exception_handler, generic_exception_handler
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


settings = get_settings()

app = FastAPI(
    title="MyDenning - Legal Intelligence API",
    description="Citation-backed legal copilot combining research, document intelligence, memory, and workflow automation.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (order matters - last added runs first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["http://localhost:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# API routes
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.1.0",
        "services": {
            "api": "up",
        },
    }
