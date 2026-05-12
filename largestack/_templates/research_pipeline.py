"""Largestack AI Project Template: Research Pipeline (5 agents)

Usage: largestack init my-project --template research
"""
TEMPLATE_FILES = {
    "agent.py": '''import asyncio
from largestack import Agent, Team, tool, create_rag

@tool
async def web_search(query: str) -> str:
    """Search the web."""
    return f"Results for: {query}"

planner = Agent(name="planner", instructions="Break the research task into 3 subtasks.", llm="openai/gpt-4o-mini")
researcher = Agent(name="researcher", instructions="Research each subtask thoroughly.", tools=[web_search], llm="openai/gpt-4o-mini")
analyst = Agent(name="analyst", instructions="Analyze findings and identify key insights.", llm="openai/gpt-4o-mini")
writer = Agent(name="writer", instructions="Write a clear, structured report.", llm="openai/gpt-4o-mini")
reviewer = Agent(name="reviewer", instructions="Review for accuracy and completeness.", llm="openai/gpt-4o-mini")

team = Team(
    agents=[planner, researcher, analyst, writer, reviewer],
    strategy="sequential",
    cost_budget=2.00,
    on_error="skip",
    retries_per_agent=2,
)

async def main():
    result = await team.run("Analyze the current state of AI agent frameworks in 2026")
    print(f"Report ({result.turns} turns, ${result.total_cost:.4f}):")
    print(result.content)

if __name__ == "__main__":
    asyncio.run(main())
''',
    "largestack.yaml": '''default_llm: openai/gpt-4o-mini
cost_budget: 2.0
max_turns: 15
trace_enabled: true
guardrails_enabled: true
pii_detection: true
injection_detection: true
semantic_cache: true
''',
}
