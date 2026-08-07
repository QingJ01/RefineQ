"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from refineq import __version__
from refineq.agent.service import AgentService, ModelTransport, OpenAICompatibleTransport
from refineq.agent.structured import (
    OpenAICompatibleStructuredTransport,
    StructuredModelTransport,
)
from refineq.api.errors import (
    http_exception_handler,
    invalid_identifier_exception_handler,
    request_validation_exception_handler,
)
from refineq.api.limits import (
    RequestBodyLimitMiddleware,
    RequestLimitMiddleware,
    SlidingWindowRateLimiter,
    UploadAdmissionController,
)
from refineq.api.routers.admin import router as admin_router
from refineq.api.routers.agent import router as agent_router
from refineq.api.routers.agent import workspace_router as workspace_agent_router
from refineq.api.routers.auth import router as auth_router
from refineq.api.routers.health import router as health_router
from refineq.api.routers.learning import router as learning_router
from refineq.api.routers.learning import workspace_router as workspace_learning_router
from refineq.api.routers.materials import router as materials_router
from refineq.api.routers.materials import workspace_router as workspace_materials_router
from refineq.api.routers.projects import router as projects_router
from refineq.api.routers.settings import router as settings_router
from refineq.api.routers.workspaces import router as workspaces_router
from refineq.config import Settings
from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.integrations.model_settings import PlatformModelSettingsRepository
from refineq.integrations.object_storage import ConfiguredObjectStorage
from refineq.integrations.ocr import OcrService
from refineq.integrations.repository import IntegrationRepository
from refineq.integrations.service import IntegrationTester
from refineq.knowledge.embeddings import PlatformEmbeddingService
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.intelligence import LearningIntelligenceService
from refineq.learning.service import LearningService
from refineq.storage.json_store import InvalidIdentifierError
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository
from refineq.storage.sessions import SessionRepository
from refineq.storage.sql_store import SqlRecordStore
from refineq.storage.workspaces import WorkspaceRepository
from refineq.workspaces.intelligence import WorkspaceRoutingIntelligence
from refineq.workspaces.service import WorkspaceService


def create_app(
    settings: Settings | None = None,
    *,
    model_transport: ModelTransport | None = None,
    learning_model_transport: StructuredModelTransport | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""

    app = FastAPI(title="RefineQ", version=__version__)
    app.state.settings = settings or Settings()
    app.state.database = database or Database(app.state.settings.resolved_database_url)
    app.state.database.initialize()
    app.state.rate_limiter = SlidingWindowRateLimiter()
    app.state.upload_admission = UploadAdmissionController(
        max_global=app.state.settings.material_upload_max_concurrent_global,
        max_per_owner=app.state.settings.material_upload_max_concurrent_per_user,
    )
    app.add_middleware(
        RequestLimitMiddleware,
        limiter=app.state.rate_limiter,
        auth_limit=app.state.settings.auth_rate_limit_requests,
        mutation_limit=app.state.settings.mutation_rate_limit_requests,
        window_seconds=app.state.settings.rate_limit_window_seconds,
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=app.state.settings.material_max_request_bytes,
        body_idle_timeout_seconds=app.state.settings.material_upload_body_idle_timeout_seconds,
        body_total_timeout_seconds=app.state.settings.material_upload_body_total_timeout_seconds,
        admission=app.state.upload_admission,
    )
    app.state.store = SqlRecordStore(app.state.database)
    app.state.projects = ProjectRepository(app.state.store)
    app.state.workspaces = WorkspaceRepository(app.state.store)
    app.state.learning = LearningRepository(app.state.store)
    app.state.integrations = IntegrationRepository(
        app.state.database,
        encryption_key=app.state.settings.model_encryption_key,
        key_path=app.state.settings.data_root / "system" / "integration-encryption.key",
        allowed_model_hosts=app.state.settings.allowed_model_hosts,
        allowed_object_storage_hosts=app.state.settings.allowed_object_storage_hosts,
    )
    app.state.integration_tester = IntegrationTester(app.state.integrations)
    app.state.embedding_service = PlatformEmbeddingService(app.state.integrations)
    app.state.object_storage = ConfiguredObjectStorage(
        app.state.integrations,
        data_root=app.state.settings.data_root,
    )
    app.state.ocr = OcrService(
        app.state.integrations,
        max_pages=app.state.settings.material_ocr_max_pages,
        max_chars=app.state.settings.material_max_extracted_chars,
        max_images_per_request=app.state.settings.material_ocr_max_images_per_request,
        max_page_pixels=app.state.settings.material_ocr_max_page_pixels,
        max_total_pixels=app.state.settings.material_ocr_max_total_pixels,
        max_image_bytes=app.state.settings.material_ocr_max_image_bytes,
    )
    app.state.knowledge = KnowledgeIndex(
        app.state.database,
        embedder=app.state.embedding_service,
    )
    app.state.model_settings = PlatformModelSettingsRepository(
        app.state.integrations,
        allowed_hosts=app.state.settings.allowed_model_hosts,
    )
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
        object_storage=app.state.object_storage,
        routing=WorkspaceRoutingIntelligence(
            app.state.model_settings,
            learning_model_transport or OpenAICompatibleStructuredTransport(),
        ),
        max_workspaces=app.state.settings.max_workspaces_per_user,
    )
    app.state.sessions = SessionRepository(app.state.store)
    app.state.agent = AgentService(
        projects=app.state.projects,
        learning=app.state.learning,
        knowledge=app.state.knowledge,
        sessions=app.state.sessions,
        model_settings=app.state.model_settings,
        transport=model_transport or OpenAICompatibleTransport(),
        max_sessions=app.state.settings.max_agent_sessions_per_user,
    )
    app.state.workspace_agent = AgentService(
        projects=app.state.workspaces,
        learning=app.state.learning,
        knowledge=app.state.knowledge,
        sessions=app.state.sessions,
        model_settings=app.state.model_settings,
        transport=model_transport or OpenAICompatibleTransport(),
        max_sessions=app.state.settings.max_agent_sessions_per_user,
    )
    app.state.identity = IdentityService(app.state.database)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(InvalidIdentifierError, invalid_identifier_exception_handler)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(learning_router)
    app.include_router(workspace_learning_router)
    app.include_router(materials_router)
    app.include_router(workspace_materials_router)
    app.include_router(agent_router)
    app.include_router(workspace_agent_router)
    app.include_router(settings_router)
    app.include_router(workspaces_router)
    app.include_router(admin_router)
    app.router.add_event_handler("shutdown", app.state.database.close)
    return app


app = create_app()
