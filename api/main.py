import os
import sys
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[reportMissingTypeStubs]
from pathlib import Path
from typing import Callable, Awaitable, Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from api.schema.internal.errors import APIError, AppException, DatabaseConnectionError
from api.logging_config import app_logger, error_logger, request_logger
from sqlalchemy.exc import OperationalError

from api.services.auth.dependencies import cleanup_tokens

# When running the file directly (for example from the `api/` folder in a debugger)
# Python's import machinery won't find the top-level `api` package because
# sys.path[0] is the `api/` directory. Add the project root to sys.path so
# absolute imports like `import api.routes` work regardless of CWD.
if __package__ is None:
    # When running this file directly we need to make relative imports work.
    # Add the project root to sys.path and set __package__ so package-relative
    # imports (from . import ...) resolve correctly without using absolute imports.
    project_root = os.path.dirname(p=os.path.dirname(p=os.path.abspath(path=__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Set package for relative imports
    __package__ = "api"

# Import from secundary file to prevent circular imports
from api.limiter import limiter

from slowapi.errors import RateLimitExceeded


# Local replacement for slowapi's internal handler. Using our own handler
# avoids importing a private symbol (`_rate_limit_exceeded_handler`) which
# may not be exported by the installed `slowapi` version.
async def _rate_limit_exceeded_handler(request: Request, exc: Exception):
    # Handler typed to Exception to match FastAPI's ExceptionHandler signature.
    # Use the exception text for the response detail (if it's a RateLimitExceeded
    # instance this will include useful info; otherwise fall back to str(exc)).
    detail = str(exc)
    return JSONResponse(
        status_code=429,
        content=APIError(
            error="Too many requests",
            code="RATE_LIMIT_EXCEEDED",
            detail=detail,
        ).model_dump(),
    )


from slowapi.middleware import SlowAPIMiddleware

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from api.config import CORS_ORIGINS, SECRET_KEY, SECURE_COOKIES


from api.routes import auth as auth_routes, users as users_routes, words as word_routes, leaderboard as leaderboard_routes

# Define main app function config and scheduler using a lifespan context manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure the scheduler job is registered and started
    try:
        await start_scheduler()
    except Exception:
        # If startup fails, log but continue so FastAPI can surface the error
        app_logger.exception("Failed to start scheduler during startup")

    try:
        yield
    finally:
        # Shutdown: stop scheduler and dispose DB engine to close pooled connections
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
                app_logger.info("Stopped token cleanup scheduler.")
        except Exception:
            app_logger.exception("Error stopping scheduler during shutdown")

        try:
            # Import here to avoid circular import at module import time
            from .database import engine

            engine.dispose()
            app_logger.info("Disposed SQLAlchemy engine.")
        except Exception as e:
            error_logger.exception("Error disposing DB engine during shutdown: %s", e)


app = FastAPI(lifespan=lifespan)
# Annotate as Any to avoid Pylance/pyright complaints when type stubs
# for apscheduler are missing — we still instantiate the real scheduler.
scheduler: Any = AsyncIOScheduler()

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=SECURE_COOKIES,
    same_site="lax",
)

# Setup templates and static files
BASE_DIR = Path(__file__).resolve().parent

# Define config for request limiter
app.state.limiter = limiter

# Add 429 error support for request limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Set CORS - MUST be added before routes are included
origins = CORS_ORIGINS

# Project TODOs: see root TODO.MD for the up-to-date task list.


# Exception handlers for loggers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            error=exc.message,
            code=exc.code,
            detail=getattr(exc, "detail", None),
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=APIError(
            error="Invalid request data",
            code="VALIDATION_ERROR",
            detail=exc.errors(),
        ).model_dump(),
    )


@app.exception_handler(OperationalError)
async def database_error_handler(request: Request, exc: OperationalError):
    error_logger.exception(
        {
            "method": request.method,
            "url": str(request.url),
            "error": "Database connection error",
            "detail": str(exc),
        }
    )
    raise DatabaseConnectionError()


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    error_logger.exception(
        {
            "method": request.method,
            "url": str(request.url),
            "error": str(exc),
        }
    )
    return JSONResponse(
        status_code=500,
        content=APIError(
            error="Internal server error",
            code="INTERNAL_ERROR",
        ).model_dump(),
    )


# Limiter and cors middleware
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define routers
# Include API routers from the routes package (each module exposes an APIRouter
# instance named `router`). Import names are aliased above to avoid shadowing
# module names with local symbols. Prefix with /api for API routes.
app.include_router(router=auth_routes.router, prefix="/api")
app.include_router(router=users_routes.router, prefix="/api")
app.include_router(router=word_routes.router, prefix="/api")
app.include_router(router=leaderboard_routes.router, prefix="/api")


@app.get("/email-verified")
def email_verified():
    """Serve email verified page"""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "email-verified.html"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/favicon.ico")
def favicon():
    """Serve favicon."""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "favicon.ico"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/robots.txt")
def robots():
    """Serve robots.txt."""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "robots.txt"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/legal")
def legal():
    """Serve legal.html."""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "legal.html"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/support")
def support():
    """Serve support.html."""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "support.html"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/sitemap.xml")
def sitemap():
    """Serve sitemap.xml."""
    try:
        return FileResponse(path=str(BASE_DIR / "public" / "sitemap.xml"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def well_known_devtools_json():
    """Serve Chrome DevTools configuration."""
    return JSONResponse(status_code=200, content={})


@app.get("/api/ping")
def ping():
    """Health check endpoint."""
    return JSONResponse(status_code=200, content={"status": "ok"})


async def start_scheduler() -> None:
    if not scheduler.get_job("cleanup-refresh-tokens"):  # type: ignore
        scheduler.add_job(  # type: ignore[reportUnknownMemberType]
            cleanup_tokens,
            trigger="interval",
            hours=1,
            id="cleanup-refresh-tokens",
            replace_existing=True,
        )

    if not scheduler.running:
        # scheduler.start()
        # app_logger.info("Started token cleanup scheduler.")
        pass


@app.middleware(middleware_type="http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start_time = time.time()
    client_ip = get_client_ip(request)
    path = request.url.path

    try:
        response: Response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        request_logger.info(
            "%-6s %s %s  %.1fms  %s",
            request.method,
            response.status_code,
            path,
            process_time,
            client_ip,
        )

        return response

    except Exception as exc:
        process_time = (time.time() - start_time) * 1000

        error_logger.exception(
            "%-6s %s %s  %.1fms  %s  — %s",
            request.method,
            500,
            path,
            process_time,
            client_ip,
            exc,
        )
        raise


@app.middleware(middleware_type="http")
async def apply_refreshed_tokens(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Propagate silently-rotated tokens to the outgoing response.

    When get_user_id() transparently refreshes an expired access token via
    the refresh token, it stashes the new token pair on request.state.
    FastAPI's dependency-injected Response object picks those cookies up
    automatically, but routes that return a custom Response/JSONResponse
    instance bypass that mechanism entirely — the cookies are silently
    dropped, leaving the client holding a now-revoked refresh token and
    causing an unexpected logout on the next request.

    This middleware closes that gap by calling apply_refreshed_token_cookies
    after every response, regardless of how the route returned.
    """
    response = await call_next(request)
    refreshed = getattr(request.state, "refreshed_tokens", None)
    if refreshed is not None:
        from api.services.auth.cookies import set_auth_cookies

        set_auth_cookies(tokens=refreshed, response=response)
    return response


# Get client ip for logger
def get_client_ip(request: Request) -> str:
    # If behind proxy (NGINX, Cloudflare, etc.)
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        # Format: client, proxy1, proxy2
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip

    # Fallback (direct connection)
    return request.client.host if request.client else "unknown"


@app.get(path="/api")
def read_api() -> dict[str, str]:
    return {"message": "See /docs for API documentation"}


from api.database import engine


def _check_database() -> dict[str, str]:
    """Try a lightweight DB query to verify connectivity."""
    try:
        with engine.connect() as conn:
            # Use a minimal, portable driver-level query to avoid SQLAlchemy
            # requiring a ClauseElement/text() object. This does not depend
            # on any application tables existing.
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        error_logger.exception({"health_check": "db_failure", "error": str(e)})
        return {"status": "error", "error": str(e)}


@app.get("/health")
def health() -> dict[str, bool | dict[str, dict[str, str]]]:
    """Liveness/health endpoint for load balancers and monitoring.

    Returns overall status and component details (database).
    """
    db_status = _check_database()
    overall = db_status.get("status") == "ok"
    return {"ok": overall, "components": {"database": db_status}}


@app.get("/api/health")
def api_health() -> dict[str, bool | dict[str, dict[str, str]]]:
    """API-prefixed health endpoint mirror for external API checks."""
    return health()
