"""Router orchestration — LLM-based classification + specialist dispatch."""
from __future__ import annotations
import asyncio, logging, re
from typing import Any
from largestack.types import AgentResult

log = logging.getLogger("largestack.router")

class Router:
    """Route queries to specialist agents based on content classification.
    
    Uses classifier agent to categorize, then dispatches to matching specialist.
    Falls back to default_agent if no category matches.
    
        router = Router(
            classifier=triage,
            routes={
                "billing": billing_agent,
                "technical": tech_agent,
                "general": general_agent,
            },
            default="general",
        )
        result = await router.run("My credit card was charged twice")
    """
    def __init__(self, classifier, routes: dict, default: str = None,
                 use_keywords: bool = True):
        self.classifier = classifier
        self.routes = routes
        self.default = default
        self.use_keywords = use_keywords
        self._stats = {k: 0 for k in routes}
    
    def _parse_category(self, classifier_output: str) -> str | None:
        """Extract category from classifier response."""
        # Try explicit markers first
        m = re.search(r"\[CATEGORY:(\w+)\]", classifier_output, re.IGNORECASE)
        if m and m.group(1).lower() in self.routes:
            return m.group(1).lower()
        
        # Try matching route names in output
        output_lower = classifier_output.lower()
        for cat in self.routes:
            if cat.lower() in output_lower:
                return cat
        
        return None
    
    async def run(self, task: str) -> AgentResult:
        # Classify
        classify_prompt = (
            f"Classify this query into ONE category: {', '.join(self.routes.keys())}\n\n"
            f"Query: {task}\n\n"
            f"Respond with ONLY the category name."
        )
        classification = await self.classifier.run(classify_prompt)
        category = self._parse_category(classification.content)
        
        if not category:
            if self.default and self.default in self.routes:
                category = self.default
                log.info(f"Router: no match, using default '{self.default}'")
            else:
                log.warning("Router: unclassified and no default set")
                return classification
        
        # Dispatch
        self._stats[category] += 1
        specialist = self.routes[category]
        log.info(f"Router: {task[:50]}... → {category}")
        
        result = await specialist.run(task)
        return AgentResult(
            agent_name="router",
            content=result.content,
            total_cost=classification.total_cost + result.total_cost,
            total_tokens=classification.total_tokens + result.total_tokens,
            turns=2,
            tool_calls_made=result.tool_calls_made,
            trace_id="router",
        )
    
    @property
    def stats(self) -> dict:
        """Routing statistics per category."""
        total = sum(self._stats.values())
        return {
            "total_routed": total,
            "by_category": dict(self._stats),
            "distribution": {k: v/max(total,1) for k, v in self._stats.items()},
        }


# Backwards compatibility alias
RouterPattern = Router
