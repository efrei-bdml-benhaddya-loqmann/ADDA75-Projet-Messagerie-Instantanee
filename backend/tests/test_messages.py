from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import create_access_token
from app.core.database import Base, get_db
from app.main import app
from app.messages.service import (
    get_conversation,
    mark_messages_as_read,
    save_message,
    update_message_status,
)
from app.users.models import User

# Configuration d'une base SQLite en mémoire partagée pour les tests
TEST_DATABASE_URL = "sqlite:///:memory:"
engine_test = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def setup_database() -> Iterator[None]:
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_service_save_and_get_conversation(db_session: Session) -> None:
    u1 = User(username="user1", password_hash="hash1")
    u2 = User(username="user2", password_hash="hash2")
    u3 = User(username="user3", password_hash="hash3")
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    m1 = save_message(db_session, u1.id, u2.id, "Message 1")
    m2 = save_message(db_session, u2.id, u1.id, "Message 2")
    # Message avec un tiers (ne doit pas apparaître dans la conversation u1 <-> u2)
    save_message(db_session, u1.id, u3.id, "Message hors conversation")

    convo = get_conversation(db_session, u1.id, u2.id)
    assert len(convo) == 2
    assert [m.id for m in convo] == [m1.id, m2.id]
    assert convo[0].contenu == "Message 1"
    assert convo[1].contenu == "Message 2"


def test_service_status_updates(db_session: Session) -> None:
    u1 = User(username="sender", password_hash="hash")
    u2 = User(username="receiver", password_hash="hash")
    db_session.add_all([u1, u2])
    db_session.commit()

    msg = save_message(db_session, u1.id, u2.id, "Coucou", statut="envoye")
    assert msg.statut == "envoye"

    updated = update_message_status(db_session, msg.id, "livre")
    assert updated is not None
    assert updated.statut == "livre"

    marked_ids = mark_messages_as_read(db_session, reader_id=u2.id, sender_id=u1.id)
    assert marked_ids == [msg.id]

    convo = get_conversation(db_session, u1.id, u2.id)
    assert convo[0].statut == "lu"


def test_rest_get_messages_unauthorized(client: TestClient) -> None:
    res = client.get("/api/messages/2")
    assert res.status_code == 401
    assert "detail" in res.json()


def test_rest_get_messages_target_not_found(client: TestClient, db_session: Session) -> None:
    u1 = User(username="alice", password_hash="hash")
    db_session.add(u1)
    db_session.commit()

    token = create_access_token(u1.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/messages/999", headers=headers)
    assert res.status_code == 404


def test_rest_get_messages_success(client: TestClient, db_session: Session) -> None:
    u1 = User(username="alice", password_hash="hash")
    u2 = User(username="bob", password_hash="hash")
    db_session.add_all([u1, u2])
    db_session.commit()

    save_message(db_session, u1.id, u2.id, "Salut Bob")
    save_message(db_session, u2.id, u1.id, "Salut Alice")

    token = create_access_token(u1.id)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get(f"/api/messages/{u2.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    # Vérification du format camelCase imposé par l'énoncé
    assert "expediteurId" in data[0]
    assert "destinataireId" in data[0]
    assert "dateEnvoi" in data[0]
    assert "statut" in data[0]
    assert data[0]["contenu"] == "Salut Bob"
    assert data[1]["contenu"] == "Salut Alice"
