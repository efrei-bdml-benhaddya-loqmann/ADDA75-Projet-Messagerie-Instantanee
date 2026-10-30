"""Registre des connexions WebSocket actives, source de vérité pour la présence.

Contrat défini dans ROADMAP.md (§2) : `is_online` sert aussi à `GET /api/utilisateurs`,
qui en tire le champ `connecte`.
"""

from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Associe chaque utilisateur connecté à sa connexion WebSocket.

    Le registre (user_id -> WebSocket) vit en mémoire du process, d'où la contrainte d'un
    seul worker Uvicorn. Une seule connexion par utilisateur : la plus récente remplace
    la précédente.
    """

    def __init__(self) -> None:
        self._active_connections: dict[int, WebSocket] = {}

    @property
    def active_connections(self) -> dict[int, WebSocket]:
        """Le dictionnaire user_id -> WebSocket des connexions actives."""
        return self._active_connections

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        """Enregistre la connexion de l'utilisateur (le token a déjà été vérifié)."""
        self._active_connections[user_id] = ws

    def disconnect(self, user_id: int, ws: WebSocket | None = None) -> None:
        """Retire l'utilisateur du registre (déconnexion volontaire ou coupure).

        Si `ws` est fourni, on ne retire l'entrée que si c'est bien cette socket-là :
        quand un client se reconnecte avant que l'ancienne socket soit détectée comme
        morte, la fermeture tardive de l'ancienne ne doit pas évincer la nouvelle.
        """
        if ws is None or self._active_connections.get(user_id) is ws:
            self._active_connections.pop(user_id, None)

    def is_online(self, user_id: int) -> bool:
        """True si l'utilisateur a une connexion active."""
        return user_id in self._active_connections

    async def send_to(self, user_id: int, payload: dict[str, Any]) -> bool:
        """Envoie le payload en JSON à l'utilisateur.

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
            # Client parti sans fermeture propre : on retire sa socket du registre,
            # sinon les envois suivants échoueraient aussi.
            self.disconnect(user_id, ws)
            return False


manager = ConnectionManager()
