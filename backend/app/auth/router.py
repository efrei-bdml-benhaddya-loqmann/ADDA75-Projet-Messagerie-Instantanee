"""Router pour l'authentification : POST /api/auth/login."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest, TokenOut
from app.auth.security import create_access_token, verify_password
from app.core.database import get_db
from app.core.errors import UnauthorizedException
from app.users.service import get_user_by_username

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Connexion et obtention d'un jeton JWT",
    responses={
        200: {"description": "Connexion réussie, jeton JWT renvoyé"},
        401: {"description": "Identifiants invalides (nom ou mot de passe incorrect)"},
    },
)
def login(creds: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenOut:
    """Authentifie un utilisateur et renvoie un JWT au format Bearer."""
    user = get_user_by_username(db, creds.username)
    if user is None or not verify_password(creds.mot_de_passe, user.password_hash):
        raise UnauthorizedException("Nom d'utilisateur ou mot de passe incorrect")

    token = create_access_token(user.id)
    return TokenOut(token=token, token_type="bearer")
