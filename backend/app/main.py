"""FastAPI application entry point."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.core.config import settings
from app.core.exceptions import AppException


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # ── Exception handler: AppException → ApiResponse ──────────────
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": exc.detail,
            },
        )

    # ── Request validation errors → 1001 ───────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        messages = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            messages.append(f"{field}: {error['msg']}")
        return JSONResponse(
            status_code=422,
            content={
                "code": 1001,
                "message": "参数错误",
                "data": messages,
            },
        )

    # ── Health check ───────────────────────────────────────────────
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    # ── Include routers ────────────────────────────────────────────
    app.include_router(auth_router)

    return app


app = create_app()
