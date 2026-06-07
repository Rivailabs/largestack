"""Time and date tool."""

from largestack._core.tools import tool


@tool
async def get_current_time(timezone: str = "UTC") -> str:
    """Get current date and time."""
    from datetime import datetime, timezone as tz

    now = datetime.now(tz.utc)
    return f"Current time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')} | Unix: {int(now.timestamp())}"
