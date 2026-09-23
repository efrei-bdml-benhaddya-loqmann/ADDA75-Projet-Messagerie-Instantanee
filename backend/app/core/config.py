"""Configuration de l'application, lue depuis les variables d'environnement et le fichier .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres de l'application.

    Champs attendus :
    - database_url : URL SQLAlchemy de la base (défaut : "sqlite:///./data/messagerie.db")
    - jwt_secret : clé de signature des JWT (obligatoire, sans valeur par défaut)
    - jwt_algorithm : algorithme de signature (défaut : "HS256")
    - jwt_expire_minutes : durée de validité d'un token (défaut : 60)
    """

    model_config = SettingsConfigDict(env_file=".env")

    # on declare les champs avec leur type et leur valeur par défaut
    database_url: str = "sqlite:///./data/messagerie.db"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


settings = Settings()
