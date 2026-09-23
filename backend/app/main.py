"""Point d'entrée de l'application : `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.users.models  # noqa: F401 (Enregistre le modèle User auprès de Base.metadata)
from app.auth.router import router as auth_router
from app.core.database import Base, engine
from app.core.errors import AppException, app_exception_handler
from app.users.router import router as users_router


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

# Gestionnaire d'exceptions
app.add_exception_handler(AppException, app_exception_handler)

# Inclusion des routers
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/health", tags=["monitoring"])
def health() -> dict[str, str]:
    """GET /health : vérifie que le serveur tourne, renvoie {"status": "ok"}."""
    return {"status": "ok"}
