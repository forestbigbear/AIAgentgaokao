import logging
from contextlib import asynccontextmanager

import pymysql
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.agents.repository import WorkflowRepository
from app.agents.routes import router as workflow_router
from app.agents.scoring import ScoringPolicy
from app.agents.workflow import WorkflowService
from app.api.responses import register_error_handlers, success
from app.api.routes import router
from app.api.schemas import ApiEnvelope
from app.core.config import PROJECT_ROOT, get_settings
from app.core.logging import configure_logging
from app.core.model_config import ModelConfigStore
from app.db.connection import Database
from app.knowledge.models import ModelGateway
from app.knowledge.config_routes import router as model_config_router
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.routes import router as knowledge_router
from app.knowledge.service import KnowledgeService


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.model_config_store = ModelConfigStore(PROJECT_ROOT / ".env")
    app.state.database = Database(settings)
    app.state.knowledge_service = KnowledgeService(
        KnowledgeRepository(app.state.database), ModelGateway(settings), settings
    )
    app.state.workflow_service = WorkflowService(
        WorkflowRepository(app.state.database), app.state.knowledge_service,
        ScoringPolicy.from_settings(settings),
    )
    logger.info("Application started")
    yield
    logger.info("Application stopped")


app = FastAPI(
    title="高考志愿智能填报系统 API",
    description="本科毕业设计基础服务；推荐结果仅供决策参考，不保证录取。",
    version="0.1.0",
    lifespan=lifespan,
)
register_error_handlers(app)
app.include_router(router)
app.include_router(knowledge_router)
app.include_router(model_config_router)
app.include_router(workflow_router)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/static/index.html")


@app.get("/api/health", response_model=ApiEnvelope, tags=["health"])
def health():
    return success({"status": "ok"})


@app.get("/api/health/db", response_model=ApiEnvelope, tags=["health"])
def database_health(request: Request):
    try:
        result = request.app.state.database.check_connection()
    except (pymysql.MySQLError, OSError) as exc:
        logger.warning("Database health check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="MySQL unavailable or database missing") from exc
    return success({"status": result["probe"], "database": result["database_name"]})

