"""Verbatim stop/task functions from Reachy Mini SDK 1.11.0 for patch contract tests.
Full upstream move.py SHA256 ca18dbc85041a49b784b17b0bb09c06a7c6eec82bcd8f1dd2a23d64275a18943.
Only the import/registry harness below replaces SDK dependencies; no hardware.
"""
import asyncio
from typing import Any, Coroutine
from uuid import UUID, uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
move_tasks: dict[UUID, asyncio.Task[None]] = {}
move_listeners: list[WebSocket] = []
router=APIRouter(prefix='/move')


class MoveUUID(BaseModel):
    """Model representing a unique identifier for a move task."""

    uuid: UUID


def create_move_task(coro: Coroutine[Any, Any, None]) -> MoveUUID:
    """Create a new move task using async task coroutine."""
    uuid = uuid4()

    async def notify_listeners(message: str, details: str = "") -> None:
        for ws in move_listeners:
            try:
                await ws.send_json(
                    {
                        "type": message,
                        "uuid": str(uuid),
                        "details": details,
                    }
                )
            except (RuntimeError, WebSocketDisconnect):
                move_listeners.remove(ws)

    async def wrap_coro() -> None:
        try:
            await notify_listeners("move_started")
            await coro
            await notify_listeners("move_completed")
        except Exception as e:
            await notify_listeners("move_failed", details=str(e))
        except asyncio.CancelledError:
            await notify_listeners("move_cancelled")
        finally:
            move_tasks.pop(uuid, None)

    task = asyncio.create_task(wrap_coro())
    move_tasks[uuid] = task

    return MoveUUID(uuid=uuid)


async def stop_move_task(uuid: UUID) -> dict[str, str]:
    """Stop a running move task by cancelling it."""
    if uuid not in move_tasks:
        raise KeyError(f"Running move with UUID {uuid} not found")

    task = move_tasks.pop(uuid, None)
    assert task is not None

    if task:
        if task.cancel():
            try:
                await task
            except asyncio.CancelledError:
                pass

    return {
        "message": f"Stopped move with UUID: {uuid}",
    }


@router.get("/running")
async def get_running_moves() -> list[MoveUUID]:
    """Get a list of currently running move tasks."""
    return [MoveUUID(uuid=uuid) for uuid in move_tasks.keys()]


@router.post("/stop")
async def stop_move(uuid: MoveUUID) -> dict[str, str]:
    """Stop a running move task."""
    return await stop_move_task(uuid.uuid)


