"""FastAPI application factory — the JSON API *and* the built UI.

The UI lives in ``frontend/`` (Next.js) and is exported to static files. When
``frontend/out`` exists this app serves it at ``/``, so ``drscreen web`` is
the whole application on one port with no Node process at runtime. During UI
development you instead run ``npm run dev`` on :3000, which proxies ``/api/*``
back here; either way the session cookie stays same-origin.

The database and SMS sender load eagerly (cheap); the model checkpoint is the
one thing that can plausibly be missing on a fresh install, so a missing or
invalid checkpoint doesn't crash the app at startup. Instead
``app.state.model_error`` is set, ``/api/status`` reports it, and the UI shows
a banner — screening stays disabled until a valid checkpoint is in place and
the app is restarted.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from drscreen.config import PROJECT_ROOT, Settings
from drscreen.notify import build_sender
from drscreen.service import ScreeningService
from drscreen.storage import Database
from drscreen.web.auth import make_serializer

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="drscreen API", docs_url=None, redoc_url=None)

    app.state.settings = settings
    app.state.serializer = make_serializer(settings.secret_key)

    db = Database(settings.database_url)
    db.create_schema()
    app.state.db = db

    app.state.service = None
    app.state.model_error: str | None = None
    # Non-fundus uploads turned away since start-up (dashboard widget).
    app.state.rejected_uploads = 0
    try:
        from drscreen.inference import Predictor

        predictor = Predictor.from_checkpoint(
            settings.model_path, settings.device, tta=settings.tta,
            referral_threshold=settings.referral_threshold,
        )
        app.state.service = ScreeningService(predictor, db, build_sender(settings), settings)
        log.info("model loaded: %s", predictor.metadata.version)
    except Exception as exc:  # missing/invalid checkpoint must not crash the app
        app.state.model_error = str(exc)
        log.warning("model not loaded, screening disabled until fixed: %s", exc)

    from drscreen.web.routes import api as api_routes

    app.include_router(api_routes.router)
    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    """Serve the exported Next.js UI at ``/`` when it has been built.

    Mounted last so it never shadows ``/api/*``. If ``frontend/out`` is
    missing the API still runs on its own — that's the ``npm run dev`` setup,
    where the UI is served from :3000 instead.
    """
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    ui_dir = PROJECT_ROOT / "frontend" / "out"
    if ui_dir.is_dir():
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
        log.info("serving UI from %s", ui_dir)
        return

    log.warning("UI not built (%s missing) — serving the API only. "
                "Build it with: cd frontend && npm install && npm run build", ui_dir)

    @app.get("/")
    def ui_missing() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The web UI has not been built yet.",
                "build_it_with": "cd frontend && npm install && npm run build",
                "api_is_running": True,
            },
        )


def run(settings: Settings | None = None, host: str = "127.0.0.1", port: int = 8000,
        reload: bool = False) -> None:
    import uvicorn

    if reload:
        uvicorn.run("drscreen.web.app:create_app", factory=True, host=host, port=port,
                   reload=True)
    else:
        uvicorn.run(create_app(settings), host=host, port=port)
