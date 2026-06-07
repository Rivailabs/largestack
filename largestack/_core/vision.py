"""Vision support — send images to multimodal LLMs.

result = await agent.run("Describe this image", images=["photo.png"])
result = await agent.run("Compare", images=["a.png", "b.png"])
result = await agent.run("Analyze", images=["https://example.com/chart.png"])
"""

from __future__ import annotations
import base64, os, httpx
from typing import Any


def build_vision_messages(task: str, images: list[str], instructions: str = None) -> list[dict]:
    """Build messages with image content for multimodal LLMs."""
    messages = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    content_parts: list[dict] = [{"type": "text", "text": task}]

    for img in images:
        if img.startswith("http://") or img.startswith("https://"):
            content_parts.append({"type": "image_url", "image_url": {"url": img}})
        elif os.path.exists(img):
            mime = _detect_mime(img)
            with open(img, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content_parts.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
            )
        elif img.startswith("data:"):
            content_parts.append({"type": "image_url", "image_url": {"url": img}})

    messages.append({"role": "user", "content": content_parts})
    return messages


def _detect_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")
