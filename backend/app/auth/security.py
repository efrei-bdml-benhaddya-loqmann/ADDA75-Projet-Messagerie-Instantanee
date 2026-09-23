"""Hachage des mots de passe et gestion des JWT.

Contrat partagé : `create_access_token` et `decode_access_token` sont aussi utilisés
par le domaine realtime pour authentifier la connexion WebSocket.
"""


def hash_password(password: str) -> str:
    """Renvoie le hash bcrypt (salé) du mot de passe."""
    raise NotImplementedError


def verify_password(password: str, password_hash: str) -> bool:
    """Indique si le mot de passe correspond au hash stocké."""
    raise NotImplementedError


def create_access_token(user_id: int) -> str:
    """Génère un JWT signé contenant l'id utilisateur (claim `sub`) et une expiration (`exp`)."""
    raise NotImplementedError


def decode_access_token(token: str) -> int:
    """Vérifie le JWT et renvoie l'id utilisateur.

    Lève jwt.InvalidTokenError si le token est invalide, falsifié ou expiré.
    """
    raise NotImplementedError
