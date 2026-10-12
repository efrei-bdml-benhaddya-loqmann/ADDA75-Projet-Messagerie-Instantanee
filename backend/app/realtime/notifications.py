"""Notification hors ligne (bonus) : webhook vers un service tiers simulé.

Comme au TP4 (webhook.site), le serveur prévient un service externe qu'un événement a eu
lieu. Ici le service tiers est simulé : l'appel est seulement journalisé dans les logs
serveur, ce que l'énoncé autorise (§6, « Notification hors ligne »).
"""

import logging

logger = logging.getLogger(__name__)


def notify_offline_recipient(destinataire_id: int, expediteur_id: int, message_id: int) -> None:
    """Simule l'envoi d'un webhook (ex. push mobile) au destinataire hors ligne."""
    logger.info(
        "Webhook simulé : notification envoyée à l'utilisateur %s "
        "(nouveau message %s de l'utilisateur %s)",
        destinataire_id,
        message_id,
        expediteur_id,
    )
