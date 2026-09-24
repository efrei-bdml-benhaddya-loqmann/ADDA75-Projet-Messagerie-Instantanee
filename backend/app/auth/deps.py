"""Dépendances FastAPI pour l'authentification et l'autorisation.

Contrat partagé défini dans ROADMAP.md (§2) :
`get_current_user` garantit le renvoi d'un User authentifié ou lève une HTTPException(401).
"""

from typing import Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.database import get_db
from app.core.errors import UnauthorizedException
from app.users.models import User


def get_current_user(
    authorization: Annotated[
        str | None,
        Header(description="Jeton sous format: Bearer <token>"),
    ] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> User:
    """Valide le jeton JWT transmis dans le header Authorization.

    Garantit une réponse HTTP 401 Unauthorized si le jeton est absent,
    malformé, expiré ou si l'utilisateur n'existe plus en base.
    """
    if not authorization:
        raise UnauthorizedException("En-tête d'authentification manquant")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        msg = "Format d'autorisation invalide. Format attendu : Bearer <token>"
        raise UnauthorizedException(msg)

    token = parts[1]

    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise UnauthorizedException("Jeton invalide ou expiré") from None

    if db is None:
        db = next(get_db())

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedException("Utilisateur non trouvé")

    return user
