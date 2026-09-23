"""Dépendances FastAPI pour l'authentification et l'autorisation.

Contrat partagé défini dans ROADMAP.md (§2) :
`get_current_user` garantit le renvoi d'un User authentifié ou lève une HTTPException(401).
"""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.database import get_db
from app.users.models import User


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> User:
    """Extrait et valide le Bearer token du header Authorization.

    Lève systématiquement HTTP 401 (et non 403) si le token est manquant,
    malformé, expiré ou si l'utilisateur associé n'existe plus en base.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton d'authentification manquant ou format invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton d'authentification invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

# TODO: Binôme A enrichira cette dépendance (ex: compte désactivé) à l'étape 3.
