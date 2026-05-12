"""Decorator API overhead benchmark."""
import sys, time
sys.path.insert(0, ".")
from largestack.decorators import Agent, RunContext

def bench():
    t0 = time.perf_counter()
    for _ in range(1000):
        agent = Agent("test/mock", instructions="x")
        @agent.tool_plain
        def tool(x: int) -> int:
            """Test."""
            return x
    elapsed = time.perf_counter() - t0
    print(f"1000 agents created: {elapsed*1000:.1f}ms ({elapsed:.3f}us/agent)")

if __name__ == "__main__":
    bench()
