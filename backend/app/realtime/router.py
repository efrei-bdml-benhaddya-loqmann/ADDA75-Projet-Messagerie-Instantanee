"""Routeur WebSocket pour l'acheminement des messages en temps réel.

Spécifications du sujet (§4 et ROADMAP.md) :
- Endpoint /ws/messages?token=...
- Authentification du JWT avant websocket.accept() (fermeture 1008 si invalide)
- Validation des charges utiles avec Pydantic
- Persistance synchrone déportée via run_in_threadpool pour ne pas bloquer l'event loop
- Accusés de réception ('envoye' -> 'livre' -> 'lu')
- Limitation de débit anti-spam et webhook simulé si le destinataire est hors ligne (bonus)
- Nettoyage à la déconnexion
"""

import json
import math
from typing import Any

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.auth.security import decode_access_token
from app.core.database import SessionLocal
from app.core.rate_limit import ws_message_limiter
from app.messages.service import mark_messages_as_read, mark_pending_as_delivered, save_message
from app.realtime.manager import manager
from app.realtime.notifications import notify_offline_recipient
from app.realtime.schemas import WSMessageIn, WSReadIn, WSTypingIn
from app.users.models import User

router = APIRouter(tags=["Realtime"])


def _authenticate(token: str | None) -> int | None:
    """Renvoie l'id de l'utilisateur du jeton, ou None si le jeton est absent, invalide,
    expiré, ou si l'utilisateur n'existe plus en base."""
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None
    with SessionLocal() as db:
        return user_id if db.get(User, user_id) is not None else None


def _persist_message(
    expediteur_id: int,
    destinataire_id: int,
    contenu: str,
    statut: str,
) -> dict[str, Any] | None:
    """Exécuté dans un threadpool pour ne pas bloquer la boucle asynchrone FastAPI.

    Règle 5 : SQLAlchemy 2.0 étant configuré en mode synchrone, l'appel à la base
    depuis une fonction 'async def' doit obligatoirement être délégué à un thread worker.
    Renvoie None si le destinataire n'existe pas (SQLite ne vérifie pas les clés étrangères).
    """
    with SessionLocal() as db:
        if db.get(User, destinataire_id) is None:
            return None
        msg = save_message(
            db=db,
            expediteur_id=expediteur_id,
            destinataire_id=destinataire_id,
            contenu=contenu,
            statut=statut,
        )
        return {
            "id": msg.id,
            "expediteurId": msg.expediteur_id,
            "destinataireId": msg.destinataire_id,
            "contenu": msg.contenu,
            "dateEnvoi": msg.date_envoi.isoformat(),
            "statut": msg.statut,
        }


def _mark_as_read_in_db(reader_id: int, sender_id: int) -> list[int]:
    """Met à jour les statuts en base dans un thread dédié."""
    with SessionLocal() as db:
        return mark_messages_as_read(db, reader_id=reader_id, sender_id=sender_id)


def _mark_pending_as_delivered(destinataire_id: int) -> dict[int, list[int]]:
    with SessionLocal() as db:
        return mark_pending_as_delivered(db, destinataire_id)


def _error(code: str, detail: Any, **extra: Any) -> dict[str, Any]:
    """Trame d'erreur, au même format {detail, code} que les erreurs REST."""
    return {"type": "error", "code": code, "detail": detail, **extra}


@router.websocket("/ws/messages")
async def websocket_messages(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Canal WebSocket bidirectionnel pour l'envoi et la réception de messages.

    Règle 7 : Fermeture avec le code 1008 (Policy Violation) conformément à la RFC 6455 §7.4.1
    https://datatracker.ietf.org/doc/html/rfc6455#section-7.4.1
    """
    # Le jeton est vérifié AVANT d'enregistrer la connexion : aucun message ne peut être
    # lu ni envoyé sans authentification. On fait tout de même accept() avant close() :
    # fermer avant accept() produit un simple refus HTTP 403 du handshake, que le navigateur
    # voit comme un code 1006 sans raison. Après accept(), le client reçoit bien 1008.
    user_id = await run_in_threadpool(_authenticate, token)
    if user_id is None:
        await websocket.accept()
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Jeton invalide ou expiré"
        )
        return

    await websocket.accept()
    await manager.connect(user_id, websocket)

    # Messages reçus pendant l'absence : ils passent à "livre", et leurs expéditeurs
    # connectés en sont informés (accusé de réception différé)
    delivered = await run_in_threadpool(_mark_pending_as_delivered, user_id)
    for sender_id, message_ids in delivered.items():
        await manager.send_to(
            sender_id,
            {"type": "delivered_ack", "destinataireId": user_id, "messageIds": message_ids},
        )

    try:
        while True:
            # receive_text + json.loads plutôt que receive_json : une trame non JSON
            # renvoie une erreur au lieu de couper la connexion
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            if not isinstance(payload, dict):
                await websocket.send_json(
                    _error("JSON_INVALIDE", "La trame doit être un objet JSON")
                )
                continue
            msg_type = payload.get("type")

            if msg_type == "message":
                try:
                    parsed = WSMessageIn.model_validate(payload)
                except ValidationError as err:
                    await websocket.send_json(_error("VALIDATION_ERROR", err.errors()))
                    continue

                if parsed.destinataire_id == user_id:
                    await websocket.send_json(
                        _error("DESTINATAIRE_INVALIDE", "Impossible de s'envoyer un message")
                    )
                    continue

                # Anti-spam (fenêtre glissante, comme au TP5) : le message n'est pas persisté
                retry_after = ws_message_limiter.hit(str(user_id))
                if retry_after:
                    await websocket.send_json(
                        _error(
                            "RATE_LIMITED",
                            "Trop de messages envoyés, patientez avant de réessayer",
                            retryAfter=math.ceil(retry_after),
                        )
                    )
                    continue

                # Vérification de présence immédiate du destinataire
                dest_online = manager.is_online(parsed.destinataire_id)
                initial_status = "livre" if dest_online else "envoye"

                # Persistance du message en base
                saved_msg = await run_in_threadpool(
                    _persist_message,
                    expediteur_id=user_id,
                    destinataire_id=parsed.destinataire_id,
                    contenu=parsed.contenu,
                    statut=initial_status,
                )
                if saved_msg is None:
                    await websocket.send_json(
                        _error(
                            "DESTINATAIRE_INCONNU",
                            f"Utilisateur {parsed.destinataire_id} introuvable",
                        )
                    )
                    continue

                # Si le destinataire est en ligne, on lui transmet immédiatement le message,
                # sinon on simule une notification push (webhook)
                if dest_online:
                    deliver_payload = {
                        "type": "message",
                        **saved_msg,
                    }
                    await manager.send_to(parsed.destinataire_id, deliver_payload)
                else:
                    notify_offline_recipient(parsed.destinataire_id, user_id, saved_msg["id"])

                # Confirmation d'envoi / accusé de réception retourné à l'expéditeur
                ack_payload = {
                    "type": "ack",
                    **saved_msg,
                }
                await websocket.send_json(ack_payload)

            elif msg_type == "read":
                try:
                    parsed_read = WSReadIn.model_validate(payload)
                except ValidationError as err:
                    await websocket.send_json(_error("VALIDATION_ERROR", err.errors()))
                    continue

                read_ids = await run_in_threadpool(
                    _mark_as_read_in_db,
                    reader_id=user_id,
                    sender_id=parsed_read.expediteur_id,
                )
                if read_ids and manager.is_online(parsed_read.expediteur_id):
                    await manager.send_to(
                        parsed_read.expediteur_id,
                        {
                            "type": "read_ack",
                            "readerId": user_id,
                            "messageIds": read_ids,
                        },
                    )

            elif msg_type == "typing":
                try:
                    parsed_typing = WSTypingIn.model_validate(payload)
                except ValidationError as err:
                    await websocket.send_json(_error("VALIDATION_ERROR", err.errors()))
                    continue

                if manager.is_online(parsed_typing.destinataire_id):
                    await manager.send_to(
                        parsed_typing.destinataire_id,
                        {
                            "type": "typing",
                            "expediteurId": user_id,
                            "isTyping": parsed_typing.is_typing,
                        },
                    )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    _error("TYPE_INCONNU", f"Type de message inconnu : '{msg_type}'")
                )

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)
