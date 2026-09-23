"""Routeur WebSocket pour l'acheminement des messages en temps réel.

Spécifications du sujet (§4 et ROADMAP.md) :
- Endpoint /ws/messages?token=...
- Authentification du JWT avant websocket.accept() (fermeture 1008 si invalide)
- Validation des charges utiles avec Pydantic
- Persistance synchrone déportée via run_in_threadpool pour ne pas bloquer l'event loop
- Accusés de réception ('envoye' -> 'livre' -> 'lu')
- Nettoyage à la déconnexion
"""

from typing import Any

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.auth.security import decode_access_token
from app.core.database import SessionLocal
from app.messages.service import mark_messages_as_read, save_message
from app.realtime.manager import manager
from app.realtime.schemas import WSMessageIn, WSReadIn, WSTypingIn

router = APIRouter(tags=["Realtime"])


def _persist_message(
    expediteur_id: int,
    destinataire_id: int,
    contenu: str,
    statut: str,
) -> dict[str, Any]:
    """Exécuté dans un threadpool pour ne pas bloquer la boucle asynchrone FastAPI.

    Règle 5 : SQLAlchemy 2.0 étant configuré en mode synchrone, l'appel à la base
    depuis une fonction 'async def' doit obligatoirement être délégué à un thread worker.
    """
    with SessionLocal() as db:
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


@router.websocket("/ws/messages")
async def websocket_messages(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Canal WebSocket bidirectionnel pour l'envoi et la réception de messages.

    Règle 7 : Fermeture avec le code 1008 (Policy Violation) conformément à la RFC 6455 §7.4.1
    https://datatracker.ietf.org/doc/html/rfc6455#section-7.4.1
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await manager.connect(user_id, websocket)

    try:
        while True:
            payload = await websocket.receive_json()
            msg_type = payload.get("type")

            if msg_type == "message":
                try:
                    parsed = WSMessageIn.model_validate(payload)
                except ValidationError as err:
                    await websocket.send_json({"type": "error", "detail": err.errors()})
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

                # Si le destinataire est en ligne, on lui transmet immédiatement le message
                if dest_online:
                    deliver_payload = {
                        "type": "message",
                        **saved_msg,
                    }
                    await manager.send_to(parsed.destinataire_id, deliver_payload)

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
                    await websocket.send_json({"type": "error", "detail": err.errors()})
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
                    await websocket.send_json({"type": "error", "detail": err.errors()})
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
                    {"type": "error", "detail": f"Type de message inconnu : '{msg_type}'"}
                )

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception:
        manager.disconnect(user_id)
