"""Largestack AI Template: Data Analysis Pipeline."""

TEMPLATE_FILES = {
    "agent.py": '''import asyncio
from largestack import Agent, Team, tool
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    key_findings: list[str]
    recommendations: list[str]
    confidence: float

@tool
async def query_database(sql: str) -> str:
    """Execute SQL query."""
    return f"Query result: 5 rows returned for: {sql}"

validator = Agent(name="validator", instructions="Validate the data quality.", llm="openai/gpt-4o-mini")
analyst = Agent(name="analyst", instructions="Analyze patterns in the data.", tools=[query_database], llm="openai/gpt-4o-mini")
reporter = Agent(name="reporter", instructions="Create executive summary.", llm="openai/gpt-4o-mini")

team = Team(agents=[validator, analyst, reporter], cost_budget=1.00)

async def main():
    result = await reporter.run("Analyze Q1 sales data", response_model=AnalysisResult)
    print(f"Summary: {result.summary}")
    print(f"Findings: {result.key_findings}")

if __name__ == "__main__":
    asyncio.run(main())
''',
}
