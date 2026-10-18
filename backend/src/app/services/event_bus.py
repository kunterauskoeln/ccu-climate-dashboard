
import asyncio

subscribers: set[asyncio.Queue] = set()

async def broadcast_event(data: dict):
    for queue in list(subscribers):
        await queue.put(data)
