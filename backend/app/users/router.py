"""Router pour la gestion des utilisateurs : POST /api/comptes, GET /api/utilisateurs."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.core.database import get_db
from app.realtime.manager import manager
from app.users import service
from app.users.models import User
from app.users.schemas import UserCreate, UserListItem, UserOut

router = APIRouter(prefix="/api", tags=["utilisateurs"])


@router.post(
    "/comptes",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Création d'un nouveau compte utilisateur",
    responses={
        201: {"description": "Compte créé avec succès"},
        409: {"description": "Nom d'utilisateur déjà pris"},
        422: {"description": "Validation échouée (champs manquants ou invalides)"},
    },
)
def register(user_in: UserCreate, db: Annotated[Session, Depends(get_db)]) -> UserOut:
    """Enregistre un nouvel utilisateur avec mot de passe haché."""
    user = service.create_user(db, user_in)
    return UserOut(id=user.id, username=user.username)


@router.get(
    "/utilisateurs",
    response_model=list[UserListItem],
    status_code=status.HTTP_200_OK,
    summary="Liste des utilisateurs avec statut de connexion",
    responses={
        200: {"description": "Liste des utilisateurs"},
        401: {"description": "Non autorisé (jeton JWT manquant ou invalide)"},
    },
)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> list[UserListItem]:
    """Renvoie la liste de tous les utilisateurs et indique s'ils sont connectés en temps réel."""
    all_users = service.get_all_users(db)
    return [
        UserListItem(
            id=u.id,
            username=u.username,
            connecte=manager.is_online(u.id),
        )
        for u in all_users
    ]
