# LARGESTACK_TOOL — Tool Errors

## LARGESTACK_TOOL_ERROR
Tool function raised an exception. Check tool implementation and input parameters.

## LARGESTACK_TOOL_PERM
Agent doesn't have permission for this tool. Add to allow list:
```python
Agent(tool_permissions={"allow": ["web_search", "calculator"]})
```
