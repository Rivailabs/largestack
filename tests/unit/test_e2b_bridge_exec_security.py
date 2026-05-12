import ast

import pytest

from largestack._security.e2b_bridge import _validate_local_exec_ast


def _validate(code: str):
    tree = ast.parse(code, mode="exec")
    _validate_local_exec_ast(tree)


def test_local_exec_ast_allows_basic_print():
    _validate("print(1 + 2)")


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from os import system",
        "open('/etc/passwd').read()",
        "eval('1+1')",
        "exec('print(1)')",
        "compile('1+1', '<x>', 'eval')",
        "print((1).__class__)",
    ],
)
def test_local_exec_ast_blocks_unsafe_constructs(code):
    with pytest.raises(ValueError):
        _validate(code)
