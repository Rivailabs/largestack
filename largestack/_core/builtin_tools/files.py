"""File I/O tools with path restrictions."""
from largestack._core.tools import tool
import os


def _get_allowed_base() -> str:
    """Lazy: get base dir at call time, not import time."""
    return os.environ.get("LARGESTACK_ALLOWED_BASE", os.getcwd())


def _check_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    base = os.path.abspath(_get_allowed_base())
    # Use commonpath for proper containment check (not startswith — vulnerable)
    try:
        if os.path.commonpath([abs_path, base]) != base:
            raise PermissionError(f"Access denied: {path} outside allowed directory")
    except ValueError:
        # Different drives on Windows
        raise PermissionError(f"Access denied: {path} outside allowed directory")
    return abs_path

@tool
async def read_file(path: str) -> str:
    """Read contents of a file."""
    p = _check_path(path)
    with open(p) as f: return f.read()

@tool
async def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    p = _check_path(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f: f.write(content)
    return f"Written {len(content)} chars to {path}"
