"""Hachage des mots de passe et gestion des JWT.

Contrat partagé : `create_access_token` et `decode_access_token` sont aussi utilisés
par le domaine realtime pour authentifier la connexion WebSocket.
"""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

# Initialise le gestionnaire bcrypt conformément au pyproject.toml (pwdlib[bcrypt])
_password_hash = PasswordHash((BcryptHasher(),))


def hash_password(password: str) -> str:
    """Renvoie le hash bcrypt (salé) du mot de passe."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Indique si le mot de passe correspond au hash stocké."""
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    """Génère un JWT signé contenant l'id utilisateur (claim `sub`) et une expiration (`exp`)."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Vérifie le JWT et renvoie l'id utilisateur.

    Lève jwt.InvalidTokenError si le token est invalide, falsifié ou expiré.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    sub = payload.get("sub")
    if sub is None:
        raise jwt.InvalidTokenError("Claim 'sub' manquant dans le token")
    return int(sub)
