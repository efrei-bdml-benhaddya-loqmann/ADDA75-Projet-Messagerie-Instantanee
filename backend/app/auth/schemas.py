"""Schémas Pydantic pour l'authentification."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Modèle de base sérialisé/désérialisé en camelCase pour JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class LoginRequest(CamelModel):
    """Payload pour la connexion : POST /api/auth/login."""

    username: str = Field(..., min_length=1, description="Nom d'utilisateur")
    mot_de_passe: str = Field(..., min_length=1, description="Mot de passe")


class TokenOut(CamelModel):
    """Réponse contenant le JWT après une connexion réussie."""

    token: str
    token_type: str = "bearer"
