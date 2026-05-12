# LARGESTACK_TOOL_PERM — Tool Permission Denied

**Error:** `ToolPermissionError`  
**Retryable:** No

**When:** An agent tried to use a tool that isn't in its `allow` list, or is in its `deny` list.

**Example:**
```
Agent 'researcher' cannot use tool 'shell_command'
  Suggestion: Add 'shell_command' to agent tool_permissions.allow list
```

**Solutions:**

1. **Add to allow list:**
   ```python
   Agent(tool_permissions={"allow": ["web_search", "calculator", "shell_command"]})
   ```
2. **Remove from deny list:**
   ```python
   Agent(tool_permissions={"deny": ["dangerous_tool"]})  # everything else allowed
   ```
3. **Use steering hooks instead** — more granular control:
   ```python
   @steer_before_tool
   def approve_writes(tool_name, params, ctx):
       if tool_name == "write_file" and "/etc" in params.get("path", ""):
           return interrupt("Cannot write to /etc")
       return proceed()
   ```
