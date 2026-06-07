from __future__ import annotations

import asyncio

import uvicorn

from realtime_assistant.dashboard import app


async def start_dashboard(host: str = "0.0.0.0", port: int = 8000) -> asyncio.Task[None]:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    return asyncio.create_task(server.serve())
