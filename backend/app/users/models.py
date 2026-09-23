"""Modèle SQLAlchemy pour les utilisateurs.

Contrat partagé défini dans ROADMAP.md (§2) :
- Table 'users'
- Clé primaire 'id' référencée par les messages
- 'username' unique
- 'password_hash' pour le stockage sécurisé du mot de passe
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # TODO: Binôme A enrichira ce modèle si nécessaire lors de l'étape 1.
