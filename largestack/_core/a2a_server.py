"""A2A Server — expose LARGESTACK agents as Agent-to-Agent protocol services.

Agent Card at /.well-known/agent-card.json
Task lifecycle: submitted → working → input-required → completed | failed
"""

from __future__ import annotations
import json, uuid, time
from typing import Any


class AgentCard:
    """A2A v1.0.0 Agent Card — published at /.well-known/agent-card.json"""

    """Agent Card metadata for A2A discovery."""

    def __init__(
        self,
        name: str,
        description: str,
        capabilities: list[str] = None,
        endpoint: str = "",
        version: str = "1.0",
    ):
        self.name = name
        self.description = description
        self.capabilities = capabilities or ["text_generation"]
        self.endpoint = endpoint
        self.version = version

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "endpoint": self.endpoint,
            "version": self.version,
            "protocolVersion": "1.0.0",
            "supportedInterfaces": [{"transport": "http+sse"}],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [{"id": "default", "name": self.name, "description": self.description}],
            "discoverable": True,
        }


class A2AServer:
    """Expose a LARGESTACK agent as an A2A-compatible service."""

    def __init__(self, agent, card: AgentCard):
        self.agent = agent
        self.card = card
        self._tasks: dict[str, dict] = {}

    async def handle_task(self, task_data: dict) -> dict:
        """Handle incoming A2A task request."""
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {"status": "TASK_STATE_WORKING", "created": time.time()}

        try:
            result = await self.agent.run(task_data.get("input", ""))
            self._tasks[task_id] = {
                "status": "TASK_STATE_COMPLETED",
                "output": result.content,
                "cost": result.total_cost,
                "TASK_STATE_COMPLETED": time.time(),
            }
            return {"task_id": task_id, "status": "TASK_STATE_COMPLETED", "output": result.content}
        except Exception as e:
            self._tasks[task_id] = {"status": "TASK_STATE_FAILED", "error": str(e)}
            return {"task_id": task_id, "status": "TASK_STATE_FAILED", "error": str(e)}

    def get_task_status(self, task_id: str) -> dict:
        return self._tasks.get(task_id, {"status": "not_found"})

    def create_fastapi_routes(self, app):
        """Add A2A routes to a FastAPI app."""
        from fastapi.responses import JSONResponse

        @app.get("/.well-known/agent-card.json")
        async def agent_card():
            return JSONResponse(
                self.card.to_dict(), headers={"Content-Type": "application/a2a+json"}
            )

        @app.post("/a2a/task")
        async def create_task(data: dict):
            return await self.handle_task(data)

        @app.get("/a2a/task/{task_id}")
        async def get_task(task_id: str):
            return self.get_task_status(task_id)
