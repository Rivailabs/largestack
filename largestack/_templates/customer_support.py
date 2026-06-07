"""Largestack AI Template: Customer Support Bot with routing."""

TEMPLATE_FILES = {
    "agent.py": '''import asyncio
from largestack import Agent, tool, SessionStore

@tool
async def lookup_order(order_id: str) -> str:
    """Look up order status."""
    return f"Order {order_id}: Shipped, arriving tomorrow."

@tool
async def check_account(email: str) -> str:
    """Check customer account."""
    return f"Account {email}: Active, Premium tier."

router = Agent(name="router", instructions="""You are a customer support router.
Classify the query: technical, billing, or general.
Route to the appropriate specialist.""", llm="openai/gpt-4o-mini")

tech_support = Agent(name="tech-support", instructions="You handle technical issues.", llm="openai/gpt-4o-mini")
billing = Agent(name="billing", instructions="You handle billing questions.", tools=[lookup_order, check_account], llm="openai/gpt-4o-mini")
general = Agent(name="general", instructions="You handle general inquiries.", llm="openai/gpt-4o-mini")

session = SessionStore("sqlite")

async def main():
    result = await session.chat(billing, "What is the status of order #12345?", session_id="customer-1")
    print(result.content)

if __name__ == "__main__":
    asyncio.run(main())
''',
}
