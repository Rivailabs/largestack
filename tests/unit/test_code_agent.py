"""Code-mode agent tests."""
import sys; sys.path.insert(0, ".")

def test_extract_code():
    from largestack._core.code_agent import CodeAgent
    a = CodeAgent()
    code = a.extract_code("Here:\n```python\nprint(1)\n```\nDone")
    assert code == "print(1)"

def test_is_final():
    from largestack._core.code_agent import CodeAgent
    a = CodeAgent()
    assert a.is_final("final_answer('done')")
    assert not a.is_final("print(1)")

def test_extract_final_answer():
    from largestack._core.code_agent import CodeAgent
    a = CodeAgent()
    ans = a.extract_final_answer('final_answer("hello")', "")
    assert ans == "hello"
