"""Sequential pipeline orchestration: A → B → C with error handling and context passing."""
from __future__ import annotations
import asyncio, logging
from typing import Any, Callable
from largestack.types import AgentResult
from largestack.errors import LargestackError

log = logging.getLogger("largestack.sequential")


class SequentialPipeline:
    """Run agents in order, passing each output as next input.
    
    Features:
      - Accumulated context across stages
      - Error recovery strategies: fail, skip, retry
      - Optional transform between stages
      - Per-stage timeouts
      - Cost and turn accumulation
    
        pipe = SequentialPipeline(
            agents=[researcher, analyst, writer],
            on_error="skip",              # or "fail" or "retry"
            max_retries=2,
            accumulate_context=True,      # pass all previous outputs
            transform=lambda out: f"Previous: {out}\nNow:",
        )
        result = await pipe.run("Topic: AI safety")
    """
    def __init__(self, agents: list, on_error: str = "fail",
                 max_retries: int = 0, accumulate_context: bool = False,
                 transform: Callable = None, timeout_per_stage: float = None):
        if not agents:
            raise ValueError("SequentialPipeline requires at least one agent")
        if on_error not in ("fail", "skip", "retry"):
            raise ValueError(f"on_error must be 'fail' | 'skip' | 'retry', got: {on_error}")
        
        self.agents = agents
        self.on_error = on_error
        self.max_retries = max_retries
        self.accumulate_context = accumulate_context
        self.transform = transform
        self.timeout_per_stage = timeout_per_stage
        self._history: list[dict] = []
    
    async def _run_stage(self, agent, input_text: str, stage_idx: int) -> AgentResult:
        """Run a single stage with optional retry and timeout."""
        last_exc = None
        attempts = self.max_retries + 1 if self.on_error == "retry" else 1
        
        for attempt in range(attempts):
            try:
                if self.timeout_per_stage:
                    return await asyncio.wait_for(
                        agent.run(input_text), timeout=self.timeout_per_stage
                    )
                return await agent.run(input_text)
            except Exception as e:
                last_exc = e
                log.warning(
                    f"Stage {stage_idx} ({getattr(agent, 'name', 'unknown')}) "
                    f"attempt {attempt+1}/{attempts} failed: {e}"
                )
        
        raise last_exc
    
    async def run(self, task: str, **kw) -> AgentResult:
        """Execute the pipeline."""
        if not self.agents:
            raise ValueError("No agents in pipeline")
        
        current_input = task
        accumulated_outputs = []
        total_cost = 0.0
        total_tokens = 0
        total_turns = 0
        all_tool_calls = []
        last_result = None
        skipped_stages = 0
        self._history = []
        
        for i, agent in enumerate(self.agents):
            # Prepare input (with optional transform + accumulation)
            stage_input = current_input
            if self.transform:
                stage_input = self.transform(current_input)
            if self.accumulate_context and accumulated_outputs:
                context_str = "\n\n".join(
                    f"[Stage {j+1} — {name}]: {out}"
                    for j, (name, out) in enumerate(accumulated_outputs)
                )
                stage_input = f"{context_str}\n\n[Current task]: {current_input}"
            
            log.info(f"Sequential: stage {i+1}/{len(self.agents)} — {getattr(agent, 'name', 'agent')}")
            
            # Execute stage
            try:
                result = await self._run_stage(agent, stage_input, i)
            except Exception as e:
                if self.on_error == "skip":
                    log.warning(f"Sequential: skipping stage {i+1} due to error: {e}")
                    self._history.append({
                        "stage": i, "agent": getattr(agent, 'name', 'unknown'),
                        "status": "skipped", "error": str(e),
                    })
                    skipped_stages += 1
                    continue  # Keep current_input as-is, proceed to next agent
                else:
                    raise LargestackError(f"Sequential pipeline failed at stage {i+1}: {e}") from e
            
            # Accumulate
            total_cost += result.total_cost
            total_tokens += result.total_tokens
            total_turns += result.turns
            all_tool_calls.extend(result.tool_calls_made)
            
            self._history.append({
                "stage": i,
                "agent": getattr(agent, 'name', 'unknown'),
                "status": "completed",
                "cost": result.total_cost,
                "turns": result.turns,
            })
            accumulated_outputs.append((getattr(agent, 'name', f'stage_{i}'), result.content))
            
            current_input = result.content
            last_result = result
        
        if last_result is None:
            raise LargestackError("Sequential pipeline produced no output (all stages skipped?)")
        
        return AgentResult(
            agent_name="sequential",
            content=last_result.content,
            total_cost=total_cost,
            total_tokens=total_tokens,
            turns=total_turns,
            tool_calls_made=all_tool_calls,
            trace_id=last_result.trace_id or "sequential",
        )
    
    @property
    def history(self) -> list[dict]:
        """Execution history from last run."""
        return list(self._history)
