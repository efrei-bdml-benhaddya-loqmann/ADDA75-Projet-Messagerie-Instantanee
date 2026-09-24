"""Registre des connexions WebSocket actives, source de vérité pour la présence.

Contrat partagé défini dans ROADMAP.md (§2) :
`is_online` est aussi utilisé par le domaine users dans
`GET /api/utilisateurs` pour renseigner le champ `connecte`.
"""

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Associe chaque utilisateur connecté à sa connexion WebSocket.

    État interne attendu : un dictionnaire user_id -> WebSocket, en mémoire du process
    (d'où la contrainte d'un seul worker Uvicorn).
    """

    def __init__(self) -> None:
        self._active_connections: dict[int, WebSocket] = {}

    @property
    def active_connections(self) -> dict[int, WebSocket]:
        """Accès direct aux connexions actives pour compatibilité."""
        return self._active_connections

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        """Enregistre la connexion de l'utilisateur (le token a déjà été vérifié)."""
        self._active_connections[user_id] = ws

    def disconnect(self, user_id: int) -> None:
        """Retire l'utilisateur du registre (déconnexion volontaire ou coupure)."""
        self._active_connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        """Indique si l'utilisateur a une connexion WebSocket active."""
        return user_id in self._active_connections

    async def send_to(self, user_id: int, payload: dict[str, Any]) -> bool:
        """Envoie `payload` en JSON à l'utilisateur.

        Renvoie True si le message a été transmis, False s'il est hors ligne.
        Doc FastAPI WebSockets : https://fastapi.tiangolo.com/advanced/websockets/
        """
        ws = self._active_connections.get(user_id)
        if ws is None:
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception:
            # Si l'envoi échoue (connexion brutalement fermée côté client),
            # on purge immédiatement l'utilisateur du registre pour éviter
            # de futures tentatives d'envoi vers un socket mort.
            self.disconnect(user_id)
            return False


manager = ConnectionManager()
