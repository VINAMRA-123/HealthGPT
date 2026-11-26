
import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.exc import SQLAlchemyError
from app.api.food_search import router as food_search_router
from app.api.profiles import router as profiles_router
from app.api.meals import router as meals_router
from app.api.chat import router as chat_router
from app.db import check_database_connection
from app.ai.tracing import configure_tracing

logger = logging.getLogger(__name__)

# Turns on LangSmith tracing only when it is fully configured in the env.
configure_tracing()

app = FastAPI(
    title="HealthGPT API",
    description="A multi-agent personal health and nutrition platform",
    version="0.1.0",
)

frontend_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_URL", "").split(",")
    if origin.strip()
]

# Compress JSON responses (meal lists, summaries, food search) over the wire.
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        *frontend_origins,
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router)
app.include_router(meals_router)
app.include_router(food_search_router)
app.include_router(chat_router)

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "healthgpt-api",
    }


@app.get("/api/v1/db-check", tags=["System"])
def database_check():
    try:
        result = check_database_connection()
        return {
            "status": "connected",
            "database_test": result,
        }
    except SQLAlchemyError:
        logger.exception("HealthGPT database connection failed")
        raise HTTPException(
            status_code=503,
            detail="Database connection failed. Check the server terminal.",
        )
