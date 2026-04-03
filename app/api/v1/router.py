from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis, audit, auth, conversations, documents,
    legal_features, legal_sources, matters, memory, playbooks,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(matters.router)
api_router.include_router(analysis.router)
api_router.include_router(playbooks.router)
api_router.include_router(conversations.router)
api_router.include_router(memory.router)
api_router.include_router(audit.router)
api_router.include_router(legal_sources.router)
api_router.include_router(legal_features.router)
