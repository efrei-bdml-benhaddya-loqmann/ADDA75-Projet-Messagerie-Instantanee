"""Hachage des mots de passe et gestion des JWT.

Contrat partagé défini dans ROADMAP.md (§2) :
`create_access_token` et `decode_access_token` sont utilisés
par le domaine realtime pour authentifier la connexion WebSocket.

Références externes :
- PyJWT : https://pyjwt.readthedocs.io/
- RFC 7519 (JSON Web Token) : https://datatracker.ietf.org/doc/html/rfc7519
- Pwdlib : https://frankie567.github.io/pwdlib/
"""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

# Utilisation explicite du hasher Bcrypt pour respecter les dépendances du projet
password_hasher = PasswordHash((BcryptHasher(),))


def hash_password(password: str) -> str:
    """Renvoie le hash bcrypt (salé) du mot de passe."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Indique si le mot de passe correspond au hash stocké."""
    return password_hasher.verify(password, password_hash)


def create_access_token(user_id: int) -> str:
    """Génère un JWT signé contenant l'id utilisateur (claim `sub`) et une expiration (`exp`)."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    # Selon la RFC 7519 (§4.1.2), le claim 'sub' doit idéalement être une chaîne de caractères
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Vérifie le JWT et renvoie l'id utilisateur.

    Lève jwt.InvalidTokenError si le token est invalide, falsifié ou expiré.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise jwt.InvalidTokenError("Token payload missing 'sub' subject claim")
    return int(user_id_str)


# TODO: Binôme A complétera les règles de politique de mot de passe à l'étape 3.
