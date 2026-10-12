"""Point d'entrée de l'application : `uv run uvicorn app.main:app --reload`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# Import explicite des modèles pour que SQLAlchemy enregistre les tables dans Base.metadata
import app.messages.models  # noqa: F401
import app.users.models  # noqa: F401
from app.auth.router import router as auth_router
from app.core.database import Base, engine
from app.core.errors import AppException, app_exception_handler, validation_exception_handler
from app.messages.router import router as messages_router
from app.realtime.router import router as realtime_router
from app.users.router import router as users_router

# Affiche les logs INFO de l'application (ex. webhook simulé) dans la console d'uvicorn
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Exécuté au démarrage et à l'arrêt du serveur.

    Au démarrage : créer les tables avec Base.metadata.create_all(bind=engine).
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="ADDA75 - Messagerie Instantanée API",
    version="0.1.0",
    description="Backend FastAPI pour la messagerie instantanée (REST & WebSocket).",
    lifespan=lifespan,
)

# Configuration CORS pour permettre aux clients web (desktop et mobile) d'accéder à l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gestionnaires globaux d'exceptions (format d'erreur homogène {detail, code})
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Inclusion des routers de l'ensemble des domaines
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(messages_router)
app.include_router(realtime_router)


# Servir directement les clients statiques sur FastAPI (port 8000)
_clients_dir = Path(__file__).resolve().parent.parent.parent / "clients"
if _clients_dir.exists():
    app.mount("/clients", StaticFiles(directory=str(_clients_dir), html=True), name="clients")


@app.get("/health", tags=["monitoring"])
def health() -> dict[str, str]:
    """GET /health : vérifie que le serveur tourne, renvoie {"status": "ok"}."""
    return {"status": "ok"}
