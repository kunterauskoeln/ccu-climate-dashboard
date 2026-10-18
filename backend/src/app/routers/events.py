import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.event_bus import subscribers

router = APIRouter(tags=["events"])

@router.get("/heating")
async def heating_events():

    async def event_generator():
        # Sofort ein Event senden
        yield "data: {\"status\": \"connected\"}\n\n"

        queue = asyncio.Queue()
        subscribers.add(queue)

        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
