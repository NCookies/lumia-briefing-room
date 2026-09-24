import asyncio
import contextlib
import hmac
import json
import logging
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from .config import Settings, load_settings
from .retention import purge_expired
from .schemas import DiagnosticBundle, LabelBatch, LogBatch
from .stats import DailyStats
from .storage import FileStore

log = logging.getLogger("receiver")


def _rejected_field_names(error: ValidationError) -> list[str]:
    names = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        name = next((p for p in reversed(item["loc"]) if isinstance(p, str)), "body")
        names.append(name)
    return names


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = FileStore(settings.data_dir)
    stats = DailyStats(settings.data_dir)

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

    def require_token(x_api_token: str = Header(default="")) -> None:
        if not any(hmac.compare_digest(x_api_token, token) for token in settings.api_tokens):
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

    @app.delete("/v1/installs/{install_id}", dependencies=[Depends(require_token)])
    def delete_install(install_id: UUID):
        return {"deleted": store.delete_install(install_id)}

    return app
