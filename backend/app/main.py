"""Point d'entrée de l'application : `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import explicite des modèles pour que SQLAlchemy enregistre les tables dans Base.metadata
import app.messages.models  # noqa: F401
import app.users.models  # noqa: F401
from app.core.database import Base, engine
from app.messages.router import router as messages_router
from app.realtime.router import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Exécuté au démarrage (avant `yield`) et à l'arrêt (après `yield`) du serveur.

    Au démarrage : créer les tables avec Base.metadata.create_all(bind=engine).
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ADDA75 Project API", version="0.1.0", lifespan=lifespan)

# Configuration CORS pour permettre aux clients web (desktop et mobile) d'accéder à l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(messages_router)
app.include_router(realtime_router)
# TODO: inclure les routers des autres domaines (comptes, auth, utilisateurs) par Binôme A


@app.get("/health")
def health() -> dict[str, str]:
    """GET /health : vérifie que le serveur tourne, renvoie {"status": "ok"}."""
    return {"status": "ok"}
