from largestack._core.loop_guard import LoopGuard
from largestack.types import ToolCall


def test_max_turns():
    g = LoopGuard(max_turns=3)
    g.check_turn()
    g.check_turn()
    g.check_turn()
    try:
        g.check_turn()
        assert False
    except:
        pass


def test_loop_detect():
    g = LoopGuard()
    tc = [ToolCall(name="s", params={"q": "t"})]
    assert not g.check_loop(tc) and not g.check_loop(tc) and g.check_loop(tc)
