"""Modèle SQLAlchemy pour les messages.

Spécifications (§4 du sujet et ROADMAP.md) :
- Table 'messages'
- Clés étrangères vers 'users.id' (expéditeur et destinataire)
- Contenu textuel non nul
- Horodatage généré exclusivement côté serveur en UTC
- Indexation sur le couple (expediteur_id, destinataire_id) pour optimiser
  la récupération de l'historique
- Statut de livraison pour l'accusé de réception (bonus)

Documentation SQLAlchemy 2.0 :
https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UTCDateTime(TypeDecorator):
    """TypeDecorator garantissant des objets datetime conscients du fuseau UTC.

    Règle 8 & 5 : SQLite stocke les dates sans information de fuseau horaire.
    Ce décorateur réassigne le fuseau UTC à la lecture pour éviter les erreurs
    de comparaison entre datetime naïf et conscient (offset-naive vs offset-aware).
    Référence : https://docs.sqlalchemy.org/en/20/core/custom_types.html
    """

    impl = DateTime
    cache_ok = True

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    expediteur_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    destinataire_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    # Conformément à la spécification, dateEnvoi est systématiquement attribuée par le serveur
    date_envoi: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    # Bonus accusé de réception : valeurs autorisées 'envoye', 'livre', 'lu'
    statut: Mapped[str] = mapped_column(String(20), default="envoye", nullable=False)

    __table_args__ = (
        # Accélère les filtres bi-directionnels : (A -> B) ou (B -> A)
        Index("ix_messages_exp_dest", "expediteur_id", "destinataire_id"),
        Index("ix_messages_dest_exp", "destinataire_id", "expediteur_id"),
    )
