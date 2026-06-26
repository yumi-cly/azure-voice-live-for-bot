from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.exceptions import DemoAppError
from app.routes.api import router as api_router
from app.services.mcp_server import create_mcp_app, mcp
from app.services.trace_store import record_trace


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
settings = get_settings()
mcp_http_app = create_mcp_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="azure-voice-live-for-bot", lifespan=lifespan)
allowed_origins = settings.allowed_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials="*" not in allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(DemoAppError)
async def demo_error_handler(_: Request, exc: DemoAppError) -> JSONResponse:
    record_trace(
        channel="event",
        kind="http_error",
        level="error",
        title=f"HTTP {exc.status_code}",
        message=exc.detail,
        payload={"status_code": exc.status_code, "error": exc.detail},
    )
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.detail})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = str(exc.detail)
    record_trace(
        channel="event",
        kind="http_error",
        level="error" if exc.status_code >= 500 else "warning",
        title=f"HTTP {exc.status_code}",
        message=message,
        payload={"status_code": exc.status_code, "detail": exc.detail},
    )
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    record_trace(
        channel="event",
        kind="validation_error",
        level="warning",
        title="HTTP 422",
        message="Request validation failed.",
        payload={"status_code": 422, "errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content={"ok": False, "error": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    record_trace(
        channel="event",
        kind="unhandled_error",
        level="error",
        title="HTTP 500",
        message=str(exc),
        payload={"status_code": 500, "error": str(exc), "type": type(exc).__name__},
    )
    return JSONResponse(status_code=500, content={"ok": False, "error": "Internal broker error."})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "broker"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", mcp_http_app, name="mcp")
