"""Services métier pour la gestion des utilisateurs."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.errors import ConflictException
from app.users.models import User
from app.users.schemas import UserCreate


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Récupère un utilisateur par son identifiant unique."""
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    """Récupère un utilisateur par son nom d'utilisateur."""
    stmt = select(User).where(User.username == username)
    return db.scalar(stmt)


def create_user(db: Session, user_in: UserCreate) -> User:
    """Crée un nouvel utilisateur après vérification de l'unicité du nom d'utilisateur.

    Lève ConflictException (HTTP 409) si le nom d'utilisateur est déjà pris.
    """
    existing_user = get_user_by_username(db, user_in.username)
    if existing_user is not None:
        raise ConflictException(f"Le nom d'utilisateur '{user_in.username}' est déjà utilisé")

    hashed_pw = hash_password(user_in.mot_de_passe)
    user = User(username=user_in.username, password_hash=hashed_pw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_all_users(db: Session) -> Sequence[User]:
    """Renvoie la liste de tous les utilisateurs triés par identifiant."""
    stmt = select(User).order_by(User.id)
    return db.scalars(stmt).all()
