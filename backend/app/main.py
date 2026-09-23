"""Point d'entrée de l'application : `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Exécuté au démarrage (avant `yield`) et à l'arrêt (après `yield`) du serveur.

    Au démarrage : créer les tables avec Base.metadata.create_all(bind=engine).
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ADDA75 Project API", version="0.1.0", lifespan=lifespan)
# TODO: inclure les routers des domaines (à partir de l'étape 2)


@app.get("/health")
def health() -> dict[str, str]:
    """GET /health : vérifie que le serveur tourne, renvoie {"status": "ok"}."""
    return {"status": "ok"}
