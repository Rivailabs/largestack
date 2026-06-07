"""Calculator tool — safe AST-based math evaluation."""

from __future__ import annotations

import ast
import math
import operator as op
from typing import Any

from largestack._core.tools import tool


SAFE_NAMES: dict[str, Any] = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
SAFE_NAMES.update(
    {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
    }
)

_ALLOWED_BINARY_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}

_ALLOWED_UNARY_OPS = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}

_MAX_EXPRESSION_LENGTH = 500
_MAX_POWER_ABS = 1000


class SafeMathError(ValueError):
    """Raised when an unsafe or unsupported math expression is provided."""


def _safe_eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise SafeMathError("Only numeric constants are allowed")

    if isinstance(node, ast.Name):
        if node.id in SAFE_NAMES:
            return SAFE_NAMES[node.id]
        raise SafeMathError(f"Unknown name: {node.id}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPS:
            raise SafeMathError(f"Unsupported operator: {op_type.__name__}")

        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)

        if op_type is ast.Pow and abs(float(right)) > _MAX_POWER_ABS:
            raise SafeMathError("Exponent too large")

        return _ALLOWED_BINARY_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPS:
            raise SafeMathError(f"Unsupported unary operator: {op_type.__name__}")
        return _ALLOWED_UNARY_OPS[op_type](_safe_eval_node(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise SafeMathError("Only direct safe function calls are allowed")

        func = SAFE_NAMES.get(node.func.id)
        if func is None or not callable(func):
            raise SafeMathError(f"Function not allowed: {node.func.id}")

        if node.keywords:
            raise SafeMathError("Keyword arguments are not supported")

        args = [_safe_eval_node(arg) for arg in node.args]
        return func(*args)

    if isinstance(node, ast.List):
        return [_safe_eval_node(item) for item in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(item) for item in node.elts)

    raise SafeMathError(f"Unsupported expression: {type(node).__name__}")


def _safe_math_eval(expression: str) -> Any:
    expression = expression.strip()

    if not expression:
        raise SafeMathError("Empty expression")

    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise SafeMathError("Expression too long")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise SafeMathError("Invalid math expression") from exc

    return _safe_eval_node(tree)


@tool
async def calculator(expression: str) -> str:
    """Evaluate a math expression safely. Supports +,-,*,/,//,%,**,sqrt,sin,cos,log,pi,e."""
    try:
        return str(_safe_math_eval(expression))
    except Exception as e:
        return f"Math error: {e}"
