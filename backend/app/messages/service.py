"""Couche service pour la persistance et la consultation des messages.

Fournit les opérations de base de données synchrones pour SQLAlchemy,
utilisées tant par les routes REST que par le worker WebSocket.
"""

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.messages.models import Message


def save_message(
    db: Session,
    expediteur_id: int,
    destinataire_id: int,
    contenu: str,
    statut: str = "envoye",
) -> Message:
    """Persiste un nouveau message en base de données et renvoie l'entité créée."""
    message = Message(
        expediteur_id=expediteur_id,
        destinataire_id=destinataire_id,
        contenu=contenu,
        statut=statut,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_conversation(
    db: Session,
    user_a_id: int,
    user_b_id: int,
) -> Sequence[Message]:
    """Récupère l'ensemble des échanges bi-directionnels entre deux utilisateurs.

    Les messages sont triés par ordre chronologique croissant pour reconstituer
    le fil de discussion linéaire.
    """
    stmt = (
        select(Message)
        .where(
            or_(
                (Message.expediteur_id == user_a_id) & (Message.destinataire_id == user_b_id),
                (Message.expediteur_id == user_b_id) & (Message.destinataire_id == user_a_id),
            )
        )
        .order_by(Message.date_envoi.asc(), Message.id.asc())
    )
    return db.execute(stmt).scalars().all()


def update_message_status(
    db: Session,
    message_id: int,
    statut: str,
) -> Message | None:
    """Met à jour l'état d'acheminement d'un message ('envoye' -> 'livre' -> 'lu')."""
    stmt = select(Message).where(Message.id == message_id)
    message = db.execute(stmt).scalar_one_or_none()
    if message is not None:
        message.statut = statut
        db.commit()
        db.refresh(message)
    return message


def mark_messages_as_read(
    db: Session,
    reader_id: int,
    sender_id: int,
) -> list[int]:
    """Marque comme 'lu' tous les messages reçus par reader_id en provenance de sender_id.

    Renvoie la liste des identifiants des messages mis à jour pour notifier l'expéditeur.
    """
    stmt = select(Message).where(
        Message.destinataire_id == reader_id,
        Message.expediteur_id == sender_id,
        Message.statut != "lu",
    )
    messages = db.execute(stmt).scalars().all()
    updated_ids: list[int] = []
    for msg in messages:
        msg.statut = "lu"
        updated_ids.append(msg.id)
    if updated_ids:
        db.commit()
    return updated_ids
