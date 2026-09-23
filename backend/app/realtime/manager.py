"""Gestionnaire des connexions WebSocket et présence des utilisateurs.

Contrat partagé défini dans la section 2 de ROADMAP.md.
"""

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Gère l'état en mémoire des connexions WebSocket actives."""

    def __init__(self) -> None:
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        """Enregistre la connexion d'un utilisateur."""
        self.active_connections[user_id] = ws

    def disconnect(self, user_id: int) -> None:
        """Supprime la connexion d'un utilisateur."""
        self.active_connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        """Indique si un utilisateur est actuellement connecté."""
        return user_id in self.active_connections

    async def send_to(self, user_id: int, payload: dict[str, Any]) -> bool:
        """Envoie un message JSON à un utilisateur s'il est en ligne.

        Renvoie True si envoyé, False s'il est hors ligne.
        """
        ws = self.active_connections.get(user_id)
        if ws is None:
            return False
        await ws.send_json(payload)
        return True


manager = ConnectionManager()
