from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.health import router as health_router
from .config import REPO_ROOT, get_settings
from .db import init_db

settings = get_settings()

app = FastAPI(title="Audiobook Studio API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# Serve the built frontend (frontend/dist) as a SPA, once it exists. In dev, the Vite
# dev server (npm run dev) serves the UI instead and this mount is simply absent.
_frontend_dist = REPO_ROOT / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="spa")
