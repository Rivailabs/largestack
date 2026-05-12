import ast
import os
import re


def find_issues(source: str) -> dict[str, list[int]]:
    """
    Detect hardcoded_secret and sql_string_formatting issues in the given source code.
    Returns a dict with issue types as keys and list of line numbers as values.
    """
    issues: dict[str, list[int]] = {}
    tree = ast.parse(source)

    # Detect hardcoded_secret: ALL_CAPS variable assigned a quoted literal
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) > 1:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        issues.setdefault('hardcoded_secret', []).append(node.lineno)

    # Detect sql_string_formatting: SQL built with f-strings, %-formatting, .format(), or string concatenation
    for node in ast.walk(tree):
        # f-string detection: any ast.JoinedStr node
        if isinstance(node, ast.JoinedStr):
            issues.setdefault('sql_string_formatting', []).append(node.lineno)
        # %-formatting: ast.BinOp with left being a string constant containing '%' and op Mod
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str) and '%' in node.left.value:
                issues.setdefault('sql_string_formatting', []).append(node.lineno)
        # .format() method call on a string constant
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'format' and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
                issues.setdefault('sql_string_formatting', []).append(node.lineno)
        # string concatenation: ast.BinOp with Add and at least one operand being a string constant containing SQL keywords
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            for operand in [node.left, node.right]:
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and 'select' in operand.value.lower():
                    issues.setdefault('sql_string_formatting', []).append(node.lineno)
                    break

    return issues


def suggest_patch(source: str) -> str:
    """
    Replace hardcoded ALL_CAPS string literals with os.environ lookups.
    Returns the patched source code.
    """
    tree = ast.parse(source)
    replacements = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and len(target.id) > 1:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        var_name = target.id
                        replacements.append((node.lineno, var_name))
    if not replacements:
        return source
    lines = source.split('\n')
    # Add import os if not present
    has_import_os = any(line.strip().startswith('import os') for line in lines)
    if not has_import_os:
        lines.insert(0, 'import os')
    # Replace each assignment line
    for lineno, var_name in replacements:
        idx = lineno - 1
        # Adjust index if we inserted import os
        if not has_import_os:
            idx += 1
        # Replace the entire line with os.environ lookup
        lines[idx] = f'{var_name} = os.environ.get("{var_name}", "placeholder")'
    return '\n'.join(lines)
