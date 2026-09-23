from unittest.mock import AsyncMock

import pytest

from app.realtime.manager import ConnectionManager


@pytest.mark.anyio
async def test_connection_manager_lifecycle() -> None:
    manager = ConnectionManager()
    dummy_ws = AsyncMock()

    assert not manager.is_online(1)

    await manager.connect(1, dummy_ws)
    assert manager.is_online(1)

    payload = {"type": "message", "contenu": "salut"}
    success = await manager.send_to(1, payload)
    assert success is True
    dummy_ws.send_json.assert_awaited_once_with(payload)

    # Vérification du comportement lorsque le destinataire est déconnecté
    assert not manager.is_online(2)
    success_offline = await manager.send_to(2, payload)
    assert success_offline is False

    manager.disconnect(1)
    assert not manager.is_online(1)


@pytest.mark.anyio
async def test_connection_manager_handles_broken_socket() -> None:
    manager = ConnectionManager()
    broken_ws = AsyncMock()
    # Simule une socket rompue lors de la tentative de transmission
    broken_ws.send_json.side_effect = RuntimeError("Socket disconnected")

    await manager.connect(42, broken_ws)
    assert manager.is_online(42)

    sent = await manager.send_to(42, {"type": "ping"})
    assert sent is False
    # La socket défaillante doit être évincée automatiquement du registre
    assert not manager.is_online(42)
