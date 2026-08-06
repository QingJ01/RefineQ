"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from refineq import __version__
from refineq.agent.service import AgentService, ModelTransport, OpenAICompatibleTransport
from refineq.agent.settings import ModelSettingsRepository
from refineq.agent.structured import (
    OpenAICompatibleStructuredTransport,
    StructuredModelTransport,
)
from refineq.api.errors import http_exception_handler, request_validation_exception_handler
from refineq.api.routers.agent import router as agent_router
from refineq.api.routers.auth import router as auth_router
from refineq.api.routers.health import router as health_router
from refineq.api.routers.learning import router as learning_router
from refineq.api.routers.learning import workspace_router as workspace_learning_router
from refineq.api.routers.materials import router as materials_router
from refineq.api.routers.projects import router as projects_router
from refineq.api.routers.settings import router as settings_router
from refineq.api.routers.workspaces import router as workspaces_router
from refineq.config import Settings
from refineq.identity.service import IdentityService
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.intelligence import LearningIntelligenceService
from refineq.learning.service import LearningService
from refineq.storage.json_store import AtomicJsonStore
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository
from refineq.storage.sessions import SessionRepository
from refineq.storage.workspaces import WorkspaceRepository
from refineq.workspaces.service import WorkspaceService


def create_app(
    settings: Settings | None = None,
    *,
    model_transport: ModelTransport | None = None,
    learning_model_transport: StructuredModelTransport | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""

    app = FastAPI(title="RefineQ", version=__version__)
    app.state.settings = settings or Settings()
    app.state.store = AtomicJsonStore(app.state.settings.data_root)
    app.state.projects = ProjectRepository(app.state.store)
    app.state.workspaces = WorkspaceRepository(app.state.store)
    app.state.learning = LearningRepository(app.state.store)
    app.state.knowledge = KnowledgeIndex(app.state.settings.data_root)
    app.state.model_settings = ModelSettingsRepository(app.state.settings.data_root)
    app.state.learning_intelligence = LearningIntelligenceService(
        app.state.knowledge,
        app.state.model_settings,
        learning_model_transport or OpenAICompatibleStructuredTransport(),
    )
    app.state.learning_service = LearningService(
        app.state.projects,
        app.state.learning,
        app.state.learning_intelligence,
    )
    app.state.workspace_learning_service = LearningService(
        app.state.workspaces,
        app.state.learning,
        app.state.learning_intelligence,
    )
    app.state.workspace_service = WorkspaceService(
        workspaces=app.state.workspaces,
        learning=app.state.learning,
        learning_service=app.state.workspace_learning_service,
        knowledge=app.state.knowledge,
    )
    app.state.sessions = SessionRepository(app.state.store)
    app.state.agent = AgentService(
        projects=app.state.projects,
        learning=app.state.learning,
        knowledge=app.state.knowledge,
        sessions=app.state.sessions,
        model_settings=app.state.model_settings,
        transport=model_transport or OpenAICompatibleTransport(),
    )
    app.state.identity = IdentityService(app.state.settings.data_root)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(learning_router)
    app.include_router(workspace_learning_router)
    app.include_router(materials_router)
    app.include_router(agent_router)
    app.include_router(settings_router)
    app.include_router(workspaces_router)
    return app


app = create_app()
