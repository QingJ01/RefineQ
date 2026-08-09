"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
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
from refineq.api.routers.calendar import router as calendar_router
from refineq.api.routers.health import router as health_router
from refineq.api.routers.home import router as home_router
from refineq.api.routers.learning import router as learning_router
from refineq.api.routers.learning import workspace_router as workspace_learning_router
from refineq.api.routers.materials import library_router as library_materials_router
from refineq.api.routers.materials import router as materials_router
from refineq.api.routers.materials import workspace_router as workspace_materials_router
from refineq.api.routers.projects import router as projects_router
from refineq.api.routers.settings import router as settings_router
from refineq.api.routers.workspaces import router as workspaces_router
from refineq.calendar.service import CalendarService
from refineq.config import Settings
from refineq.database.engine import Database
from refineq.home.events import HomeEventRepository, HomeReceiptRepository
from refineq.home.intelligence import HomeIntelligence
from refineq.home.service import HomeDispatchService
from refineq.home.tokens import HomeTokenSigner
from refineq.identity.deletion import AccountDeletionCoordinator
from refineq.identity.password_reset import (
    PasswordResetDelivery,
    build_password_reset_delivery,
)
from refineq.identity.service import IdentityService
from refineq.integrations.model_settings import PlatformModelSettingsRepository
from refineq.integrations.object_storage import ConfiguredObjectStorage
from refineq.integrations.ocr import OcrService
from refineq.integrations.repository import IntegrationRepository
from refineq.integrations.service import IntegrationTester
from refineq.knowledge.deletion import MaterialDeletionCoordinator
from refineq.knowledge.embeddings import PlatformEmbeddingService
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.intelligence import LearningIntelligenceService
from refineq.learning.personalized import TargetedPlanService
from refineq.learning.service import LearningService
from refineq.materials.service import MaterialAnalysisService
from refineq.operations.admin import AdminOperations
from refineq.storage.journey_events import JourneyEventRepository
from refineq.storage.json_store import InvalidIdentifierError
from refineq.storage.learning import LearningRepository
from refineq.storage.material_analyses import MaterialAnalysisRepository
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
    agent_intent_transport: StructuredModelTransport | None = None,
    home_classifier_transport: StructuredModelTransport | None = None,
    home_answer_transport: StructuredModelTransport | None = None,
    database: Database | None = None,
    password_reset_delivery: PasswordResetDelivery | None = None,
) -> FastAPI:
    """Build an isolated application instance for production or tests."""

    app = FastAPI(title="RefineQ", version=__version__)

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response

    app.state.settings = settings or Settings()
    app.state.database = database or Database(app.state.settings.resolved_database_url)
    app.state.database.initialize()
    app.state.admin_operations = AdminOperations(app.state.database, app.state.settings)
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
    app.state.store = SqlRecordStore(app.state.database, enforce_owner_state=True)
    app.state.projects = ProjectRepository(app.state.store)
    app.state.workspaces = WorkspaceRepository(app.state.store)
    app.state.learning = LearningRepository(app.state.store)
    app.state.material_analyses = MaterialAnalysisRepository(app.state.store)
    app.state.journey_events = JourneyEventRepository(app.state.store)
    app.state.home_events = HomeEventRepository(app.state.store)
    app.state.home_receipts = HomeReceiptRepository(app.state.store)
    app.state.calendar_service = CalendarService(
        workspaces=app.state.workspaces,
        learning=app.state.learning,
    )
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
    app.state.identity = IdentityService(app.state.database)
    app.state.password_reset_delivery = (
        password_reset_delivery
        if password_reset_delivery is not None
        else build_password_reset_delivery(app.state.settings)
    )
    app.state.account_deletions = AccountDeletionCoordinator(
        data_root=app.state.settings.data_root,
        identity=app.state.identity,
        object_storage=app.state.object_storage,
    )
    app.state.account_deletions.recover_pending()
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
        enforce_owner_state=True,
    )
    app.state.material_deletions = MaterialDeletionCoordinator(
        data_root=app.state.settings.data_root,
        knowledge=app.state.knowledge,
        object_storage=app.state.object_storage,
    )
    app.state.material_deletions.recover_pending()
    app.state.model_settings = PlatformModelSettingsRepository(
        app.state.integrations,
        allowed_hosts=app.state.settings.allowed_model_hosts,
    )
    app.state.learning_intelligence = LearningIntelligenceService(
        app.state.knowledge,
        app.state.model_settings,
        learning_model_transport or OpenAICompatibleStructuredTransport(),
    )
    app.state.material_analysis = MaterialAnalysisService(
        app.state.knowledge,
        app.state.material_analyses,
        app.state.model_settings,
        learning_model_transport
        or OpenAICompatibleStructuredTransport(timeout=90.0, max_retries=0),
    )
    app.state.targeted_plans = TargetedPlanService(
        app.state.learning,
        app.state.material_analyses,
        app.state.model_settings,
        learning_model_transport
        or OpenAICompatibleStructuredTransport(timeout=30.0, max_retries=0),
    )
    app.state.learning_service = LearningService(
        app.state.projects,
        app.state.learning,
        app.state.learning_intelligence,
        app.state.journey_events,
    )
    app.state.workspace_learning_service = LearningService(
        app.state.workspaces,
        app.state.learning,
        app.state.learning_intelligence,
        app.state.journey_events,
    )
    app.state.sessions = SessionRepository(app.state.store)
    resolved_intent_transport = agent_intent_transport
    if resolved_intent_transport is None and model_transport is None:
        resolved_intent_transport = OpenAICompatibleStructuredTransport(
            timeout=8.0,
            max_retries=0,
        )
    app.state.workspace_service = WorkspaceService(
        workspaces=app.state.workspaces,
        learning=app.state.learning,
        learning_service=app.state.workspace_learning_service,
        knowledge=app.state.knowledge,
        material_deletions=app.state.material_deletions,
        sessions=app.state.sessions,
        routing=WorkspaceRoutingIntelligence(
            app.state.model_settings,
            learning_model_transport or OpenAICompatibleStructuredTransport(),
        ),
        max_workspaces=app.state.settings.max_workspaces_per_user,
    )
    app.state.home_signer = HomeTokenSigner(
        key_path=app.state.settings.data_root / "system" / "home-action-signing.key"
    )
    app.state.home_intelligence = HomeIntelligence(
        app.state.model_settings,
        classifier=(
            home_classifier_transport
            or OpenAICompatibleStructuredTransport(timeout=5.0, max_retries=0)
        ),
        answerer=(
            home_answer_transport
            or OpenAICompatibleStructuredTransport(timeout=15.0, max_retries=1)
        ),
    )
    app.state.home_dispatch = HomeDispatchService(
        workspace_service=app.state.workspace_service,
        learning=app.state.learning,
        learning_service=app.state.workspace_learning_service,
        knowledge=app.state.knowledge,
        intelligence=app.state.home_intelligence,
        signer=app.state.home_signer,
        events=app.state.home_events,
        receipts=app.state.home_receipts,
        sessions=app.state.sessions,
    )
    app.state.agent = AgentService(
        projects=app.state.projects,
        learning=app.state.learning,
        knowledge=app.state.knowledge,
        sessions=app.state.sessions,
        model_settings=app.state.model_settings,
        transport=model_transport or OpenAICompatibleTransport(),
        intent_transport=resolved_intent_transport,
        max_sessions=app.state.settings.max_agent_sessions_per_user,
    )
    app.state.workspace_agent = AgentService(
        projects=app.state.workspaces,
        learning=app.state.learning,
        knowledge=app.state.knowledge,
        sessions=app.state.sessions,
        model_settings=app.state.model_settings,
        transport=model_transport or OpenAICompatibleTransport(),
        intent_transport=resolved_intent_transport,
        max_sessions=app.state.settings.max_agent_sessions_per_user,
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(InvalidIdentifierError, invalid_identifier_exception_handler)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(learning_router)
    app.include_router(workspace_learning_router)
    app.include_router(materials_router)
    app.include_router(library_materials_router)
    app.include_router(workspace_materials_router)
    app.include_router(agent_router)
    app.include_router(workspace_agent_router)
    app.include_router(settings_router)
    app.include_router(workspaces_router)
    app.include_router(calendar_router)
    app.include_router(home_router)
    app.include_router(admin_router)
    app.router.add_event_handler("shutdown", app.state.account_deletions.close)
    app.router.add_event_handler("shutdown", app.state.material_deletions.close)
    app.router.add_event_handler("shutdown", app.state.database.close)
    return app


app = create_app()
