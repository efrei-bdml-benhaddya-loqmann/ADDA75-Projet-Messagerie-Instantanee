"""Registre des connexions WebSocket actives, source de vérité pour la présence.

Contrat partagé : `is_online` est aussi utilisé par le domaine users dans
`GET /api/utilisateurs` pour renseigner le champ `connecte`.
"""

from fastapi import WebSocket


class ConnectionManager:
    """Associe chaque utilisateur connecté à sa connexion WebSocket.

    État interne attendu : un dictionnaire user_id -> WebSocket, en mémoire du process
    (d'où la contrainte d'un seul worker Uvicorn).
    """

    def __init__(self) -> None:
        """Initialise le registre vide."""
        raise NotImplementedError

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        """Enregistre la connexion de l'utilisateur (le token a déjà été vérifié)."""
        raise NotImplementedError

    def disconnect(self, user_id: int) -> None:
        """Retire l'utilisateur du registre (déconnexion volontaire ou coupure)."""
        raise NotImplementedError

    def is_online(self, user_id: int) -> bool:
        """Indique si l'utilisateur a une connexion WebSocket active."""
        raise NotImplementedError

    async def send_to(self, user_id: int, payload: dict) -> bool:
        """Envoie `payload` en JSON à l'utilisateur.

        Renvoie True si le message a été transmis, False s'il est hors ligne.
        """
        raise NotImplementedError


# TODO: instancier `manager = ConnectionManager()`, l'instance unique partagée par
# l'endpoint /ws/messages et par GET /api/utilisateurs
