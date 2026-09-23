"""Schémas Pydantic pour la validation des trames WebSocket échangées."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class WSMessageIn(BaseModel):
    """Trame envoyée par un client pour adresser un message texte à un pair."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["message"] = "message"
    destinataire_id: int
    contenu: str = Field(..., min_length=1, max_length=5000)


class WSReadIn(BaseModel):
    """Trame informant que les messages d'un expéditeur ont été lus (bonus accusé de lecture)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["read"] = "read"
    expediteur_id: int


class WSTypingIn(BaseModel):
    """Trame d'indicateur de saisie en temps réel (bonus)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    type: Literal["typing"] = "typing"
    destinataire_id: int
    is_typing: bool = True


class WSPingIn(BaseModel):
    """Trame de pulsation (keep-alive / ping-pong)."""

    type: Literal["ping"] = "ping"
