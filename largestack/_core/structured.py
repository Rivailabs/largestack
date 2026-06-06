"""Structured output — native provider APIs with prompt fallback.

Priority:
1. Native response_format json_schema (OpenAI-compatible) — provider-enforced,
   validated + parse-retried by ``parse_structured``
2. Native tool_use (Anthropic) — constrained decoding
3. Native response_schema (Gemini)
4. Prompt injection fallback — for providers without native support
"""
from __future__ import annotations
import json, logging, re
from typing import Any, Type
from pydantic import BaseModel, ValidationError

log = logging.getLogger("largestack.structured")


def _resolve_provider(model: str) -> str:
    """Resolve the provider for a model string, including bare/prefix-routed
    names (e.g. ``gpt-4o`` -> openai) via the gateway's MODEL_PREFIX_MAP — so
    native structured output isn't silently skipped for un-prefixed models."""
    if "/" in model:
        return model.split("/")[0].lower()
    try:
        from largestack._core.gateway import MODEL_PREFIX_MAP
        for prefix, provider in MODEL_PREFIX_MAP.items():
            if model.startswith(prefix):
                return provider
    except Exception:
        pass
    return ""


def _strictify_schema(schema: Any) -> Any:
    """Recursively add ``additionalProperties: false`` to every object schema.

    OpenAI's strict json_schema mode *requires* this on every object (pydantic's
    model_json_schema() omits it), and returns HTTP 400 otherwise — which made
    the native OpenAI path silently fail and fall back to prompt mode. We also
    recurse into properties / items / $defs / combinators.
    """
    if isinstance(schema, dict):
        out = dict(schema)
        if out.get("type") == "object" or "properties" in out:
            out.setdefault("additionalProperties", False)
        for key in ("properties", "$defs", "definitions"):
            if isinstance(out.get(key), dict):
                out[key] = {k: _strictify_schema(v) for k, v in out[key].items()}
        if "items" in out:
            out["items"] = _strictify_schema(out["items"])
        for comb in ("anyOf", "allOf", "oneOf"):
            if isinstance(out.get(comb), list):
                out[comb] = [_strictify_schema(s) for s in out[comb]]
        return out
    return schema


def build_native_params(model: str, schema: dict) -> dict:
    """Build provider-specific structured output parameters."""
    provider = _resolve_provider(model)

    if provider in ("openai", "groq", "together", "fireworks",
                     "perplexity", "cerebras", "xai", "nvidia", "openrouter"):
        # OpenAI-compatible: response_format with JSON schema.
        # NOTE: deepseek is intentionally excluded — its API rejects strict
        # `json_schema` response_format (confirmed live). It is routed to the
        # prompt fallback below. Any other provider that rejects these params is
        # caught in run_structured() and also falls back to prompt mode.
        # strict=False + additionalProperties:false: avoids the HTTP 400 that
        # strict=True caused on pydantic schemas lacking additionalProperties,
        # while still steering the model; parse_structured validates + retries.
        return {"response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.get("title", "Response"),
                           "schema": _strictify_schema(schema), "strict": False}
        }}
    elif provider == "anthropic":
        # Anthropic: tool_use for constrained output.
        # NOTE: we emit OpenAI-shape `parameters` (not the Anthropic-native
        # `input_schema`) because anthropic_prov.py re-wraps every tool entry
        # via `{name, description, input_schema=t["parameters"]}`. Emitting
        # `input_schema` here would be silently dropped and the schema lost.
        # The engine's _is_structured_tool_call() intercepts the matching
        # tool_use as the final structured answer rather than a normal tool call.
        return {"tools": [{
            "name": "structured_output",
            "description": "Return structured data matching the schema",
            "parameters": schema
        }], "tool_choice": {"type": "tool", "name": "structured_output"}}
    elif provider == "google":
        # Google Gemini: response_schema
        return {"response_mime_type": "application/json", "response_schema": schema}
    elif provider == "ollama":
        # Ollama native /api/chat structured outputs — pass the JSON schema as `format`
        # (constrained decoding). Makes typed output reliable even on small local models.
        return {"format": schema}

    return {}  # No native support — will fall back to prompt

def build_structured_prompt(model_class: Type[BaseModel], task: str) -> str:
    """Fallback: append JSON schema to prompt (for providers without native support)."""
    schema = model_class.model_json_schema()
    return (f"{task}\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```\n"
            f"No text outside the JSON.")

def parse_structured(content: str, model_class: Type[BaseModel]) -> BaseModel:
    """Parse LLM response into Pydantic model."""
    # Try direct parse
    for attempt in [content.strip(), 
                    re.sub(r'^```json?\s*|\s*```$', '', content.strip(), flags=re.MULTILINE).strip()]:
        try:
            return model_class.model_validate_json(attempt)
        except (ValidationError, json.JSONDecodeError):
            pass
    # Extract JSON from mixed content
    # Find JSON by balanced braces (handles nested objects)
    start = content.find('{')
    if start == -1: raise ValueError(f"No JSON found in: {content[:200]}")
    depth = 0
    for i, ch in enumerate(content[start:], start):
        if ch == '{': depth += 1
        elif ch == '}': depth -= 1
        if depth == 0:
            match_str = content[start:i+1]
            break
    else:
        match_str = None
    if match_str:
        try:
            return model_class.model_validate_json(match_str)
        except (ValidationError, json.JSONDecodeError):
            pass
        # Try flexible field mapping — LLMs often use different field names
        try:
            raw = json.loads(match_str)
            if isinstance(raw, dict):
                schema_fields = set(model_class.model_fields.keys())
                # Try direct construction with available fields
                mapped = {}
                for field_name in schema_fields:
                    if field_name in raw:
                        mapped[field_name] = raw[field_name]
                    else:
                        # Fuzzy match: snake_case variants, partial matches
                        for k, v in raw.items():
                            k_norm = k.lower().replace(" ", "_").replace("-", "_")
                            if field_name in k_norm or k_norm in field_name:
                                mapped[field_name] = v
                                break
                if mapped:
                    try:
                        return model_class.model_validate(mapped)
                    except ValidationError:
                        pass
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse as {model_class.__name__}: {content[:200]}")

async def run_structured(agent, task: str, response_model: Type[BaseModel],
                         max_retries: int = 2, **kw) -> BaseModel:
    """Run agent with structured output. Returns the validated Pydantic model.

    Order of preference:
    1. Native structured output (OpenAI json_schema, Anthropic tool_use, Gemini schema).
    2. Prompt-injection fallback — used when the provider has no native support, OR
       when the native call is rejected by the provider. DeepSeek and several
       OpenAI-compatible providers don't support strict json_schema, so without this
       fallback structured output would fail outright on them.
    """
    parsed, _ = await run_structured_with_result(agent, task, response_model, max_retries, **kw)
    return parsed


async def run_structured_with_result(agent, task: str, response_model: Type[BaseModel],
                                      max_retries: int = 2, **kw):
    """Like ``run_structured`` but also returns the underlying ``AgentResult``
    (cost / trace_id / tool calls), so callers such as the typed decorator API can
    use native structured output AND report real usage. Returns ``(model, result)``;
    ``result`` is the last engine AgentResult (or None if unavailable)."""
    from largestack.errors import ProviderError  # AllProvidersFailedError subclasses this

    schema = response_model.model_json_schema()
    native_params = build_native_params(agent.llm, schema)
    last_result = None

    # 1. Native path — provider-enforced structured output.
    if native_params:
        native_task = task
        for attempt in range(max_retries + 1):
            try:
                result = await agent._engine.execute(native_task, **{**kw, **native_params})
                last_result = result
                content = result.content
                # Anthropic tool_use returns the structured payload as a dict.
                if isinstance(content, dict):
                    return response_model.model_validate(content), result
                return parse_structured(content, response_model), result
            except ProviderError as e:
                # Provider rejected the native structured params — fall back to prompt mode.
                log.debug(f"native structured output rejected ({type(e).__name__}); "
                          f"using prompt fallback: {e}")
                break
            except (ValueError, ValidationError) as e:
                if attempt < max_retries:
                    native_task = f"Previous response was invalid: {e}\n\n{native_task}"
                else:
                    log.debug(f"native structured output unparseable; using prompt fallback: {e}")
                    break

    # 2. Prompt-injection fallback (no native support, or native rejected/unparseable).
    structured_task = build_structured_prompt(response_model, task)
    for attempt in range(max_retries + 1):
        result = await agent._engine.execute(structured_task, **kw)
        last_result = result
        try:
            return parse_structured(result.content, response_model), result
        except ValueError as e:
            if attempt < max_retries:
                structured_task = f"Invalid JSON: {e}\n\n{structured_task}"
            else:
                raise
