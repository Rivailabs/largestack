"""Entry point for simple LARGESTACK agent."""
import asyncio
from largestack._core.yaml_agent import load_agent


async def main():
    agent = load_agent("agent.yaml")
    result = await agent.run("Hello!")
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
