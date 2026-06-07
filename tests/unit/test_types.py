from largestack.types import AgentResult, ToolCall, LLMResponse, CostEstimate


def test_tool_call():
    tc = ToolCall(name="search", params={"q": "test"})
    assert tc.name == "search" and tc.id


def test_llm_response():
    r = LLMResponse(content="Hello", model="gpt-4o", input_tokens=10, output_tokens=5)
    assert r.content == "Hello" and r.cost == 0.0


def test_agent_result():
    r = AgentResult(content="Done", agent_name="test", total_cost=0.01)
    assert r.status == "completed"


def test_cost_estimate():
    e = CostEstimate(low=0.01, expected=0.05, high=0.10, model="gpt-4o")
    assert e.low < e.expected < e.high
