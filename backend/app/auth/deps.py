"""Dépendances FastAPI pour l'authentification et l'autorisation.

Contrat partagé défini dans ROADMAP.md (§2) :
`get_current_user` garantit le renvoi d'un User authentifié ou lève une HTTPException(401).
"""

from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.database import get_db
from app.core.errors import UnauthorizedException
from app.users.models import User

# Déclare le schéma "Bearer" dans OpenAPI : Swagger affiche le bouton « Authorize ».
# auto_error=False : sinon FastAPI renverrait lui-même une erreur (403 selon les versions),
# alors que l'énoncé exige 401 ; on la lève nous-mêmes ci-dessous.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Jeton obtenu via POST /api/auth/login (coller uniquement le jeton)",
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> User:
    """Valide le jeton JWT transmis dans le header Authorization.

    Garantit une réponse HTTP 401 Unauthorized si le jeton est absent,
    malformé, expiré ou si l'utilisateur n'existe plus en base.
    """
    if credentials is None:
        raise UnauthorizedException(
            "En-tête d'authentification manquant ou mal formé (attendu : Bearer <token>)"
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise UnauthorizedException("Jeton invalide ou expiré") from None

    if db is None:
        db = next(get_db())

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedException("Utilisateur non trouvé")

    return user
