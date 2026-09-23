"""Connexion à la base de données et gestion des sessions SQLAlchemy."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# check_same_thread=False : FastAPI exécute les routes `def` dans des threads différents
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """Classe mère de tous les modèles ORM (User, Message)."""


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : ouvre une session pour la requête et la ferme à la fin."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
