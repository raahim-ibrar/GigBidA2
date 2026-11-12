"""Future SSE bridge: use durable run event IDs and reconnect/replay from the last event."""

import json


def encode_sse(event: str, data: dict, event_id: int) -> str:
    if "\n" in event or "\r" in event or event_id < 0:
        raise ValueError("Invalid SSE metadata")
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(data)}\n\n"
