from app.core.websocket_manager import manager


async def dispatch_event(user_id: str, event_type: str, payload: dict):
    await manager.send_to_user(user_id, {
        "event": event_type,
        "data": payload
    })


async def dispatch_role_event(role: str, event_type: str, payload: dict):
    await manager.send_to_role(role, {
        "event": event_type,
        "data": payload
    })