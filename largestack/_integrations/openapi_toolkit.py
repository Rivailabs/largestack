"""OpenAPI Toolkit — auto-generate LARGESTACK tools from any OpenAPI spec (v0.8.0).

Single highest-leverage integration: instead of writing N adapters for
N services, point this at any OpenAPI/Swagger spec URL and every endpoint
becomes a LARGESTACK @tool callable. Works with thousands of public APIs
(Stripe, Twilio, GitHub, Slack, etc.) and any internal service that
publishes a spec.

Usage:

    from largestack._integrations.openapi_toolkit import OpenAPIToolkit
    from largestack import Agent

    # Pull spec from URL or pass dict
    toolkit = await OpenAPIToolkit.from_url("https://petstore.swagger.io/v2/swagger.json")
    agent = Agent(name="api", llm="...", tools=toolkit.get_tools())

    # Or build from dict
    toolkit = OpenAPIToolkit(spec_dict)

Supports:
- OpenAPI 3.0 + 3.1 (the standard since 2017)
- Swagger 2.0 (legacy but still common — auto-converted to OpenAPI 3 shape)
- All HTTP verbs (GET/POST/PUT/PATCH/DELETE)
- Path parameters, query parameters, request body (JSON)
- Authentication: Bearer token, API key (header or query)
- Multiple servers (picks first by default)

Each operation becomes a tool whose:
- Name = ``operationId`` (or ``METHOD_path`` if missing)
- Description = ``summary`` + ``description``
- Parameters = JSON Schema from the spec (LLM gets correct types)

Errors are caught and returned as strings — agent loop survives.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Callable

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.openapi_toolkit")


_NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_]+")


def _safe_tool_name(method: str, path: str, op_id: str | None = None) -> str:
    """Generate a safe Python identifier for a tool name."""
    if op_id:
        # operationId is the canonical name
        name = _NAME_SAFE_RE.sub("_", op_id).strip("_")
        if name and name[0].isalpha():
            return name
    # Fallback: METHOD_path with separators normalized
    slug = _NAME_SAFE_RE.sub("_", path).strip("_")
    return f"{method.lower()}_{slug}".strip("_") or f"{method.lower()}_op"


class OpenAPIToolkit:
    """Auto-generate tools from an OpenAPI spec.

    Args:
        spec: OpenAPI 3.x or Swagger 2.x dict.
        base_url: override server URL (else first ``servers[0].url``).
        auth_header: ``("Authorization", "Bearer xxx")`` style.
        api_key_header: dict like ``{"X-API-Key": "xxx"}``.
        api_key_query: dict like ``{"api_key": "xxx"}`` to attach to all queries.
        timeout: per-request HTTP timeout in seconds (default 30).
        max_response_chars: truncate response bodies to this many chars
            (default 50000) to keep them LLM-context-friendly.
    """

    def __init__(
        self,
        spec: dict,
        *,
        base_url: str | None = None,
        auth_header: tuple[str, str] | None = None,
        api_key_header: dict[str, str] | None = None,
        api_key_query: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_response_chars: int = 50_000,
    ):
        if not isinstance(spec, dict) or not spec:
            raise ValueError("spec must be a non-empty dict")
        self.spec = spec
        self.timeout = timeout
        self.max_response_chars = max_response_chars
        self._auth_header = auth_header
        self._api_key_header = api_key_header or {}
        self._api_key_query = api_key_query or {}
        self.base_url = self._resolve_base_url(base_url)
        self._tools: list[Callable] = []
        self._build_tools()

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        base_url: str | None = None,
        **kwargs,
    ) -> "OpenAPIToolkit":
        """Fetch a spec from URL and build the toolkit.

        Supports both JSON and YAML specs (auto-detected from content).
        """
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url, follow_redirects=True)
            if r.status_code >= 400:
                raise ValueError(f"failed to fetch spec from {url}: HTTP {r.status_code}")
            text = r.text

        try:
            spec = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore

                spec = yaml.safe_load(text)
            except ImportError:
                raise ValueError("spec doesn't parse as JSON; install pyyaml for YAML support")
            except yaml.YAMLError as e:
                raise ValueError(f"spec is neither valid JSON nor YAML: {e}")

        return cls(spec, base_url=base_url, **kwargs)

    def _resolve_base_url(self, override: str | None) -> str:
        if override:
            return override.rstrip("/")
        # OpenAPI 3.x
        servers = self.spec.get("servers") or []
        if servers and isinstance(servers, list):
            url = servers[0].get("url", "")
            if url:
                return url.rstrip("/")
        # Swagger 2.x
        host = self.spec.get("host", "")
        scheme = "https"
        schemes = self.spec.get("schemes") or []
        if "https" not in schemes and schemes:
            scheme = schemes[0]
        base_path = self.spec.get("basePath", "") or ""
        if host:
            return f"{scheme}://{host}{base_path}".rstrip("/")
        return ""

    def _build_tools(self) -> None:
        """Walk all paths and generate one tool per operation."""
        paths = self.spec.get("paths") or {}
        for path_template, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            # Path-level parameters apply to all methods
            common_params = methods.get("parameters") or []
            for method, op in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not isinstance(op, dict):
                    continue
                tool_fn = self._build_one(method, path_template, op, common_params)
                if tool_fn is not None:
                    self._tools.append(tool_fn)

    def _build_one(
        self,
        method: str,
        path_template: str,
        op: dict,
        common_params: list,
    ) -> Callable | None:
        """Build a single @tool callable for an operation."""
        op_id = op.get("operationId")
        name = _safe_tool_name(method, path_template, op_id)
        description = (op.get("summary") or "") + "\n" + (op.get("description") or "")
        description = description.strip() or f"{method.upper()} {path_template}"

        # Combine parameters: path-level + operation-level
        all_params = list(common_params) + list(op.get("parameters") or [])
        # De-dupe by (name, in)
        seen: dict = {}
        for p in all_params:
            if isinstance(p, dict) and "name" in p:
                seen[(p["name"], p.get("in"))] = p
        params = list(seen.values())

        # Determine if there's a request body
        request_body_schema = None
        rb = op.get("requestBody")
        if isinstance(rb, dict):
            content = rb.get("content") or {}
            json_ct = content.get("application/json") or {}
            request_body_schema = json_ct.get("schema")

        # Build the JSON schema for tool params (LLM-facing)
        tool_schema = self._build_param_schema(params, request_body_schema)

        toolkit = self  # for closure access

        @tool(name=name, description=description, timeout=int(self.timeout) + 5)
        async def _operation(**kwargs) -> str:
            try:
                return await toolkit._call_operation(
                    method=method,
                    path_template=path_template,
                    params=params,
                    request_body_schema=request_body_schema,
                    kwargs=kwargs,
                )
            except Exception as e:
                return f"OpenAPI tool {name} failed: {e}"

        # Attach the LLM-facing schema
        if tool_schema:
            _operation._openapi_schema = tool_schema  # type: ignore
            _operation.parameters = tool_schema  # type: ignore
        return _operation

    @staticmethod
    def _build_param_schema(params: list, request_body_schema: dict | None) -> dict:
        """Construct JSON Schema for the tool's params.

        Combines path/query/header parameters with the request body
        (placed under 'body' key for clarity).
        """
        properties: dict = {}
        required: list = []
        for p in params:
            if not isinstance(p, dict):
                continue
            pname = p.get("name")
            if not pname:
                continue
            schema = p.get("schema") or {}
            properties[pname] = dict(schema)
            properties[pname]["x-openapi-in"] = p.get("in", "query")
            if p.get("required"):
                required.append(pname)
        if request_body_schema:
            properties["body"] = dict(request_body_schema)
            properties["body"]["x-openapi-in"] = "body"
            required.append("body")
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    async def _call_operation(
        self,
        *,
        method: str,
        path_template: str,
        params: list,
        request_body_schema: dict | None,
        kwargs: dict,
    ) -> str:
        """Execute the HTTP call for a generated operation."""
        # Substitute path parameters
        path = path_template
        path_param_names = {
            p["name"] for p in params if isinstance(p, dict) and p.get("in") == "path"
        }
        for pname in path_param_names:
            if pname in kwargs:
                value = kwargs.pop(pname)
                path = path.replace("{" + pname + "}", str(value))

        # Build query string from query params + injected api_key_query
        query: dict = dict(self._api_key_query)
        query_param_names = {
            p["name"] for p in params if isinstance(p, dict) and p.get("in") == "query"
        }
        for qname in query_param_names:
            if qname in kwargs:
                query[qname] = kwargs.pop(qname)

        # Header parameters from spec
        headers: dict[str, str] = {}
        header_param_names = {
            p["name"] for p in params if isinstance(p, dict) and p.get("in") == "header"
        }
        for hname in header_param_names:
            if hname in kwargs:
                headers[hname] = str(kwargs.pop(hname))

        # Auth headers (always applied)
        if self._auth_header:
            headers[self._auth_header[0]] = self._auth_header[1]
        for k, v in self._api_key_header.items():
            headers[k] = v

        # Body
        body = None
        if request_body_schema and "body" in kwargs:
            body = kwargs.pop("body")
            headers.setdefault("Content-Type", "application/json")

        # Anything left in kwargs is an unknown param — log but don't fail
        if kwargs:
            log.debug(
                f"OpenAPI tool {method} {path}: unknown kwargs ignored: {list(kwargs.keys())}"
            )

        url = self.base_url + path
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            req_kw: dict = {"params": query or None, "headers": headers or None}
            if body is not None:
                req_kw["json"] = body
            r = await client.request(method.upper(), url, **req_kw)

        # Format response
        text = r.text
        if len(text) > self.max_response_chars:
            text = text[: self.max_response_chars] + f"...[truncated, total {len(r.text)} chars]"

        return json.dumps(
            {
                "status": r.status_code,
                "url": str(r.url),
                "body": text,
            }
        )

    def get_tools(self) -> list[Callable]:
        """Return all generated tools as a list."""
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)
