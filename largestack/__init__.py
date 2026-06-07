"""Largestack AI — Universal Multi-Agent AI Framework.

from largestack import Agent, Team, Workflow, tool

@tool
async def search(query: str) -> str:
    return f"Results: {query}"

agent = Agent(name="r", tools=[search], llm="deepseek/deepseek-chat")
result = await agent.run("Analyze trends")

# Structured output
result = await agent.run("Analyze", response_model=MySchema)

# Multi-agent with error recovery
team = Team(agents=[a1, a2, a3], on_error="skip", retries_per_agent=2)
"""

__version__ = "1.1.1"

# v0.3.7: auto-install logging redaction filter in production. Strips
# API keys / Bearer tokens / JWTs from log records before they're emitted.
# Disable via LARGESTACK_DISABLE_LOG_REDACTION=1 (not recommended).
import os as _os

# v1.1.1: load a project .env into the environment on import (first-run convenience).
# Does NOT override already-set vars (shell/CI/Docker secrets always win). Opt out
# with LARGESTACK_NO_DOTENV=1. Zero-dependency minimal parser.
try:
    from largestack._core.env import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass  # never let .env loading break package import

if _os.environ.get("LARGESTACK_DISABLE_LOG_REDACTION", "").lower() not in ("1", "true", "yes"):
    try:
        from largestack._observe.log_redaction import install_redaction_filter

        install_redaction_filter()
    except Exception:
        pass  # Never let log-filter install break package import
del _os

_BENCHMARK_SUBPROCESS = __import__("os").environ.get(
    "LARGESTACK_BENCHMARK_SUBPROCESS", ""
).lower() in ("1", "true", "yes")
if _BENCHMARK_SUBPROCESS:
    # Keep benchmark subprocesses lightweight and independent of optional ML imports.
    from largestack.agent import Agent
    from largestack.testing import TestModel

    __all__ = ["Agent", "TestModel"]
else:
    from largestack.agent import Agent
    from largestack.team import Team
    from largestack.workflow import Workflow
    from largestack.orchestrator import Orchestrator, OrchestratorResult
    from largestack._core.tools import tool
    from largestack._core.streaming import StreamHandler
    from largestack._core.context import AgentContext
    from largestack._core.session import SessionStore
    from largestack._core.hitl import HumanInTheLoop
    from largestack._core.registry import AgentRegistry
    from largestack._guard.tool_access import ToolAccessPolicy
    from largestack._guard.agent_identity import AgentIdentityManager
    from largestack._guard.memory_integrity import MemoryIntegrityChecker
    from largestack._guard.inter_agent_auth import InterAgentAuth
    from largestack._core.ag_ui import AGUIServer

    from largestack._core.steering import (
        steer_before_tool,
        steer_after_model,
        proceed,
        guide,
        interrupt,
        accept,
        discard,
    )

    from largestack._guard.pipeline import GuardrailPipeline as Guardrails
    from largestack._guard.pii import PIIGuard
    from largestack._guard.injection import InjectionGuard
    from largestack._guard.output_sanitizer import OutputSanitizer
    from largestack.guardrails import create_guardrails

    from largestack._memory.buffer import ConversationMemory
    from largestack._memory.episodic import EpisodicMemory
    from largestack._memory.observational import ObservationalMemory
    from largestack._memory.procedural import ProceduralMemory
    from largestack._memory.semantic import SemanticMemory
    from largestack._memory.graph import GraphMemory
    from largestack._memory.shared import SharedMemorySpace
    from largestack.memory import create_memory
    from largestack.rag import create_rag
    from largestack.secure_rag import SecureRAGAgent, SecureRagResult
    from largestack.observability import Monitor, FeedbackRecord
    from largestack.provider_matrix import (
        provider_support_matrix,
        get_provider_capabilities,
        tool_capable_providers,
        check_connection,
    )
    from largestack.autonomous_builder import (
        AutonomousProjectBuilder,
        BuilderBudget,
        BuildReport,
        GeneratedFile,
        NoOpMemory,
        PatchSet,
        ProjectBuildPlan,
        ProjectSpec,
        RepairAttempt,
        ValidationResult,
    )

    # Decorator API (PydanticAI-style) — v0.1.1.3
    from largestack.decorators import (
        Agent as TypedAgent,
        RunContext,
        ModelRetry,
        AgentRunResult,
        ToolDefinition,
    )

    # Testing utilities
    from largestack.testing import (
        TestModel,
        FunctionModel,
        capture_run_messages,
        disable_model_requests,
        enable_model_requests,
        block_model_requests,
        ALLOW_MODEL_REQUESTS,
    )

    # MCP (Model Context Protocol): expose Largestack tools to MCP clients via the
    # stdio server, and connect OUT to external MCP servers via the client.
    from largestack._core.mcp_server import MCPServer
    from largestack._core.mcp_client import MCPClient

    from largestack.types import AgentResult, ToolCall, ToolResult, LLMResponse, CostEstimate
    from largestack.errors import (
        LargestackError,
        BudgetExceededError,
        LoopDetectedError,
        ProviderError,
        GuardrailBlockedError,
        KillSwitchActivatedError,
        ToolExecutionError,
        ToolPermissionError,
        ModelRequestsBlockedError,
    )

    __all__ = [
        "Agent",
        "Team",
        "Workflow",
        "Orchestrator",
        "OrchestratorResult",
        "tool",
        "StreamHandler",
        "TypedAgent",
        "RunContext",
        "ModelRetry",
        "AgentRunResult",
        "ToolDefinition",
        "TestModel",
        "FunctionModel",
        "capture_run_messages",
        "disable_model_requests",
        "enable_model_requests",
        "block_model_requests",
        "ALLOW_MODEL_REQUESTS",
        "MCPServer",
        "MCPClient",
        "AgentContext",
        "SessionStore",
        "HumanInTheLoop",
        "AgentRegistry",
        "AGUIServer",
        "ToolAccessPolicy",
        "AgentIdentityManager",
        "MemoryIntegrityChecker",
        "InterAgentAuth",
        "steer_before_tool",
        "steer_after_model",
        "proceed",
        "guide",
        "interrupt",
        "accept",
        "discard",
        "Guardrails",
        "create_guardrails",
        "PIIGuard",
        "InjectionGuard",
        "OutputSanitizer",
        "ConversationMemory",
        "EpisodicMemory",
        "ObservationalMemory",
        "ProceduralMemory",
        "SemanticMemory",
        "GraphMemory",
        "SharedMemorySpace",
        "create_memory",
        "create_rag",
        "SecureRAGAgent",
        "SecureRagResult",
        "Monitor",
        "FeedbackRecord",
        "provider_support_matrix",
        "get_provider_capabilities",
        "tool_capable_providers",
        "check_connection",
        "AutonomousProjectBuilder",
        "BuilderBudget",
        "BuildReport",
        "GeneratedFile",
        "NoOpMemory",
        "PatchSet",
        "ProjectBuildPlan",
        "ProjectSpec",
        "RepairAttempt",
        "ValidationResult",
        "AgentResult",
        "ToolCall",
        "ToolResult",
        "LLMResponse",
        "CostEstimate",
        "LargestackError",
        "BudgetExceededError",
        "LoopDetectedError",
        "ProviderError",
        "GuardrailBlockedError",
        "KillSwitchActivatedError",
        "ToolExecutionError",
        "ToolPermissionError",
        "ModelRequestsBlockedError",
    ]
