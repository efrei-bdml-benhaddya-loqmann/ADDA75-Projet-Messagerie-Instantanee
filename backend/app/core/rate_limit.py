"""Limitation de débit par fenêtre glissante (même algorithme que le RateLimitFilter du TP5).

Chaque clé (utilisateur, ou IP + username pour le login) garde les horodatages de ses
derniers appels. Au-delà de `max_requests` sur `window_seconds`, l'appel est refusé et on
renvoie le délai d'attente, utilisé pour l'en-tête `Retry-After` (REST) ou le champ
`retryAfter` (WebSocket).

L'état est en mémoire du process : comme le ConnectionManager, il suppose un seul worker
(en multi-instances il faudrait Redis, cf. rapport).
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        # Les routes REST `def` tournent dans des threads différents
        self._lock = threading.Lock()

    def hit(self, key: str) -> float:
        """Enregistre un appel. Renvoie 0 s'il est autorisé, sinon les secondes à attendre."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return self.window_seconds - (now - hits[0])
            hits.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Anti-spam : 10 messages par tranche de 10 secondes et par utilisateur
ws_message_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=10)
# Anti brute-force : 5 tentatives de connexion par minute pour un couple (IP, username)
login_limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
