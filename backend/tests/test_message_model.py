from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.messages.models import Message
from app.users.models import User


def test_message_model_creation_and_defaults() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    try:
        user_a = User(username="alice", password_hash="dummy_hash_a")
        user_b = User(username="bob", password_hash="dummy_hash_b")
        session.add_all([user_a, user_b])
        session.commit()

        before = datetime.now(UTC)
        msg = Message(
            expediteur_id=user_a.id,
            destinataire_id=user_b.id,
            contenu="Bonjour Bob !",
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)

        assert msg.id is not None
        assert msg.expediteur_id == user_a.id
        assert msg.destinataire_id == user_b.id
        assert msg.contenu == "Bonjour Bob !"
        assert msg.statut == "envoye"
        assert msg.date_envoi >= before
    finally:
        session.close()
