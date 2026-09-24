import asyncio
import base64
import contextlib
import hmac
import ipaddress
import json
import logging
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from .alerts import Alerter, discord_sender, mask_ip
from .config import Settings, load_settings
from .ratelimit import RateLimiter
from .retention import purge_expired
from .schemas import DiagnosticBundle, LabelBatch, LogBatch
from .stats import DailyStats
from .storage import FileStore, list_labels

log = logging.getLogger("receiver")


def _rejected_field_names(error: ValidationError) -> list[str]:
    names = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        name = next((p for p in reversed(item["loc"]) if isinstance(p, str)), "body")
        names.append(name)
    return names


def _encode_cursor(key: tuple[str, str, str] | None) -> str | None:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode() if key else None


def _decode_cursor(text: str) -> tuple[str, str, str] | None:
    try:
        key = json.loads(base64.urlsafe_b64decode(text.encode()))
        return tuple(key) if isinstance(key, list) and len(key) == 3 else None
    except ValueError:
        return None


REJECTED_STATUSES = {401, 404, 405, 413, 422}
REASONS = {"requests": "요청이 너무 많음", "failures": "거부되는 요청이 반복됨"}


def client_ip(request: Request) -> str:
    """receiver 는 caddy 뒤에서만 접근되므로 caddy 가 붙인 X-Forwarded-For 의 마지막 값이 실제 클라이언트다."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None, alerter: Alerter | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = FileStore(settings.data_dir)
    stats = DailyStats(settings.data_dir)
    if alerter is None:
        url = settings.discord_webhook_url
        alerter = Alerter(discord_sender(url) if url else None)

    def on_block(ip: str, reason: str) -> None:
        alerter.notify(
            f"[lumia receiver] 차단: {mask_ip(ip)} — {REASONS.get(reason, reason)} "
            f"({settings.rate_limit_window_sec // 60}분 기준, {settings.block_sec // 60}분간 차단)"
        )

    limiter = RateLimiter(
        window_sec=settings.rate_limit_window_sec,
        max_requests=settings.rate_limit_requests,
        max_failures=settings.rate_limit_failures,
        block_sec=settings.block_sec,
        on_block=on_block,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async def purge_forever():
            while True:
                try:
                    removed = await asyncio.to_thread(purge_expired, settings.data_dir, settings.retention_days)
                    if removed:
                        log.info("purged %d expired files", removed)
                except Exception:
                    log.exception("retention purge failed")
                await asyncio.sleep(settings.purge_interval_sec)

        task = asyncio.create_task(purge_forever())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="receiver", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)
        ip = client_ip(request)
        if not limiter.allow(ip):
            return JSONResponse(
                {"detail": "too many requests"}, status_code=429, headers={"Retry-After": str(settings.block_sec)}
            )
        response = await call_next(request)
        if response.status_code in REJECTED_STATUSES:
            limiter.record_failure(ip)
        return response

    def require_token(x_api_token: str = Header(default="")) -> None:
        if not any(hmac.compare_digest(x_api_token, token) for token in settings.api_tokens):
            raise HTTPException(status_code=401, detail="invalid token")

    def require_admin(x_admin_token: str = Header(default="")) -> None:
        if not settings.admin_token:
            raise HTTPException(status_code=404, detail="not found")
        if not hmac.compare_digest(x_admin_token, settings.admin_token):
            raise HTTPException(status_code=401, detail="invalid token")

    async def parse(request: Request, endpoint: str, model: type[BaseModel]):
        raw = await request.body()
        if len(raw) > settings.max_body_bytes:
            raise HTTPException(status_code=413, detail="payload too large")
        context: dict = {}
        try:
            batch = model.model_validate(json.loads(raw), context=context)
        except (ValueError, ValidationError) as e:
            names = _rejected_field_names(e) if isinstance(e, ValidationError) else ["body"]
            await run_in_threadpool(stats.record, endpoint, len(raw), rejected_fields=names)
            detail = (
                e.errors(include_url=False, include_context=False, include_input=False)
                if isinstance(e, ValidationError)
                else "invalid json"
            )
            return None, JSONResponse({"detail": detail}, status_code=422)
        await run_in_threadpool(stats.record, endpoint, len(raw), dropped=context.get("dropped", ()))
        return batch, None

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/v1/labels", dependencies=[Depends(require_token)])
    async def post_labels(request: Request):
        batch, error = await parse(request, "labels", LabelBatch)
        if error:
            return error
        saved = await run_in_threadpool(
            store.save_labels, batch.mode, batch.installId, batch.appVersion, batch.schemaVersion,
            [item.model_dump(exclude_none=True) for item in batch.labels],
        )
        return {"saved": saved}

    @app.post("/v1/logs", dependencies=[Depends(require_token)])
    async def post_logs(request: Request):
        batch, error = await parse(request, "logs", LogBatch)
        if error:
            return error
        await run_in_threadpool(
            store.append_log, batch.mode, batch.installId,
            {"schemaVersion": batch.schemaVersion, "env": batch.env.model_dump(exclude_none=True),
             "entries": [e.model_dump(exclude_none=True) for e in batch.entries]},
        )
        return {"saved": len(batch.entries)}

    @app.post("/v1/diagnostics", dependencies=[Depends(require_token)])
    async def post_diagnostics(request: Request):
        batch, error = await parse(request, "diagnostics", DiagnosticBundle)
        if error:
            return error
        receipt = await run_in_threadpool(
            store.save_diagnostic, batch.mode, batch.installId,
            {"schemaVersion": batch.schemaVersion, "displayId": batch.displayId,
             "env": batch.env.model_dump(exclude_none=True),
             "entries": [e.model_dump(exclude_none=True) for e in batch.entries]},
        )
        return {"receiptId": receipt, "saved": len(batch.entries)}

    @app.get("/v1/admin/labels", dependencies=[Depends(require_admin)])
    def export_labels(mode: Literal["dev", "release"] = "release", after: str = "", limit: int = Query(500, ge=1, le=2000)):
        labels, last, more = list_labels(settings.data_dir, mode, _decode_cursor(after), limit)
        cursor = _encode_cursor(last)
        return {"labels": labels, "next": cursor if more else None, "cursor": cursor}

    @app.delete("/v1/installs/{install_id}", dependencies=[Depends(require_token)])
    def delete_install(install_id: UUID):
        return {"deleted": store.delete_install(install_id)}

    return app
