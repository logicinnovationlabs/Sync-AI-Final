"""
FastAPI application entrypoint for Block E: Chunking and Embedding Pipeline

Mounts embedding API routers, configures middleware, handles startup/shutdown.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime
from typing import Dict, Any

from app.config import settings
from app.api.v1.embed import router as embed_router


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    """
    # Startup
    logger.info("Block E Chunking and Embedding Pipeline starting up...")
    
    # Database and Redis connections would be initialized here
    # await database.connect()
    # await redis_client.connect()
    
    logger.info("Block E startup complete")
    
    yield
    
    # Shutdown
    logger.info("Block E shutting down...")
    
    # Database and Redis connections would be closed here
    # await database.disconnect()
    # await redis_client.disconnect()
    
    logger.info("Block E shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Block E: Chunking and Embedding Pipeline",
    description="Text chunking, AST-based code chunking, and embedding generation pipeline",
    version="0.1.0",
    lifespan=lifespan,
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.enforce_tenant_isolation else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
            },
            "request_id": request.headers.get("X-Request-ID"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


# Mount routers
app.include_router(embed_router, prefix="/api/v1")


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "block-e-chunking",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Block E: Chunking and Embedding Pipeline",
        "version": "0.1.0",
        "description": "Text chunking, AST-based code chunking, and embedding generation",
        "docs": "/docs",
        "endpoints": {
            "POST /api/v1/embed": "Enqueue embedding for chunk IDs or document ID",
            "POST /api/v1/reembed": "Force re-embedding for tenant and/or model version",
            "GET /api/v1/embed/jobs/{job_id}": "Poll job status",
        },
    }
