"""Core type definitions for Largestack AI."""
from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

class AgentStatus(str, Enum):
    IDLE = "idle"; RUNNING = "running"; PAUSED = "paused"
    COMPLETED = "completed"; FAILED = "failed"; TERMINATED = "terminated"

class SteeringAction(str, Enum):
    PROCEED = "proceed"; GUIDE = "guide"; INTERRUPT = "interrupt"
    ACCEPT = "accept"; DISCARD = "discard"

class GuardrailAction(str, Enum):
    BLOCK = "block"; WARN = "warn"; REDACT = "redact"; LOG = "log"

class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    params: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.now)

class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    error: Optional[str] = None
    duration_ms: float = 0

class LLMResponse(BaseModel):
    content: str = ""
    model: str = ""
    tool_calls: list[ToolCall] = []
    reasoning_content: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    finish_reason: str = ""

class AgentResult(BaseModel):
    content: str
    agent_name: str
    total_cost: float = 0.0
    total_tokens: int = 0
    turns: int = 0
    trace_id: str = ""
    duration_ms: float = 0.0
    tool_calls_made: list[str] = []
    status: str = "completed"

class CostEstimate(BaseModel):
    low: float
    expected: float
    high: float
    model: str
    input_tokens: int = 0
    estimated_output_tokens: int = 0

class SteeringResult(BaseModel):
    action: SteeringAction
    feedback: str = ""
    result: Optional[Any] = None

class Message(BaseModel):
    role: str
    content: str | list[dict[str, Any]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None

class ProviderConfig(BaseModel):
    name: str
    api_key: str = ""
    base_url: str = ""
    timeout: float = 120.0
    max_retries: int = 3
