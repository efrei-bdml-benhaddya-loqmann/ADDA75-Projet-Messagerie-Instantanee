"""Routeur REST pour la consultation des messages et de l'historique."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.core.database import get_db
from app.core.errors import NotFoundException
from app.messages.schemas import MessageResponse
from app.messages.service import get_conversation
from app.users.models import User

router = APIRouter(prefix="/api/messages", tags=["Messages"])


@router.get(
    "/{utilisateur_id}",
    response_model=list[MessageResponse],
    summary="Récupérer l'historique des messages avec un utilisateur",
    responses={
        401: {"description": "Non autorisé (jeton JWT manquant ou invalide)"},
        404: {"description": "Utilisateur cible introuvable"},
    },
)
def get_historique_messages(
    utilisateur_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MessageResponse]:
    """Renvoie la liste chronologique des messages échangés entre l'utilisateur connecté

    et l'utilisateur cible spécifié dans l'URL.
    """
    # Vérification de l'existence de l'interlocuteur pour renvoyer 404 si inexistant
    target_user = db.query(User).filter(User.id == utilisateur_id).first()
    if target_user is None:
        raise NotFoundException(f"Utilisateur {utilisateur_id} introuvable")

    messages = get_conversation(db, current_user.id, utilisateur_id)
    return list(messages)
