"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.upload import router as upload_router
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("CSV Sync Server started")
    yield
    logger.info("CSV Sync Server stopped")


app = FastAPI(
    title="CSV Sync Server",
    description="A RESTful API for uploading and managing CSV files",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload_router)


if __name__ == "__main__":
    import uvicorn
    from app.core.config import HOST, PORT
    uvicorn.run(app, host=HOST, port=PORT)
