from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.auth.security import create_access_token
from app.core.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.messages.models import Message
from app.realtime.manager import manager
from app.users.models import User

TEST_DATABASE_URL = "sqlite:///:memory:"
engine_test = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def setup_database() -> Iterator[None]:
    # Règle 8 : Lier SessionLocal à l'engine de test (StaticPool) pour que les threads
    # exécutés via run_in_threadpool partagent la même base SQLite en mémoire.
    SessionLocal.configure(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)
    SessionLocal.configure(bind=engine)


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


def test_ws_rejected_without_token(client: TestClient) -> None:
    # Doit être rejeté avec le code 1008 (Policy Violation)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/messages"):
            pass
    assert exc_info.value.code == 1008


def test_ws_rejected_with_invalid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/messages?token=faux_token"):
            pass
    assert exc_info.value.code == 1008


def test_ws_message_recipient_offline_persisted(client: TestClient, db_session: Session) -> None:
    u1 = User(username="alice", password_hash="hash")
    u2 = User(username="bob", password_hash="hash")
    db_session.add_all([u1, u2])
    db_session.commit()

    token_a = create_access_token(u1.id)

    with client.websocket_connect(f"/ws/messages?token={token_a}") as ws_a:
        assert manager.is_online(u1.id)
        assert not manager.is_online(u2.id)

        ws_a.send_json({
            "type": "message",
            "destinataireId": u2.id,
            "contenu": "Message pour Bob hors ligne",
        })

        ack = ws_a.receive_json()
        assert ack["type"] == "ack"
        assert ack["destinataireId"] == u2.id
        assert ack["contenu"] == "Message pour Bob hors ligne"
        # Destinataire hors ligne -> statut reste "envoye"
        assert ack["statut"] == "envoye"

    # Vérification du nettoyage à la fermeture de la connexion
    assert not manager.is_online(u1.id)

    # Vérification que le message est bien persisté en base pour récupération à la reconnexion
    saved = db_session.query(Message).filter(Message.destinataire_id == u2.id).first()
    assert saved is not None
    assert saved.contenu == "Message pour Bob hors ligne"
    assert saved.statut == "envoye"


def test_ws_direct_message_delivery_and_read_receipt(
    client: TestClient, db_session: Session
) -> None:
    u1 = User(username="alice", password_hash="hash")
    u2 = User(username="bob", password_hash="hash")
    db_session.add_all([u1, u2])
    db_session.commit()

    token_a = create_access_token(u1.id)
    token_b = create_access_token(u2.id)

    with client.websocket_connect(f"/ws/messages?token={token_a}") as ws_a:
        with client.websocket_connect(f"/ws/messages?token={token_b}") as ws_b:
            assert manager.is_online(u1.id)
            assert manager.is_online(u2.id)

            # A envoie un message à B
            ws_a.send_json({
                "type": "message",
                "destinataireId": u2.id,
                "contenu": "Salut Bob en direct !",
            })

            # B reçoit le message en direct
            msg_b = ws_b.receive_json()
            assert msg_b["type"] == "message"
            assert msg_b["expediteurId"] == u1.id
            assert msg_b["destinataireId"] == u2.id
            assert msg_b["contenu"] == "Salut Bob en direct !"
            assert msg_b["statut"] == "livre"

            # A reçoit l'accusé de réception confirmant la livraison directe
            ack_a = ws_a.receive_json()
            assert ack_a["type"] == "ack"
            assert ack_a["statut"] == "livre"

            # B envoie un accusé de lecture pour les messages reçus de A
            ws_b.send_json({
                "type": "read",
                "expediteurId": u1.id,
            })

            # A reçoit la confirmation de lecture
            read_ack = ws_a.receive_json()
            assert read_ack["type"] == "read_ack"
            assert read_ack["readerId"] == u2.id
            assert msg_b["id"] in read_ack["messageIds"]

            # Indicateur de saisie en temps réel
            ws_a.send_json({
                "type": "typing",
                "destinataireId": u2.id,
                "isTyping": True,
            })
            typing_b = ws_b.receive_json()
            assert typing_b["type"] == "typing"
            assert typing_b["expediteurId"] == u1.id
            assert typing_b["isTyping"] is True


def test_ws_offline_then_reconnect_history(client: TestClient, db_session: Session) -> None:
    """Vérifie le scénario complet : envoi vers destinataire hors ligne, persistance,

    puis reconnexion et consultation de l'historique par le destinataire (Section 2.1).
    """
    u1 = User(username="alice", password_hash="hash")
    u2 = User(username="bob", password_hash="hash")
    db_session.add_all([u1, u2])
    db_session.commit()

    token_a = create_access_token(u1.id)
    token_b = create_access_token(u2.id)

    # Alice se connecte en WS, Bob est hors ligne
    with client.websocket_connect(f"/ws/messages?token={token_a}") as ws_a:
        ws_a.send_json({
            "type": "message",
            "destinataireId": u2.id,
            "contenu": "Tu verras ce message a ton retour",
        })
        ack = ws_a.receive_json()
        assert ack["type"] == "ack"
        assert ack["statut"] == "envoye"

    # Bob se connecte plus tard et consulte son historique REST avec Alice
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res = client.get(f"/api/messages/{u1.id}", headers=headers_b)
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) == 1
    assert messages[0]["expediteurId"] == u1.id
    assert messages[0]["destinataireId"] == u2.id
    assert messages[0]["contenu"] == "Tu verras ce message a ton retour"
    assert messages[0]["statut"] == "envoye"

