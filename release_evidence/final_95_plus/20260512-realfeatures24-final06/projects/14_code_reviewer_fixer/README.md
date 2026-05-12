# code_reviewer_fixer

A Python project that provides offline security checks for hardcoded secrets and SQL injection risks in source code. It detects hardcoded ALL_CAPS string literals (potential secrets) and SQL built using f-strings, %-formatting, .format(), or string concatenation. The `suggest_patch` function replaces hardcoded values with `os.environ` lookups. Additionally, the project includes a Largestack smoke test demonstrating router orchestration and memory isolation features. All checks are offline and safe; no real secrets or network calls are used.
