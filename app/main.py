import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.auth_routes import router as auth_router
from app.api.repo_routes import router as repo_router
from app.api.search_routes import router as search_router
from app.api.chat_routes import router as chat_router
from app.api.graph_routes import router as graph_router
from app.api.system_routes import router as system_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database
    init_db()
    print(f"[+] {settings.APP_NAME} v{settings.VERSION} initialized.")
    print(f"[+] Configured Gemini Model: {settings.GEMINI_MODEL}")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Codebase Intelligence & RAG System powered by Gemini 3.8 Flash",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(repo_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(graph_router)
app.include_router(system_router)

# Mount Static Files
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "model": settings.GEMINI_MODEL
    }
