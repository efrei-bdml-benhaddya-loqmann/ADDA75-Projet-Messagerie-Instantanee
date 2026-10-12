"""Schémas Pydantic pour les utilisateurs."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Modèle de base sérialisé/désérialisé en camelCase pour JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class UserCreate(CamelModel):
    """Payload pour l'inscription : POST /api/comptes."""

    # max_length=50 : aligné sur la colonne String(50), que SQLite ne fait pas respecter
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Nom d'utilisateur unique (lettres, chiffres, _ . -)",
        examples=["alice"],
    )
    # max_length=72 : bcrypt ignore tout ce qui dépasse 72 octets
    mot_de_passe: str = Field(
        ..., min_length=4, max_length=72, description="Mot de passe en clair", examples=["secret1"]
    )


class UserOut(CamelModel):
    """Réponse après création de compte : 201 Created."""

    id: int
    username: str


class UserListItem(CamelModel):
    """Élément de la liste renvoyée par GET /api/utilisateurs."""

    id: int
    username: str
    connecte: bool
