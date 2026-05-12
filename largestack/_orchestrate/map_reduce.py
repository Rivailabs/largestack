"""Map-reduce orchestration — parallel map + synthesis reduce.

Splits work across many agents in parallel, then aggregates with a reducer.
Pattern used in document processing, code review, data analysis.
"""
from __future__ import annotations
import asyncio, logging
from typing import Any, Callable
from largestack.types import AgentResult

log = logging.getLogger("largestack.mapreduce")

class MapReduce:
    """Map tasks to mapper agents, reduce results with reducer agent.
    
        mapper = Agent(name="summarizer", instructions="Summarize in 2 sentences")
        reducer = Agent(name="aggregator", instructions="Combine summaries into a report")
        
        mr = MapReduce(mapper=mapper, reducer=reducer)
        result = await mr.run(items=["doc1", "doc2", "doc3"])
    """
    def __init__(self, mapper, reducer, max_concurrency: int = 10,
                 on_error: str = "skip"):
        self.mapper = mapper
        self.reducer = reducer
        self.max_concurrency = max_concurrency
        self.on_error = on_error  # 'skip' | 'fail' | 'retry'
    
    async def _map_one(self, item: Any, sem: asyncio.Semaphore, idx: int) -> tuple[int, Any]:
        """Run mapper on one item with concurrency limit."""
        async with sem:
            try:
                result = await self.mapper.run(str(item))
                return (idx, result)
            except Exception as e:
                log.error(f"MapReduce: mapper failed on item {idx}: {e}")
                if self.on_error == "fail":
                    raise
                return (idx, None)
    
    async def run(self, items: list[Any]) -> AgentResult:
        if not items:
            raise ValueError("MapReduce: items list is empty")
        
        sem = asyncio.Semaphore(self.max_concurrency)
        tasks = [self._map_one(item, sem, i) for i, item in enumerate(items)]
        
        log.info(f"MapReduce: mapping {len(items)} items (concurrency={self.max_concurrency})")
        map_results = await asyncio.gather(*tasks)
        
        # Filter out failures
        valid = [(i, r) for i, r in map_results if r is not None]
        if not valid:
            raise RuntimeError("MapReduce: all mappers failed")
        
        # Compute map metrics
        map_cost = sum(r.total_cost for _, r in valid)
        map_tokens = sum(r.total_tokens for _, r in valid)
        
        # Reduce step
        combined_input = "\n\n".join(
            f"[Item {i+1}]: {r.content}" for i, r in valid
        )
        reduce_task = (
            f"Synthesize these {len(valid)} results into a single coherent answer:\n\n"
            f"{combined_input}"
        )
        
        log.info(f"MapReduce: reducing {len(valid)} results")
        final = await self.reducer.run(reduce_task)
        
        return AgentResult(
            agent_name="map_reduce",
            content=final.content,
            total_cost=map_cost + final.total_cost,
            total_tokens=map_tokens + final.total_tokens,
            turns=len(valid) + 1,
            tool_calls_made=[],
            trace_id="mapreduce",
        )
