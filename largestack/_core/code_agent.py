"""Code-mode agent — writes Python instead of JSON tool calls.

Inspired by smolagents CodeAgent. Claims 30% fewer LLM steps on GAIA.

Usage:
    from largestack._core.code_agent import CodeAgent
    
    agent = CodeAgent(llm="openai/gpt-4o", sandbox="e2b")
    result = await agent.run("Calculate fibonacci(20) and plot it")
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("largestack.code_agent")


@dataclass
class CodeStep:
    code: str
    output: str = ""
    error: str | None = None


class CodeAgent:
    """Agent that solves tasks by writing executable Python code.
    
    The LLM outputs Python code in ```python``` blocks. The agent extracts,
    sandboxes, and executes them, feeding output back to the LLM.
    """
    
    SYSTEM_PROMPT = """You solve tasks by writing Python code.

Format every action as:
```python
# your code here
```

Available tools are imported as Python functions. After each code block,
you'll see the output. Continue until the task is solved, then write:
final_answer("your answer")
"""
    
    def __init__(self, llm: str = "openai/gpt-4o-mini", sandbox: str = "local",
                 max_steps: int = 10):
        self.llm = llm
        self.sandbox_type = sandbox
        self.max_steps = max_steps
        self._sandbox = None
        self._gateway = None
    
    def _get_gateway(self):
        if self._gateway is None:
            from largestack._core.gateway import LLMGateway
            self._gateway = LLMGateway()
        return self._gateway
    
    async def _get_sandbox(self):
        if self._sandbox is None:
            from largestack._core.e2b_sandbox import E2BSandbox
            self._sandbox = E2BSandbox()
        return self._sandbox
    
    def extract_code(self, text: str) -> str | None:
        """Extract Python from ```python``` block."""
        m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        return m.group(1).strip() if m else None
    
    def is_final(self, code: str) -> bool:
        return "final_answer(" in code
    
    def extract_final_answer(self, code: str, output: str):
        """Extract final_answer arg. Handles strings, dicts, nested calls via paren counting."""
        idx = code.find("final_answer(")
        if idx < 0:
            return output
        start = idx + len("final_answer(")
        depth = 1
        i = start
        while i < len(code) and depth > 0:
            ch = code[i]
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            i += 1
        if depth != 0:
            raise ValueError(f"Unmatched parens in final_answer call: {code[idx:idx+80]}")
        arg = code[start:i-1].strip()
        # Try eval as Python literal (handles dicts, lists, numbers)
        try:
            import ast
            return ast.literal_eval(arg)
        except Exception:
            pass
        # Strip outer quotes if string literal
        if len(arg) >= 2 and arg[0] in ("'", '"') and arg[-1] == arg[0]:
            return arg[1:-1]
        return arg
    
    async def run(self, task: str) -> str:
        """Solve task by code generation + execution loop.
        
        Passes proper message history to gateway preserving role boundaries.
        """
        gateway = self._get_gateway()
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        steps: list[CodeStep] = []
        sandbox = await self._get_sandbox()
        self._trace = steps
        
        for step_n in range(self.max_steps):
            # Pass full message history (with roles intact) to gateway
            try:
                resp = await gateway.chat(model=self.llm, messages=messages,
                                            temperature=0.2)
                response = resp.content
            except Exception as e:
                return f"LLM call failed: {e}"
            
            code = self.extract_code(response)
            if not code:
                return response
            
            # Execute in sandbox
            exec_result = await sandbox.run_python(code)
            steps.append(CodeStep(code=code, output=exec_result.stdout,
                                  error=exec_result.error))
            
            if self.is_final(code):
                return self.extract_final_answer(code, exec_result.stdout)
            
            # Feed output back
            messages.append({"role": "assistant", "content": response})
            output_msg = exec_result.stdout
            if exec_result.error:
                output_msg += f"\nError: {exec_result.error}"
            messages.append({"role": "user", "content": f"Output:\n{output_msg}"})
        
        return f"Max steps reached. Last output: {steps[-1].output if steps else 'none'}"
    
    @property
    def trace(self) -> list[CodeStep]:
        return getattr(self, '_trace', [])
