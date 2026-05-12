import json
import os

_script_cache = {}
_route_cache = {}
_publish_approved = False

def make_script(topic: str) -> dict:
    """Generate a script and storyboard for the given topic."""
    script = f"Script for {topic}: Engaging intro, main content, call to action."
    storyboard = [
        f"Scene 1: Hook about {topic}",
        f"Scene 2: Explain {topic} benefits",
        f"Scene 3: Demonstrate {topic} usage",
        f"Scene 4: Call to action for {topic}"
    ]
    result = {"script": script, "storyboard": storyboard}
    _script_cache[topic] = result
    return result

def route_model(platform: str) -> str:
    """Return a mock video format for the given platform."""
    mapping = {
        "instagram reel": "mock-video-fast",
        "youtube short": "mock-video-standard",
        "tiktok": "mock-video-fast"
    }
    result = mapping.get(platform, "mock-video-default")
    _route_cache[platform] = result
    return result

def publish_decision() -> dict:
    """Return a publish decision that never executes automatically."""
    return {"executed": False, "approved": _publish_approved}

def approve_publish():
    """Internal function to approve publish (not part of public API)."""
    global _publish_approved
    _publish_approved = True
