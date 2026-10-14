"""API V1 : authentifiée et lecture seule par défaut."""
import logging

from fastapi import Depends, FastAPI, HTTPException, Security, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

from .logic import ClientConflict, QuotaExceeded
from .settings import Settings
from .shared_protocol import HEX_SHA256, PLATFORM, PROTOCOL_VERSION, validate_record
from .store import PostgresStore

logger = logging.getLogger(__name__)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class ContributionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: str
    platform: str
    records: list[dict] = Field(min_length=1, max_length=25)


class MaxBodySizeMiddleware:
    """ASGI limiter: rejects oversized bodies even without Content-Length."""

    def __init__(self, app, limit=65536):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        content_length = next(
            (v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"content-length"),
            None,
        )
        if content_length is not None and (
            not content_length.isdecimal() or int(content_length) > self.limit
        ):
            return await JSONResponse({"detail": "payload_too_large"}, status_code=413)(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.limit:
                    raise BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            return await JSONResponse({"detail": "payload_too_large"}, status_code=413)(scope, receive, send)


class BodyTooLarge(Exception):
    pass


def create_app(store=None, settings=None):
    cfg = settings or Settings.from_env()
    repository = store if store is not None else PostgresStore(cfg.database_url)
    app = FastAPI(
        title="Community fingerprint API",
        version="0.10.15",
        # Pas d'interface publique de découverte des routes à cette étape.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.add_middleware(MaxBodySizeMiddleware)

    @app.exception_handler(QuotaExceeded)
    def quota_handler(request, exc):
        return JSONResponse(status_code=429, content={"detail": "daily_quota_exceeded"})

    @app.exception_handler(ClientConflict)
    def conflict_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": "conflicting_client_vote"})

    @app.exception_handler(Exception)
    def server_error(request, exc):
        # Ne jamais renvoyer DATABASE_URL, la chaîne de connexion ou des tokens.
        logger.error("Server error: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "server_unavailable"})

    def require_client(raw: str | None = Security(api_key_header)):
        if not raw:
            raise HTTPException(status_code=401, detail="invalid_api_key")
        user = repository.authenticate(raw)
        if not user:
            raise HTTPException(status_code=401, detail="invalid_api_key")
        return user

    @app.get("/healthz")
    def health():
        # Readiness : pas de faux 200 si la connexion SQL ou le schéma
        # sont inaccessibles. HTTP 503 bloque la mise en ligne Railway.
        try:
            if not repository.ready():
                raise HTTPException(status_code=503, detail="database_unavailable")
        except HTTPException:
            raise
        except Exception:
            logger.warning("Healthcheck: base indisponible (%s)",
                           type(repository).__name__)
            raise HTTPException(status_code=503, detail="database_unavailable") from None
        return {"status": "ready", "writes_enabled": cfg.writes_enabled}

    @app.get("/v1/status")
    def status(user=Depends(require_client)):
        return {"schema_version": PROTOCOL_VERSION, "writes_enabled": cfg.writes_enabled,
                "min_confirmations": cfg.min_confirmations, **repository.stats(user["id"])}

    @app.post("/v1/contributions")
    def contribute(batch: ContributionBatch, user=Depends(require_client)):
        if not cfg.writes_enabled:
            raise HTTPException(status_code=403, detail="uploads_disabled_by_server")
        if batch.schema_version != PROTOCOL_VERSION or batch.platform != PLATFORM:
            raise HTTPException(status_code=422, detail="unsupported_protocol")
        if len({r.get("record_fingerprint") for r in batch.records if isinstance(r,dict)}) != len(batch.records):
            raise HTTPException(status_code=422, detail="duplicate_records_in_batch")
        try:
            for record in batch.records:
                validate_record(record)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid_record:{exc}") from None
        outcome = repository.submit(user["id"], batch.records, cfg.write_limit_day)
        return {"status": "received_unverified", **outcome}

    @app.get("/v1/answers/{question_fingerprint}")
    def answer(question_fingerprint: str, user=Depends(require_client)):
        if not HEX_SHA256.fullmatch(question_fingerprint):
            raise HTTPException(status_code=422, detail="invalid_fingerprint")
        outcome = repository.lookup(
            user["id"], question_fingerprint,
            cfg.min_confirmations, cfg.read_limit_day,
        )
        return {"question_fingerprint": question_fingerprint, **outcome}

    return app


app = create_app()
