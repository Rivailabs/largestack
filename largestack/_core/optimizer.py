"""DSPy-style prompt optimizer — improves prompts via metric optimization.

Uses a meta-LLM to refine prompts based on eval scores.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

log = logging.getLogger("largestack.optimizer")


@dataclass
class OptimizationResult:
    initial_prompt: str
    best_prompt: str
    initial_score: float
    best_score: float
    iterations: int
    history: list[dict]


class PromptOptimizer:
    """Optimize an agent's prompt by iterative refinement.

    Args:
        metric: async fn(prompt, examples) -> float
        meta_llm: LLM used to propose new prompts
    """

    def __init__(
        self,
        metric: Callable,
        meta_llm: str = "openai/gpt-4o-mini",
        max_iterations: int = 5,
        patience: int = 2,
    ):
        self.metric = metric
        self.meta_llm = meta_llm
        self.max_iterations = max_iterations
        self.patience = patience

    async def optimize(
        self, initial_prompt: str, examples: list, eval_examples: list | None = None
    ) -> OptimizationResult:
        """Optimize prompt. Uses train (examples) for selection, eval_examples for scoring.

        If eval_examples is None, splits examples 70/30.
        """
        from largestack import Agent

        # Train/eval split
        if eval_examples is None:
            split = max(1, int(len(examples) * 0.7))
            train_examples = examples[:split]
            eval_examples = examples[split:] or examples
        else:
            train_examples = examples

        meta = Agent(
            name="optimizer",
            llm=self.meta_llm,
            instructions="You improve prompts. Output only the new prompt.",
        )

        current_prompt = initial_prompt
        initial_score = await self._score(current_prompt, eval_examples)
        best_score = initial_score
        best_prompt = current_prompt
        history = [{"iter": 0, "prompt": current_prompt, "score": initial_score}]
        no_improve = 0

        for i in range(self.max_iterations):
            request = (
                f"Current prompt:\n{current_prompt}\n\n"
                f"Score: {best_score:.3f}\n"
                f"Train examples: {train_examples[:3]}\n"
                f"Output an improved version (output ONLY the new prompt):"
            )
            try:
                result = await meta.run(request)
                new_prompt = result.content.strip()

                # Score on held-out eval set
                new_score = await self._score(new_prompt, eval_examples)
                history.append({"iter": i + 1, "prompt": new_prompt, "score": new_score})

                if new_score > best_score:
                    best_score = new_score
                    best_prompt = new_prompt
                    current_prompt = new_prompt
                    no_improve = 0
                    log.info(f"Iter {i + 1}: improved {best_score:.3f}")
                else:
                    no_improve += 1
                    log.info(f"Iter {i + 1}: no improvement ({new_score:.3f} vs {best_score:.3f})")
                    if no_improve >= self.patience:
                        log.info(f"Early stop after {self.patience} no-improvement iters")
                        break
            except Exception as e:
                log.error(f"Optimization iter {i + 1} failed: {e}")
                break

        return OptimizationResult(
            initial_prompt=initial_prompt,
            best_prompt=best_prompt,
            initial_score=initial_score,
            best_score=best_score,
            iterations=len(history) - 1,
            history=history,
        )

    async def _score(self, prompt: str, examples: list) -> float:
        try:
            import inspect

            if inspect.iscoroutinefunction(self.metric):
                return await self.metric(prompt, examples)
            return self.metric(prompt, examples)
        except Exception as e:
            log.error(f"Metric failed: {e}")
            return 0.0
