"""Tool access control — OWASP ASI02 (Tool/Function Misuse).

Validates tool parameters, enforces rate limits, and restricts tool access per agent.

    policy = ToolAccessPolicy()
    policy.allow("researcher", ["web_search", "read_file"])
    policy.deny("researcher", ["shell_command", "write_file"])
    policy.rate_limit("web_search", max_calls=10, window_seconds=60)
    policy.validate_params("shell_command", {"command": r"^ls|cat|head|tail"})
"""
from __future__ import annotations
import re, time, logging
from typing import Any

log = logging.getLogger("largestack.tool_access")

class ToolAccessPolicy:
    def __init__(self):
        self._allow: dict[str, set[str]] = {}  # agent → allowed tools
        self._deny: dict[str, set[str]] = {}   # agent → denied tools
        self._rate: dict[str, dict] = {}        # tool → {max, window, calls:[]}
        self._param_rules: dict[str, dict[str, str]] = {}  # tool → {param: regex}
        self._output_caps: dict[str, int] = {}  # tool → max output chars

    def allow(self, agent_name: str, tools: list[str]):
        self._allow.setdefault(agent_name, set()).update(tools)

    def deny(self, agent_name: str, tools: list[str]):
        self._deny.setdefault(agent_name, set()).update(tools)

    def rate_limit(self, tool_name: str, max_calls: int = 10, window_seconds: float = 60):
        self._rate[tool_name] = {"max": max_calls, "window": window_seconds, "calls": []}

    def validate_params(self, tool_name: str, rules: dict[str, str]):
        """Set regex validation rules for tool parameters."""
        self._param_rules[tool_name] = rules

    def cap_output(self, tool_name: str, max_chars: int = 10000):
        self._output_caps[tool_name] = max_chars

    def check_access(self, agent_name: str, tool_name: str) -> bool:
        if agent_name in self._deny and tool_name in self._deny[agent_name]:
            log.warning(f"Tool access DENIED: {agent_name} → {tool_name}")
            return False
        if agent_name in self._allow and tool_name not in self._allow[agent_name]:
            log.warning(f"Tool access DENIED (not in allowlist): {agent_name} → {tool_name}")
            return False
        return True

    def check_rate(self, tool_name: str) -> bool:
        if tool_name not in self._rate: return True
        r = self._rate[tool_name]
        now = time.time()
        r["calls"] = [t for t in r["calls"] if now - t < r["window"]]
        if len(r["calls"]) >= r["max"]:
            log.warning(f"Tool rate limit: {tool_name} ({len(r['calls'])}/{r['max']} in {r['window']}s)")
            return False
        r["calls"].append(now)
        return True

    def check_params(self, tool_name: str, params: dict) -> tuple[bool, str]:
        if tool_name not in self._param_rules: return True, ""
        for param, pattern in self._param_rules[tool_name].items():
            val = str(params.get(param, ""))
            # v1.1.1: fullmatch, not match — re.match anchors only the START, so a
            # rule like "^(ls|cat)" accepted "ls; rm -rf ~". fullmatch requires the
            # WHOLE value to match. (Callers must still treat tool args as untrusted
            # and never pass them straight to a shell.)
            if not re.fullmatch(pattern, val, re.DOTALL):
                msg = f"Parameter validation failed: {tool_name}.{param}='{val}' doesn't match '{pattern}'"
                log.warning(msg)
                return False, msg
        return True, ""

    def truncate_output(self, tool_name: str, output: str) -> str:
        cap = self._output_caps.get(tool_name, 50000)
        if len(output) > cap:
            log.info(f"Tool output truncated: {tool_name} ({len(output)} → {cap} chars)")
            return output[:cap] + f"\n[TRUNCATED: {len(output) - cap} chars removed]"
        return output

    async def enforce(self, agent_name: str, tool_name: str, params: dict) -> tuple[bool, str]:
        """Full enforcement: access + rate + params."""
        if not self.check_access(agent_name, tool_name):
            return False, f"Access denied: {agent_name} cannot use {tool_name}"
        if not self.check_rate(tool_name):
            return False, f"Rate limit exceeded for {tool_name}"
        ok, msg = self.check_params(tool_name, params)
        if not ok: return False, msg
        return True, ""
