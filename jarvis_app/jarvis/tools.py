"""Jarvis tools — real, working actions the agent can call.

Each tool is an async function decorated with Largestack's @tool. The agent
decides when to call them; Largestack handles the schema + execution.

Safety model: read/append actions run for real. Anything destructive or
outbound (delete, move, send, pay, publish, deploy) is NOT performed here — it
is routed through `request_approval`, which PERSISTS the request to an approval
queue (status 'pending') and returns a 'waiting for human approval' message.
File listing is confined to the configured workspace; the calculator is bounded.
"""

from __future__ import annotations

import ast
import operator
from pathlib import Path

from largestack import tool

from . import memory_store
from .config import KNOWLEDGE_DIR, WORKSPACE_ROOT

# ---- Safe, bounded calculator ----------------------------------------------
# Bounds prevent resource-exhaustion abuse: e.g. "9**9**9" would otherwise block
# the event loop computing an astronomically large integer.

_MAX_EXPR_LEN = 120
_MAX_DEPTH = 25
_MAX_MAGNITUDE = 10**12  # reject operands/results larger than this
_MAX_POW_EXP = 100  # reject exponents larger than this BEFORE computing


def _guarded_pow(base, exp):
    if abs(exp) > _MAX_POW_EXP or abs(base) > _MAX_MAGNITUDE:
        raise ValueError("number too large")
    return operator.pow(base, exp)


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _guarded_pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _eval(node, depth: int = 0):
    if depth > _MAX_DEPTH:
        raise ValueError("expression too deeply nested")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if abs(node.value) > _MAX_MAGNITUDE:
            raise ValueError("number too large")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left, depth + 1), _eval(node.right, depth + 1))
    raise ValueError("only basic arithmetic is allowed")


@tool
async def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '23 * 19 + 7' (bounded for safety)."""
    if len(expression) > _MAX_EXPR_LEN:
        return "Error: expression too long"
    try:
        result = _eval(ast.parse(expression, mode="eval"))
    except Exception as exc:  # noqa: BLE001 - tool returns the error as text
        return f"Error: {exc}"
    if isinstance(result, (int, float)) and abs(result) > _MAX_MAGNITUDE:
        return "Error: result too large"
    return str(result)


# ---- Persistent notes ------------------------------------------------------


@tool
async def take_note(text: str) -> str:
    """Save a note to the user's persistent notebook."""
    n = memory_store.add_note(text)
    return f"Saved as note #{n}."


@tool
async def list_notes() -> str:
    """List all of the user's saved notes."""
    notes = memory_store.get_notes()
    if not notes:
        return "No notes yet."
    return "\n".join(f"{i}. {n['text']}  ({n['at']})" for i, n in enumerate(notes, 1))


# ---- Persistent key/value memory ------------------------------------------


@tool
async def remember_fact(key: str, value: str) -> str:
    """Remember a fact under a short key, e.g. key='project deadline', value='June 20'."""
    memory_store.set_fact(key, value)
    return f"Got it — I'll remember that {key} is {value}."


@tool
async def recall_fact(key: str) -> str:
    """Recall a previously remembered fact by its key."""
    val = memory_store.get_fact(key)
    return val if val is not None else f"I don't have anything remembered for '{key}'."


# ---- Read-only file listing ------------------------------------------------


@tool
async def list_directory(path: str = ".") -> str:
    """List file/folder names inside the Jarvis workspace (read-only, confined)."""
    try:
        root = WORKSPACE_ROOT
        target = Path(path)
        target = (target if target.is_absolute() else root / target).resolve()
        if target != root and root not in target.parents:
            return f"Error: '{path}' is outside the Jarvis workspace ({root})."
        if not target.is_dir():
            return f"Not a directory: {path}"
        entries = sorted(e.name + ("/" if e.is_dir() else "") for e in target.iterdir())
        return "\n".join(entries[:50]) if entries else "(empty)"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---- Simple local-document Q&A (keyword RAG) -------------------------------


@tool
async def search_knowledge(query: str) -> str:
    """Search Jarvis's local knowledge documents and return the best matching snippet."""
    words = {w.lower() for w in query.split() if len(w) > 2}
    best, best_score, best_src = "", 0, ""
    if KNOWLEDGE_DIR.is_dir():
        for doc in KNOWLEDGE_DIR.glob("*.md"):
            text = doc.read_text(errors="ignore")
            score = sum(text.lower().count(w) for w in words)
            if score > best_score:
                best, best_score, best_src = text, score, doc.name
    if not best_score:
        return "INSUFFICIENT_EVIDENCE: nothing relevant found in local knowledge."
    return f"[source: {best_src}]\n{best[:800]}"


# ---- Human-approval gate for risky actions ---------------------------------


@tool
async def request_approval(action: str, details: str = "") -> str:
    """Request human approval for a risky/irreversible action (delete, move, send,
    pay, publish, deploy). NEVER performs the action — it persists the request to
    the approval queue with status 'pending' so a human can review it."""
    req_id = memory_store.add_approval(action, details)
    return (
        f"⏸ APPROVAL REQUIRED — recorded as pending request #{req_id}, not executed.\n"
        f"Action: {action}\nDetails: {details}\n"
        f"Review the queue at {memory_store.APPROVALS_FILE} before it can run."
    )


ALL_TOOLS = [
    calculate,
    take_note,
    list_notes,
    remember_fact,
    recall_fact,
    list_directory,
    search_knowledge,
    request_approval,
]
