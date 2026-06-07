"""Largestack AI Template: Content Creation Factory."""

TEMPLATE_FILES = {
    "agent.py": """import asyncio
from largestack import Agent, Team, tool, HumanInTheLoop

hitl = HumanInTheLoop(backend="terminal")

researcher = Agent(name="researcher", instructions="Research the topic with 5 key facts.", llm="openai/gpt-4o-mini")
writer = Agent(name="writer", instructions="Write engaging blog post (500 words).", llm="openai/gpt-4o-mini")
editor = Agent(name="editor", instructions="Edit for clarity, grammar, and engagement.", llm="openai/gpt-4o-mini")
seo = Agent(name="seo", instructions="Add SEO title, meta description, keywords.", llm="openai/gpt-4o-mini")

team = Team(
    agents=[researcher, writer, editor, seo],
    strategy="sequential",
    cost_budget=1.00,
)

async def main():
    result = await team.run("Write about the future of AI agents in 2026")
    print(result.content)

if __name__ == "__main__":
    asyncio.run(main())
""",
}
