"""WebSocket streaming with backpressure handling."""
from __future__ import annotations
import asyncio, json
from typing import Any

class WebSocketStream:
    """Bidirectional WebSocket streaming for agent responses.
    
    Features: token streaming, tool call events, backpressure, client interrupts.
    """
    def __init__(self, max_buffer: int = 100):
        self.max_buffer = max_buffer
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=max_buffer)
        self._interrupted = False
    
    async def stream_agent(self, websocket, agent, task: str):
        """Stream agent execution over WebSocket."""
        try:
            await websocket.send_json({"type": "start", "task": task})
            
            # Run agent with streaming
            async for token in agent.stream(task):
                if self._interrupted:
                    await websocket.send_json({"type": "interrupted"})
                    break
                
                # Backpressure: wait if buffer full
                try:
                    self._buffer.put_nowait(token)
                except asyncio.QueueFull:
                    await asyncio.sleep(0.01)  # Brief pause for client to catch up
                    await self._buffer.put(token)
                
                await websocket.send_json({"type": "token", "content": token})
            
            await websocket.send_json({"type": "done"})
        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
    
    async def handle_client_message(self, data: dict):
        """Handle incoming client messages (interrupts, feedback)."""
        if data.get("type") == "interrupt":
            self._interrupted = True
        elif data.get("type") == "feedback":
            pass  # Store for agent learning
    
    def create_fastapi_route(self, app, agent):
        """Add WebSocket route to FastAPI app."""
        from fastapi import WebSocket, WebSocketDisconnect
        
        @app.websocket("/ws/agent")
        async def ws_agent(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "task":
                        await self.stream_agent(websocket, agent, data["content"])
                    else:
                        await self.handle_client_message(data)
            except WebSocketDisconnect:
                pass
