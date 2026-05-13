import ast
import re


def find_issues(source):
    issues = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return issues

    # Detect hardcoded secrets: assignment where value is a string literal and target name contains 'password' or 'secret'
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    name_lower = target.id.lower()
                    if 'password' in name_lower or 'secret' in name_lower:
                        issues.append('hardcoded_secret')
                        break

    # Detect SQL f-string formatting: f-strings that contain SQL keywords and have interpolations
    # We'll use regex to find f-strings with SQL keywords and at least one interpolation
    # Simple pattern: f"..." or f'...' containing SQL keywords like SELECT, INSERT, etc.
    # We'll also check for f-strings in AST
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # Check if the f-string contains SQL keywords
            # Reconstruct the f-string source
            fstring_source = ast.get_source_segment(source, node)
            if fstring_source and re.search(r'\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN)\b', fstring_source, re.IGNORECASE):
                # Check if there is at least one interpolation (ast.FormattedValue)
                for value in node.values:
                    if isinstance(value, ast.FormattedValue):
                        issues.append('sql_string_formatting')
                        break

    return issues


def suggest_patch(source):
    # Replace hardcoded secrets: PASSWORD = 'changeme' -> [GENERIC_API_KEY_REDACTED]
    # Replace SQL f-string interpolations with ? placeholders
    # We'll process line by line for simplicity
    lines = source.split('\n')
    new_lines = []
    for line in lines:
        # Check for hardcoded secret assignment
        # Pattern: variable = 'some_string' where variable contains password or secret
        match = re.match(r'^\s*(\w+)\s*=\s*\'([^\']*)\'\s*$', line)
        if match:
            var_name = match.group(1)
            if 'password' in var_name.lower() or 'secret' in var_name.lower():
                # Replace the value with APP_PASSWORD
                line = line.replace(match.group(0), f"{var_name} = APP_PASSWORD")
                new_lines.append(line)
                continue
        # Check for SQL f-string: f"..." or f'...' with interpolations
        # We'll use a more robust approach: find f-strings and replace interpolations
        # Simple regex to find f-strings
        fstring_pattern = r"(f\"[^\"]*\"|f\'[^\']*\')"
        def replace_interpolations(match):
            fstring = match.group(0)
            # Replace each {expression} with ?
            # But careful: nested braces? We'll assume simple cases
            # Use regex to find { } pairs
            result = re.sub(r'\{[^}]+\}', '?', fstring)
            return result
        line = re.sub(fstring_pattern, replace_interpolations, line)
        new_lines.append(line)
    return '\n'.join(new_lines)
