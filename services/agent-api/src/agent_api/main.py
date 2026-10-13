from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_api.agent.loop import AgentRunner
from agent_api.agent.runs import (
    RunManager,
    enable_create_skill_once,
    enable_file_tools_once,
    enable_read_skill_once,
    recover_interrupted_runs,
    relax_legacy_run_timeout,
)
from agent_api.api import router
from agent_api.config import Settings, get_settings
from agent_api.db import Database
from agent_api.llm import LLMClient
from agent_api.llm.openai_compat import OpenAICompatClient
from agent_api.llm.providers import ModelConfigurationError
from agent_api.schedules import ScheduleClock
from agent_api.skills import resolve_skills_dir, resolve_user_skills_dir
from agent_api.tools import ToolRegistry, default_registry
from agent_api.tracing import NoopExporter, TraceExporter
from agent_api.uploads import resolve_upload_dir


def build_llm(settings: Settings) -> LLMClient:
    return OpenAICompatClient(
        api_key=settings.dashscope_api_key or "not-configured",
        base_url=settings.dashscope_base_url,
        provider="dashscope",
    )


def create_app(
    *,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    registry: ToolRegistry | None = None,
    exporter: TraceExporter | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        await db.create_all()
        await recover_interrupted_runs(db)
        await enable_file_tools_once(db)
        await enable_read_skill_once(db)
        await enable_create_skill_once(db)
        await relax_legacy_run_timeout(db)
        tools = registry or default_registry()
        workspace_root = resolve_upload_dir(settings)
        skills_dir = resolve_skills_dir(settings)
        user_skills_dir = resolve_user_skills_dir(settings)
        runner = AgentRunner(
            db,
            llm or build_llm(settings),
            tools,
            exporter or NoopExporter(),
            workspace_root,
            skills_dir,
            user_skills_dir,
            environment=settings,
        )
        app.state.settings = settings
        app.state.db = db
        app.state.registry = tools
        app.state.workspace_root = workspace_root
        app.state.skills_dir = skills_dir
        app.state.user_skills_dir = user_skills_dir
        app.state.runs = RunManager(db, runner, settings)
        clock = ScheduleClock(db, app.state.runs)
        app.state.schedules = clock
        clock.start()
        yield
        await clock.stop()
        await app.state.runs.shutdown()
        await db.dispose()

    app = FastAPI(title=settings.agent_name, version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ModelConfigurationError)
    async def model_not_configured(request: Request, error: ModelConfigurationError):
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "model_not_configured", "message": str(error)}},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
