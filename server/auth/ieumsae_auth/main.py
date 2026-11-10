import logging
from ieumsae_shared.runtime import configure_logging
from ieumsae_shared.web_security import SecurityBoundary
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import settings
from .mailer import MailDeliveryError
from .db import engine, init_db
from .routers import auth, device, user

configure_logging()
log = logging.getLogger("ieumsae.auth")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Ieumsae Auth", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(device.router)
app.include_router(user.router)


@app.exception_handler(MailDeliveryError)
async def mail_error(_: Request, __: MailDeliveryError):
    return JSONResponse({"error": "mail_unavailable"}, status_code=503)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail
    body = detail if isinstance(detail, dict) else {"code": detail}
    return JSONResponse({"error": body}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):

    return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"

    resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return resp


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):

    log.error("REQUEST_FAILED")
    return JSONResponse({"error": "internal_error"}, status_code=500)


@app.get("/auth/health")
async def health():
    return {"status": "ok"}


app.add_middleware(SecurityBoundary)
