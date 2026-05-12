"""Agent with tools using the configured provider."""
from pathlib import Path
import ast
import operator
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent, tool

_ALLOWED = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_expr(node):
    if isinstance(node, ast.Expression):
        return _eval_expr(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval_expr(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval_expr(node.left), _eval_expr(node.right))
    raise ValueError("Only numeric arithmetic expressions are allowed")


@tool
async def calculate(expression: str) -> str:
    """Evaluate a safe numeric arithmetic expression."""
    try:
        return str(_eval_expr(ast.parse(expression, mode="eval")))
    except Exception as exc:
        return f"Error: {exc}"


@tool
async def get_weather(city: str) -> str:
    """Get simulated weather for a city."""
    return f"Weather in {city}: 72F Sunny (simulated)"


async def main():
    agent = Agent(name="assistant", instructions="Use tools when useful. Return the final answer clearly.", tools=[calculate, get_weather], llm=select_model(), guardrails=False, cost_budget=0.10, max_turns=5)
    try:
        result = await agent.run("What is 42 * 17? Use the calculate tool.", timeout=90)
        print(f"Agent: {result.content}\nTools: {result.tool_calls_made}")
    finally:
        await close_quietly(agent)


if __name__ == "__main__":
    main_or_skip(main)
