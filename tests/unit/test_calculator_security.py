import pytest

from largestack._core.builtin_tools.calc import _safe_math_eval


def test_safe_math_basic_arithmetic():
    assert _safe_math_eval("2 + 3 * 4") == 14


def test_safe_math_functions_and_constants():
    assert _safe_math_eval("round(sqrt(16) + pi, 2)") == 7.14


def test_safe_math_rejects_attribute_access():
    with pytest.raises(ValueError):
        _safe_math_eval("__import__('os').system('echo hacked')")


def test_safe_math_rejects_non_numeric_constants():
    with pytest.raises(ValueError):
        _safe_math_eval("'hello'")


def test_safe_math_rejects_large_exponent():
    with pytest.raises(ValueError):
        _safe_math_eval("2 ** 100000")
