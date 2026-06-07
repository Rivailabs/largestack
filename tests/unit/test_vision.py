"""Tests for vision/image support."""

import sys, os, tempfile

sys.path.insert(0, ".")
from largestack._core.vision import build_vision_messages


def test_vision_url():
    msgs = build_vision_messages("Describe", ["https://example.com/img.png"])
    content = msgs[-1]["content"]
    assert len(content) == 2
    assert content[0]["type"] == "text" and content[0]["text"] == "Describe"
    assert content[1]["type"] == "image_url"


def test_vision_file():
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(b"\x89PNG\r\n")
    tmp.close()
    msgs = build_vision_messages("Analyze", [tmp.name])
    assert msgs[-1]["content"][1]["type"] == "image_url"
    assert "base64" in msgs[-1]["content"][1]["image_url"]["url"]
    os.unlink(tmp.name)


def test_vision_with_instructions():
    msgs = build_vision_messages("Describe", ["https://x.com/a.png"], instructions="Be concise")
    assert msgs[0]["role"] == "system" and "concise" in msgs[0]["content"]


def test_vision_multiple_images():
    msgs = build_vision_messages("Compare", ["https://a.com/1.png", "https://b.com/2.png"])
    content = msgs[-1]["content"]
    assert len(content) == 3  # text + 2 images
