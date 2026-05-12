"""MCP Client — JSON-RPC 2.0 over stdio + Streamable HTTP."""
from __future__ import annotations
import json, logging, asyncio, uuid
from typing import Any
import httpx

log = logging.getLogger("largestack.mcp")

class MCPClient:
    """Connect to MCP servers and discover/call tools."""
    
    def __init__(self, url: str | None = None, command: str | None = None):
        self.url = url
        self.command = command
        self._tools: list[dict] = []
        self._client: httpx.AsyncClient | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False
    
    async def connect(self) -> None:
        if self.url:
            self._client = httpx.AsyncClient(timeout=30)
            init_resp = await self._rpc("initialize", {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "largestack-ai", "version": "0.1.0"}
            })
            await self._notify("notifications/initialized", {})
            # Capability negotiation: only call tools/list if server declared tools capability
            caps = init_resp.get("capabilities", {})
            if "tools" in caps or not caps:
                tools_resp = await self._rpc("tools/list", {})
            else:
                tools_resp = {"tools": []}
            self._tools = tools_resp.get("tools", [])
            self._connected = True
            log.info(f"MCP connected to {self.url}: {len(self._tools)} tools")
        elif self.command:
            await self._connect_stdio()
    
    async def _connect_stdio(self):
        parts = self.command.split()
        self._process = await asyncio.create_subprocess_exec(
            *parts, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        resp = await self._stdio_rpc("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "largestack-ai", "version": "0.1.0"}
        })
        await self._stdio_notify("notifications/initialized", {})
        tools_resp = await self._stdio_rpc("tools/list", {})
        self._tools = tools_resp.get("tools", [])
        self._connected = True
    
    async def call_tool(self, name: str, arguments: dict[str, Any] = None) -> str:
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")
        if self.url:
            result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        else:
            result = await self._stdio_rpc("tools/call", {"name": name, "arguments": arguments or {}})
        content_parts = result.get("content", [])
        return "\n".join(p.get("text", "") for p in content_parts if p.get("type") == "text")
    
    async def list_tools(self) -> list[dict]:
        return self._tools
    
    def get_tool_schemas(self) -> list[dict]:
        """Convert MCP tool schemas to LARGESTACK @tool format."""
        return [{"name": t["name"], "description": t.get("description", ""),
                 "parameters": t.get("inputSchema", {"type": "object", "properties": {}})} for t in self._tools]
    
    async def get_tools_as_callables(self) -> list:
        """Create @tool-decorated callables from MCP tools. Must be called inside async context."""
        from largestack._core.tools import tool
        callables = []
        for t in self._tools:
            tname = t["name"]
            tdesc = t.get("description", "")
            client = self  # Capture reference
            
            async def _make_fn(name=tname):
                async def mcp_call(**kwargs) -> str:
                    return await client.call_tool(name, kwargs)
                mcp_call.__name__ = name
                mcp_call.__doc__ = tdesc
                return tool(mcp_call)
            
            callables.append(await _make_fn())
        return callables
    
    async def _rpc(self, method: str, params: dict) -> dict:
        req_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        resp = await self._client.post(self.url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data: raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})
    
    async def _notify(self, method: str, params: dict) -> None:
        await self._client.post(self.url, json={"jsonrpc": "2.0", "method": method, "params": params})
    
    async def _stdio_rpc(self, method: str, params: dict) -> dict:
        req_id = str(uuid.uuid4())
        msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}) + "\n"
        self._process.stdin.write(msg.encode())
        await self._process.stdin.drain()
        line = await self._process.stdout.readline()
        data = json.loads(line.decode())
        if "error" in data: raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})
    
    async def _stdio_notify(self, method: str, params: dict) -> None:
        self._process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n").encode())
        await self._process.stdin.drain()
    
    async def disconnect(self) -> None:
        if self._client: await self._client.aclose()
        if self._process: self._process.terminate(); await self._process.wait()
        self._connected = False
    
    def scan_for_poisoning(self) -> list[dict]:
        """Scan tool descriptions for hidden prompt injections (5.5% of MCP servers)."""
        import re
        suspicious = []
        patterns = [re.compile(p, re.I) for p in [
            r"ignore\s+previous", r"system\s*prompt", r"do\s+not\s+tell",
            r"<\|", r"\[INST\]", r"override", r"pretend\s+to\s+be"]]
        for t in self._tools:
            desc = t.get("description", "")
            for p in patterns:
                if p.search(desc):
                    suspicious.append({"tool": t["name"], "pattern": p.pattern, "description": desc[:100]})
                    break
        if suspicious:
            log.warning(f"MCP POISONING: {len(suspicious)} suspicious tools at {self.url}")
        return suspicious
