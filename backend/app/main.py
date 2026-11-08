"""FastAPI application factory."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import AppContext
from app.api.v1.routes import VERSION, router
from app.core.config import Settings, get_settings
from app.core.errors import AppError, error_body
from app.db.repository import Repository
from app.jobs.runner import JobRunner
from app.services.groq_client import GroqLLMClient, LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("n2")


def create_app(settings: Settings | None = None, client: LLMClient | None = None,
               repo: Repository | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        r = repo or Repository(settings.db_path)
        c = client or GroqLLMClient(settings)
        runner = JobRunner(r, c, settings)
        runner.recover_on_startup()
        app.state.ctx = AppContext(settings=settings, repo=r, client=c, runner=runner)
        missing = settings.missing_configuration()
        if missing:
            log.warning("configuration incomplete; missing: %s (values are never logged)", ", ".join(missing))
        yield
        await runner.shutdown()
        if repo is None:
            r.close()

    app = FastAPI(title="N² Agentic Extraction Arena", version=VERSION, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

    @app.exception_handler(AppError)
    async def app_error(_req: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def req_validation(_req: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=error_body("request_invalid", "Request validation failed",
                                                                 jsonable(exc.errors())))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_req: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_body("http_error", str(exc.detail)))

    @app.exception_handler(Exception)
    async def unhandled(_req: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content=error_body("internal_error", "Unexpected server error"))

    app.include_router(router)

    # Optionally serve the built frontend (used by the Docker image) from the same origin as the API.
    static_dir = os.getenv("STATIC_DIR")
    if static_dir and (Path(static_dir) / "index.html").is_file():
        _mount_frontend(app, Path(static_dir).resolve())
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the single-page app: real files when they exist, index.html for client-side routes."""
    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index)


def jsonable(obj):
    import json
    return json.loads(json.dumps(obj, default=str))


app = create_app()
