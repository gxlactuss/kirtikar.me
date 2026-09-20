import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.v1 import api_v1_router
from app.core.config import settings

logger = logging.getLogger("app.main")

BASE_DIR = Path(__file__).resolve().parent.parent


def _bootstrap_schema() -> None:
    """Bring the database up to head.

    The demo runs on a SQLite file inside a container that can be replaced at
    any time, so "the database already exists" is not a safe assumption to
    boot on. Running the migrations rather than `create_all` keeps the schema
    identical to the one the app's Postgres deployment gets, including the
    columns later migrations added.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    logger.info("database is at head")


def _warm_vision_model() -> None:
    """Load the IS-Net session before anyone asks for it.

    Loading the ONNX model takes several seconds, and without this the cost
    lands on the first visitor's run — the one time it is most visible, since
    it arrives on top of a cold container. It runs on a thread so /health can
    answer while it happens, which is what lets a keep-alive ping and an
    early visitor both get a response from a Space that has just started.
    """
    try:
        import rembg

        rembg.new_session("isnet-general-use")
        logger.info("vision model warm")
    except Exception:
        # A failed warm-up is not a failed boot: the stage builds its own
        # session and will try again, and the pipeline already degrades to a
        # non-composited photo rather than failing the run.
        logger.exception("could not warm the vision model")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.MEDIA_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    _bootstrap_schema()

    if settings.DEMO_MODE:
        # Create the shared seller now rather than letting the first request
        # pay for it, so a visitor's create is a create and nothing else.
        from app.core.demo import get_or_create_demo_seller
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            get_or_create_demo_seller(db)
        finally:
            db.close()
        logger.info("DEMO_MODE is on: unauthenticated requests resolve to the demo seller")

    threading.Thread(target=_warm_vision_model, name="warm-vision", daemon=True).start()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Seller-side publishing portal backend (Listing Factory).",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

if settings.CORS_ORIGINS:
    origins = (
        settings.CORS_ORIGINS
        if isinstance(settings.CORS_ORIGINS, list)
        else [settings.CORS_ORIGINS]
    )
    # A wildcard origin and credentials are mutually exclusive: the browser
    # rejects `Access-Control-Allow-Origin: *` on a credentialed request, so
    # asking for both is how a permissive config turns into every call
    # failing CORS. The demo sends no cookies and no Authorization header, so
    # dropping credentials on a wildcard is the combination that works.
    allow_credentials = "*" not in origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(api_v1_router)
