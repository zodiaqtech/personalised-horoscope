"""
Personalised Horoscope Engine — FastAPI Application

Architecture:
  - Natal profiles: computed once per user via VedicAstroAPI, stored in MongoDB
  - Daily transit: computed locally via pyswisseph (zero API cost), cached in Redis
  - Batch cron: runs at 00:05 IST daily, generates horoscopes for all users
  - Rule engine: JSON-driven BPHS rules, loaded once at startup
  - Text: static templates, no LLM required
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from app.services.rule_engine import load_rules
from app.services.transit_service import get_redis
from app.services.scheduler import start_scheduler, stop_scheduler
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("=" * 60)
    logger.info("Personalised Horoscope Engine starting...")
    logger.info("=" * 60)

    # 1. Load BPHS rules (once)
    load_rules(settings.RULES_FILE)
    logger.info(f"Rules loaded from {settings.RULES_FILE}")

    # 2. Verify Redis
    r = get_redis()
    if r:
        logger.info("Redis: connected")
    else:
        logger.warning("Redis: NOT available — transit will use in-memory fallback")

    # 3. MongoDB
    if settings.MONGODB_ENABLED:
        from app.db.mongodb import connect_to_mongo
        await connect_to_mongo(settings.MONGODB_URI, settings.MONGODB_DB_NAME)
    else:
        logger.info("MongoDB: DISABLED (set MONGODB_ENABLED=True to enable)")

    # 4. Start midnight-IST batch scheduler
    start_scheduler()

    logger.info("Engine ready. Batch cron scheduled at 00:05 IST daily.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────
    stop_scheduler()

    if settings.MONGODB_ENABLED:
        from app.db.mongodb import disconnect_from_mongo
        await disconnect_from_mongo()

    logger.info("Engine shut down cleanly.")


app = FastAPI(
    title="Personalised Horoscope Engine",
    description=(
        "Level-2 BPHS horoscope engine.\n\n"
        "**Transit**: pyswisseph (local, zero cost, Lahiri sidereal)\n"
        "**Natal**: VedicAstroAPI (called once per user lifetime)\n"
        "**Batch**: midnight IST cron generates horoscopes for all users\n"
        "**Rules**: deterministic JSON (198 BPHS rules, 5 categories)\n"
        "**Text**: static templates — no LLM"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "Personalised Horoscope Engine",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "batch": "/api/v1/batch/status",
        "transit": "/api/v1/transit/today",
    }
