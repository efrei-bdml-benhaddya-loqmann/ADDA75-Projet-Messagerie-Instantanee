"""Tests du module d'authentification et de sécurité."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.users.schemas import UserCreate
from app.users.service import create_user


def test_password_hashing() -> None:
    """Vérifie que le hachage est salé et que la vérification fonctionne."""
    password = "monMotDePasseSecret123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("mauvaisMotDePasse", hashed) is False


def test_jwt_token_cycle() -> None:
    """Vérifie la génération et le décodage d'un jeton JWT valide."""
    user_id = 42
    token = create_access_token(user_id)
    decoded_id = decode_access_token(token)

    assert decoded_id == user_id


def test_jwt_invalid_token() -> None:
    """Vérifie qu'un jeton falsifié ou invalide lève InvalidTokenError."""
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("token.completement.bidon")


def test_jwt_expired_token() -> None:
    """Vérifie qu'un jeton expiré lève InvalidTokenError."""
    past = datetime.now(UTC) - timedelta(minutes=10)
    expired_payload = {
        "sub": "99",
        "iat": past - timedelta(minutes=60),
        "exp": past,
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(expired_token)


def test_login_success(client: TestClient, db_session: Session) -> None:
    """POST /api/auth/login : connexion réussie et obtention du JWT."""
    create_user(db_session, UserCreate(username="alice", mot_de_passe="secret123"))

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "motDePasse": "secret123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["tokenType"] == "bearer"

    user_id = decode_access_token(data["token"])
    assert user_id > 0


def test_login_wrong_password(client: TestClient, db_session: Session) -> None:
    """POST /api/auth/login : 401 si mauvais mot de passe."""
    create_user(db_session, UserCreate(username="bob", mot_de_passe="bonMotDePasse"))

    response = client.post(
        "/api/auth/login",
        json={"username": "bob", "motDePasse": "mauvaisMotDePasse"},
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


def test_login_user_not_found(client: TestClient) -> None:
    """POST /api/auth/login : 401 si utilisateur inexistant."""
    response = client.post(
        "/api/auth/login",
        json={"username": "inconnu", "motDePasse": "nimporte"},
    )
    assert response.status_code == 401
