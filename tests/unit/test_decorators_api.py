"""Tests for PydanticAI-style decorator API."""
import sys, asyncio; sys.path.insert(0, ".")
from dataclasses import dataclass

def test_typed_agent_creates():
    from largestack.decorators import Agent, RunContext
    @dataclass
    class Deps:
        user_id: str
    a = Agent[Deps, str]('openai/gpt-4o-mini', deps_type=Deps, instructions="test")
    assert a.model == 'openai/gpt-4o-mini'
    assert a.deps_type is Deps

def test_tool_decorator_with_ctx():
    from largestack.decorators import Agent, RunContext
    @dataclass
    class Deps:
        x: int = 1
    a = Agent[Deps, str]('test/model', deps_type=Deps)
    
    @a.tool
    async def my_tool(ctx: RunContext[Deps], q: str) -> str:
        return q
    
    assert 'my_tool' in a.tools
    assert a.tools['my_tool'].takes_ctx is True

def test_tool_plain_no_ctx():
    from largestack.decorators import Agent
    a = Agent('test/model')
    
    @a.tool_plain
    def add(x: int, y: int) -> int:
        """Add."""
        return x + y
    
    assert 'add' in a.tools
    assert a.tools['add'].takes_ctx is False

def test_tool_schema_extraction():
    from largestack.decorators import Agent
    a = Agent('test/model')
    
    @a.tool_plain
    def calc(x: int, y: float, name: str = "test") -> str:
        """Calculate."""
        return ""
    
    schema = a.tools['calc'].parameters_schema
    assert schema['type'] == 'object'
    assert schema['properties']['x']['type'] == 'integer'
    assert schema['properties']['y']['type'] == 'number'
    assert schema['properties']['name']['type'] == 'string'
    assert 'x' in schema['required']
    assert 'name' not in schema['required']  # has default

def test_output_validator_registers():
    from largestack.decorators import Agent, ModelRetry, RunContext
    a = Agent('test/model')
    
    @a.output_validator
    def check(ctx, output):
        if 'bad' in output:
            raise ModelRetry('clean it up')
        return output
    
    assert len(a._output_validators) == 1

def test_model_retry_exception():
    from largestack.decorators import ModelRetry
    e = ModelRetry("hint here")
    assert e.hint == "hint here"
    assert str(e) == "hint here"

def test_run_context_dataclass():
    from largestack.decorators import RunContext
    @dataclass
    class Deps:
        x: int = 5
    ctx = RunContext(deps=Deps())
    assert ctx.deps.x == 5
    assert ctx.retry_count == 0
    ctx.increment_retry()
    assert ctx.retry_count == 1
    ctx.add_usage(input_tokens=100, cost=0.01)
    assert ctx.usage['input_tokens'] == 100
    assert ctx.usage['cost'] == 0.01
