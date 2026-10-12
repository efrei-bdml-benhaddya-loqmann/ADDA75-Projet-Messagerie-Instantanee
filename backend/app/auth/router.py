"""Router pour l'authentification : POST /api/auth/login."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest, TokenOut
from app.auth.security import create_access_token, verify_password
from app.core.database import get_db
from app.core.errors import TooManyRequestsException, UnauthorizedException
from app.core.rate_limit import login_limiter
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
        429: {"description": "Trop de tentatives (anti brute-force), voir l'en-tête Retry-After"},
    },
)
def login(
    creds: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]
) -> TokenOut:
    """Authentifie un utilisateur et renvoie un JWT au format Bearer."""
    client_ip = request.client.host if request.client else "inconnu"
    retry_after = login_limiter.hit(f"{client_ip}:{creds.username}")
    if retry_after:
        raise TooManyRequestsException(retry_after)

    user = get_user_by_username(db, creds.username)
    if user is None or not verify_password(creds.mot_de_passe, user.password_hash):
        raise UnauthorizedException("Nom d'utilisateur ou mot de passe incorrect")

    token = create_access_token(user.id)
    return TokenOut(token=token, token_type="bearer")
