"""Local explanation API. Read-only reports; no Spark, model training or allocation routes."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .contracts import (
    AssistantError,
    EvaluationSummary,
    ExplainRequest,
    Explanation,
    Fact,
    Health,
    ReportSummary,
)
from .engine import ExplanationEngine
from .evidence import EvidenceStore
from .ollama import OllamaAdapter


class BodyLimit:
    def __init__(self, app, limit=8192):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request body exceeds 8192 bytes.",
                            "retryable": False,
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(store=None, adapter=None):
    engine = ExplanationEngine(store or EvidenceStore(), adapter or OllamaAdapter())

    @asynccontextmanager
    async def lifespan(app):
        yield
        if hasattr(engine.adapter, "close"):
            engine.adapter.close()

    app = FastAPI(
        title="Synthetic retention evidence assistant", version="0.4.0", lifespan=lifespan
    )
    app.add_middleware(BodyLimit)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.exception_handler(AssistantError)
    async def controlled_error(request: Request, exc: AssistantError):
        return JSONResponse({"error": exc.body.model_dump()}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Never echo arbitrary input, exception details or local filesystem paths.
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Use a valid question, approved scenario and execution mode.",
                    "retryable": False,
                }
            },
            status_code=422,
        )

    @app.get("/health", response_model=Health)
    def health():
        return {
            "status": "ok",
            "report_validated": True,
            "ollama_status": "not_probed",
            "local_only": True,
        }

    @app.get("/report-summary", response_model=ReportSummary)
    def summary():
        return engine.store.summary()

    @app.post("/explain", response_model=Explanation)
    def explain(request: ExplainRequest):
        return engine.explain(request)

    @app.get("/evidence/{reference:path}", response_model=Fact)
    def evidence(reference: str):
        return engine.store.fact(reference)

    @app.get("/evaluation-summary", response_model=EvaluationSummary)
    def evaluation():
        path = Path(__file__).resolve().parents[3] / "reports/stage4/evaluation-summary.json"
        if not path.exists():
            return EvaluationSummary(status="not_executed")
        try:
            raw = path.read_bytes()
            if len(raw) > 65536:
                raise ValueError("Summary too large")
            result = EvaluationSummary.model_validate(json.loads(raw))
            if set(result.strategies) != {"deterministic", "basic", "bound"}:
                result.status = "incomplete"
            return result
        except (OSError, ValueError, ValidationError) as exc:
            raise AssistantError(
                "invalid_evaluation", "Recorded evaluation is missing or incompatible.", 503
            ) from exc

    @app.get("/", response_class=HTMLResponse)
    def ui():
        return Path(__file__).with_name("index.html").read_text(encoding="utf-8")

    return app
