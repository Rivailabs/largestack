"""Largestack AI Template: Code Generation with testing."""
TEMPLATE_FILES = {
    "agent.py": '''import asyncio
from largestack import Agent, Workflow, tool
from largestack._security.code_sandbox import CodeSandbox

sandbox = CodeSandbox(backend="subprocess", timeout=30)

@tool
async def run_code(code: str) -> str:
    """Execute Python code in sandbox."""
    result = await sandbox.execute(code, language="python")
    return f"Exit: {result.exit_code}\\nOutput: {result.stdout}\\nErrors: {result.stderr}"

@tool
async def run_tests(test_code: str) -> str:
    """Run pytest on test code."""
    result = await sandbox.execute(f"import pytest; exec(\\"\\"\\"{test_code}\\"\\"\\")", language="python")
    return f"Tests: {result.stdout}" if result.success else f"FAILED: {result.stderr}"

planner = Agent(name="planner", instructions="Break the coding task into clear steps.", llm="openai/gpt-4o-mini")
coder = Agent(name="coder", instructions="Write clean Python code.", tools=[run_code], llm="openai/gpt-4o-mini")
tester = Agent(name="tester", instructions="Write comprehensive tests.", tools=[run_tests], llm="openai/gpt-4o-mini")
reviewer = Agent(name="reviewer", instructions="Review code quality.", llm="openai/gpt-4o-mini")

wf = Workflow("code-gen", mode="dag")
wf.add_node("plan", planner)
wf.add_node("code", coder, deps=["plan"])
wf.add_node("test", tester, deps=["code"])
wf.add_node("review", reviewer, deps=["code", "test"])

async def main():
    result = await wf.run({"task": "Write a function to find prime numbers up to N"})
    print(result.get("review_output", "No output"))

if __name__ == "__main__":
    asyncio.run(main())
''',
}
