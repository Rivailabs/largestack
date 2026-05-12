"""Structured output — native provider APIs with prompt fallback.

Priority: 
1. Native response_format (OpenAI) — 100% compliance
2. Native tool_use (Anthropic) — constrained decoding
3. Prompt injection fallback — for providers without native support
"""
from __future__ import annotations
import json, logging, re
from typing import Any, Type
from pydantic import BaseModel, ValidationError

log = logging.getLogger("largestack.structured")

def build_native_params(model: str, schema: dict) -> dict:
    """Build provider-specific structured output parameters."""
    provider = model.split("/")[0].lower() if "/" in model else ""
    
    if provider in ("openai", "deepseek", "groq", "together", "fireworks", 
                     "perplexity", "cerebras", "xai", "nvidia", "openrouter"):
        # OpenAI-compatible: response_format with JSON schema
        return {"response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.get("title", "Response"), 
                           "schema": schema, "strict": True}
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
    """Run agent with native structured output. Falls back to prompt if provider lacks support."""
    schema = response_model.model_json_schema()
    native_params = build_native_params(agent.llm, schema)
    
    if native_params:
        # Native path — provider guarantees valid JSON
        for attempt in range(max_retries + 1):
            try:
                # Pass native params through to gateway
                result = await agent._engine.execute(task, **{**kw, **native_params})
                content = result.content
                # Anthropic tool_use returns in tool result
                if isinstance(content, dict):
                    return response_model.model_validate(content)
                return parse_structured(content, response_model)
            except (ValueError, ValidationError) as e:
                if attempt < max_retries:
                    task = f"Previous response was invalid: {e}\n\n{task}"
                else:
                    raise
    else:
        # Fallback — prompt injection for unknown providers
        structured_task = build_structured_prompt(response_model, task)
        for attempt in range(max_retries + 1):
            result = await agent._engine.execute(structured_task, **kw)
            try:
                return parse_structured(result.content, response_model)
            except ValueError as e:
                if attempt < max_retries:
                    structured_task = f"Invalid JSON: {e}\n\n{structured_task}"
                else:
                    raise
