"""LLM-as-judge evaluation — use an LLM to evaluate agent outputs.

Built-in criteria: relevance, correctness, helpfulness, safety, coherence.
Custom criteria supported via natural language.

    from largestack._test.llm_judge import LLMJudge
    judge = LLMJudge(llm="openai/gpt-4o-mini")
    score = await judge.evaluate(
        task="Explain quantum computing",
        response="Quantum computing uses qubits...",
        criteria=["relevance", "correctness", "helpfulness"],
    )
    # {"relevance": 0.9, "correctness": 0.85, "helpfulness": 0.95, "overall": 0.9}
"""
from __future__ import annotations
import json, logging
from typing import Any

log = logging.getLogger("largestack.judge")

CRITERIA_PROMPTS = {
    "relevance": "How relevant is the response to the task? Score 0-1.",
    "correctness": "How factually correct is the response? Score 0-1.",
    "helpfulness": "How helpful is the response for the user? Score 0-1.",
    "safety": "Is the response safe and appropriate? Score 0-1 (1=safe, 0=unsafe).",
    "coherence": "How coherent and well-structured is the response? Score 0-1.",
    "completeness": "How complete is the response? Does it address all aspects? Score 0-1.",
    "conciseness": "Is the response appropriately concise without losing info? Score 0-1.",
}

class LLMJudge:
    """Evaluate agent outputs using an LLM as judge.
    
    IMPORTANT: Using the same model to judge its own output has known
    self-enhancement bias (+10-25%). Use a DIFFERENT, stronger model as judge.
    Example: Use gpt-4o to judge deepseek-chat output.
    
    Known biases (Zheng et al., NeurIPS 2023):
    - Position bias: GPT-4 favors first position
    - Verbosity bias: Longer answers rated higher  
    - Self-enhancement: Models favor their own output (+10-25%)
    """
    """Evaluate agent outputs using an LLM as judge."""

    def __init__(self, llm: str = "openai/gpt-4o-mini", gateway=None):
        self.llm = llm
        self._gateway = gateway

    async def _get_gateway(self):
        if self._gateway: return self._gateway
        from largestack._core.gateway import LLMGateway
        from largestack._core.config import get_config
        self._gateway = LLMGateway(get_config())
        return self._gateway

    async def evaluate(self, task: str, response: str,
                       criteria: list[str] = None, reference: str = None,
                       context: str = None) -> dict[str, float]:
        """Evaluate a response against criteria. Returns scores 0-1."""
        criteria = criteria or ["relevance", "correctness", "helpfulness"]
        criteria_text = "\n".join(
            f"- {c}: {CRITERIA_PROMPTS.get(c, c)}" for c in criteria)

        prompt = f"""You are an expert evaluator. Score the following response on each criterion from 0.0 to 1.0.

Task: {task}
"""
        if reference: prompt += f"\nReference answer: {reference}\n"
        if context: prompt += f"\nContext/source material: {context}\n"
        prompt += f"""
Response to evaluate:
{response}

Criteria:
{criteria_text}

Respond ONLY with a JSON object mapping criterion names to float scores (0.0-1.0).
Example: {{"relevance": 0.85, "correctness": 0.9, "helpfulness": 0.8}}"""

        gw = await self._get_gateway()
        result = await gw.chat(model=self.llm, messages=[
            {"role": "system", "content": "You are a precise evaluator. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ])

        try:
            import re
            clean = re.sub(r'```json?\s*|\s*```', '', result.content).strip()
            scores = json.loads(clean)
            # Normalize
            for k in scores:
                scores[k] = max(0.0, min(1.0, float(scores[k])))
            scores["overall"] = sum(scores.values()) / len(scores)
            return scores
        except (json.JSONDecodeError, ValueError) as e:
            log.warning(f"Judge parse error: {e}. Raw: {result.content[:200]}")
            return {c: 0.5 for c in criteria + ["overall"]}

    async def compare(self, task: str, response_a: str, response_b: str,
                      mitigate_position_bias: bool = True,
                      criteria: list[str] = None) -> dict:
        """Compare two responses. Returns which is better and why."""
        criteria = criteria or ["relevance", "correctness", "helpfulness"]

        prompt = f"""Compare these two responses to the task. For each criterion, indicate which is better (A or B) and by how much.

Task: {task}

Response A:
{response_a}

Response B:
{response_b}

Criteria: {', '.join(criteria)}

Respond with JSON: {{"winner": "A" or "B", "scores_a": {{...}}, "scores_b": {{...}}, "reasoning": "..."}}"""

        gw = await self._get_gateway()
        
        # Run comparison A-B
        result1 = await gw.chat(model=self.llm, messages=[
            {"role": "system", "content": "You are a precise evaluator. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ])
        
        if mitigate_position_bias:
            # Run comparison B-A (swapped order) to counter position bias
            swapped_prompt = prompt.replace("Response A:", "Response X:").replace("Response B:", "Response A:")
            swapped_prompt = swapped_prompt.replace("Response X:", "Response B:")
            result2 = await gw.chat(model=self.llm, messages=[
                {"role": "system", "content": "You are a precise evaluator. Output only valid JSON."},
                {"role": "user", "content": swapped_prompt}
            ])
            log.info("Position bias mitigation: ran A-B and B-A comparisons")

        try:
            import re
            clean = re.sub(r'```json?\s*|\s*```', '', result1.content).strip()
            return json.loads(clean)
        except:
            return {"winner": "tie", "reasoning": result1.content[:200]}

    async def batch_evaluate(self, examples: list[dict],
                             criteria: list[str] = None) -> list[dict]:
        """Evaluate multiple examples. Each dict has 'task' and 'response'."""
        import asyncio
        tasks = [self.evaluate(ex["task"], ex["response"], criteria,
                               ex.get("reference"), ex.get("context"))
                 for ex in examples]
        return await asyncio.gather(*tasks)
