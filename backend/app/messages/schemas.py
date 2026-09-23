"""Schémas Pydantic pour la validation et la sérialisation des messages.

Conformément à la consigne du projet (ROADMAP.md § points d'attention FastAPI) :
- Les clés JSON envoyées et reçues par l'API sont en camelCase (expediteurId, dateEnvoi, etc.)
- Le code Python reste idiomatique en snake_case (expediteur_id, date_envoi, etc.)

Documentation Pydantic alias generator :
https://docs.pydantic.dev/latest/concepts/alias/#using-an-alias-generator
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class MessageBase(BaseModel):
    contenu: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    """Représentation publique d'un message retourné par l'API REST."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: int
    expediteur_id: int
    destinataire_id: int
    contenu: str
    date_envoi: datetime
    statut: str
