from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis, audit, auth, billing, calendar, client_portal, clients,
    conversations, documents, email_intake, legal_features, legal_sources,
    matters, memory, playbooks, tasks, teams,
)

api_router = APIRouter()

# Auth
api_router.include_router(auth.router)

# Practice management core
api_router.include_router(clients.router)
api_router.include_router(matters.router)
api_router.include_router(documents.router)
api_router.include_router(tasks.router)
api_router.include_router(calendar.router)
api_router.include_router(billing.router)
api_router.include_router(teams.router)

# AI intelligence layer
api_router.include_router(analysis.router)
api_router.include_router(conversations.router)
api_router.include_router(playbooks.router)
api_router.include_router(legal_sources.router)
api_router.include_router(legal_features.router)

# Workflow & ops
api_router.include_router(memory.router)
api_router.include_router(audit.router)
api_router.include_router(email_intake.router)
api_router.include_router(client_portal.router)
