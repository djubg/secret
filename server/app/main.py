from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import admin, auth, license, updates
from app.core.settings import get_settings
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Simple API Hub for license actions, profile auth, and update checks. "
        "Use /hub/* endpoints for license workflows."
    ),
    openapi_tags=[
        {"name": "hub", "description": "License workflow hub: generate, activate, validate, extend, revoke, delete."},
        {"name": "auth", "description": "User registration/login/profile endpoints."},
        {"name": "updates", "description": "Desktop update metadata endpoints."},
    ],
    swagger_ui_parameters={
        "docExpansion": "none",
        "defaultModelsExpandDepth": -1,
    },
)
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)


def _ensure_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info('license_keys')"))}
        if "full_key" not in cols:
            conn.execute(text("ALTER TABLE license_keys ADD COLUMN full_key TEXT"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_license_full_key ON license_keys (full_key)"))


_ensure_schema_updates()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(license.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(updates.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/", include_in_schema=False)
def root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "app_name": settings.app_name,
            "version": app.version,
            "links": [
                {"label": "Admin Dashboard", "url": "/admin", "desc": "Generer et gerer les licences"},
                {"label": "All Keys", "url": "/admin/keys", "desc": "Voir toutes les cles et leur statut"},
                {"label": "User Profiles", "url": "/admin/users", "desc": "Voir les profils, avatars et licences"},
                {"label": "API Docs (Swagger)", "url": "/docs", "desc": "Tester les endpoints REST"},
                {"label": "API Docs (ReDoc)", "url": "/redoc", "desc": "Documentation alternative"},
                {"label": "Health Check", "url": "/health", "desc": "Verifier l'etat du backend"},
                {"label": "Latest Update API", "url": "/updates/latest", "desc": "Infos de mise a jour"},
            ],
        },
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
