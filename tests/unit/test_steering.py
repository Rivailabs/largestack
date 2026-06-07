import asyncio
from largestack._core.steering import SteeringEngine, steer_before_tool, proceed, interrupt
from largestack.types import SteeringAction


@steer_before_tool
def block_delete(tool_name, params, ctx):
    return interrupt("No delete") if tool_name == "delete" else proceed()


def test_block():
    e = SteeringEngine([block_delete])
    r = asyncio.run(e.run_before("delete", {}, {}))
    assert r.action == SteeringAction.INTERRUPT


def test_allow():
    e = SteeringEngine([block_delete])
    r = asyncio.run(e.run_before("search", {}, {}))
    assert r.action == SteeringAction.PROCEED
