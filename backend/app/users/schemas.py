"""Schémas Pydantic pour les utilisateurs."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Modèle de base sérialisé/désérialisé en camelCase pour JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class UserCreate(CamelModel):
    """Payload pour l'inscription : POST /api/comptes."""

    username: str = Field(..., min_length=1, description="Nom d'utilisateur unique")
    mot_de_passe: str = Field(..., min_length=1, description="Mot de passe en clair")


class UserOut(CamelModel):
    """Réponse après création de compte : 201 Created."""

    id: int
    username: str


class UserListItem(CamelModel):
    """Élément de la liste renvoyée par GET /api/utilisateurs."""

    id: int
    username: str
    connecte: bool
