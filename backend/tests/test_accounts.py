"""Tests pour la création de comptes et la liste des utilisateurs."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import create_access_token
from app.users.schemas import UserCreate
from app.users.service import create_user


def test_create_account_success(client: TestClient) -> None:
    """POST /api/comptes : 201 Created et retour de {id, username}."""
    response = client.post(
        "/api/comptes",
        json={"username": "charlie", "motDePasse": "charliePass123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "charlie"
    assert "id" in data
    assert "motDePasse" not in data
    assert "password_hash" not in data


def test_create_account_duplicate_409(client: TestClient) -> None:
    """POST /api/comptes : 409 Conflict si le nom d'utilisateur est déjà pris."""
    payload = {"username": "doublon", "motDePasse": "pass1"}
    first = client.post("/api/comptes", json=payload)
    assert first.status_code == 201

    second = client.post("/api/comptes", json=payload)
    assert second.status_code == 409
    assert "déjà utilisé" in second.json()["detail"].lower()


def test_create_account_missing_fields_422(client: TestClient) -> None:
    """POST /api/comptes : 422 Unprocessable Entity si le payload est incomplet."""
    response = client.post("/api/comptes", json={"username": ""})
    assert response.status_code == 422


def test_get_users_without_token_returns_401(client: TestClient) -> None:
    """GET /api/utilisateurs : 401 si aucun header Authorization."""
    response = client.get("/api/utilisateurs")
    assert response.status_code == 401
    assert "manquant" in response.json()["detail"].lower()


def test_get_users_with_invalid_token_returns_401(client: TestClient) -> None:
    """GET /api/utilisateurs : 401 si le token est invalide."""
    response = client.get(
        "/api/utilisateurs",
        headers={"Authorization": "Bearer token.completement.faux"},
    )
    assert response.status_code == 401
    assert "invalide" in response.json()["detail"].lower()


def test_get_users_with_malformed_header_returns_401(client: TestClient) -> None:
    """GET /api/utilisateurs : 401 si le header n'est pas au format Bearer."""
    response = client.get(
        "/api/utilisateurs",
        headers={"Authorization": "Basic 12345"},
    )
    assert response.status_code == 401


def test_get_users_success_with_token(client: TestClient, db_session: Session) -> None:
    """GET /api/utilisateurs : 200 avec la liste des utilisateurs si token valide."""
    user1 = create_user(db_session, UserCreate(username="user1", mot_de_passe="pass1"))
    user2 = create_user(db_session, UserCreate(username="user2", mot_de_passe="pass2"))

    token = create_access_token(user1.id)
    response = client.get(
        "/api/utilisateurs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 2
    assert users[0]["id"] == user1.id
    assert users[0]["username"] == "user1"
    assert users[0]["connecte"] is False
    assert users[1]["id"] == user2.id
    assert users[1]["username"] == "user2"
    assert users[1]["connecte"] is False
