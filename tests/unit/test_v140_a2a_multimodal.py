"""v0.14.0: Tests for A2A multi-modal message parts.

The actual API lives in ``largestack._a2a.multimodal``. Importing it
monkey-patches ``A2AMessage.from_parts``, ``A2AMessage.image``, and
``A2AMessage.file`` classmethods.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest


# -------------------- Part constructors --------------------

def test_text_part_shape():
    from largestack._a2a.multimodal import text_part
    p = text_part("hello")
    assert p == {"type": "text", "text": "hello"}


def test_image_part_with_inline_bytes():
    from largestack._a2a.multimodal import image_part
    raw = b"PNG-bytes"
    p = image_part(data=raw, media_type="image/png", alt_text="logo")
    assert p["type"] == "image"
    assert p["media_type"] == "image/png"
    assert p["alt_text"] == "logo"
    decoded = base64.b64decode(p["data"])
    assert decoded == raw


def test_image_part_from_path(tmp_path):
    from largestack._a2a.multimodal import image_part
    img = tmp_path / "x.png"
    img.write_bytes(b"PNG\x00\x01")
    p = image_part(path=img)
    assert p["type"] == "image"
    assert "image/png" in p["media_type"]
    assert base64.b64decode(p["data"]) == b"PNG\x00\x01"


def test_file_part_with_filename():
    from largestack._a2a.multimodal import file_part
    p = file_part(
        data=b"PDF-content",
        media_type="application/pdf",
        filename="contract.pdf",
    )
    assert p["filename"] == "contract.pdf"
    assert p["type"] == "file"


def test_data_part_carries_arbitrary_json():
    from largestack._a2a.multimodal import data_part
    p = data_part(data={"loan_id": "L001", "amount": 50000})
    assert p["type"] == "data"
    assert p["data"]["loan_id"] == "L001"


def test_uri_part():
    from largestack._a2a.multimodal import uri_part
    p = uri_part(
        uri="https://example.com/img.png",
        media_type="image/png", name="logo",
    )
    assert p["type"] == "uri"
    assert p["uri"] == "https://example.com/img.png"


# -------------------- A2AMessage classmethods (patched) --------------------

def test_from_parts_classmethod():
    from largestack._a2a.multimodal import text_part  # forces patch
    from largestack._a2a import A2AMessage
    msg = A2AMessage.from_parts("agent", text_part("done"))
    assert msg.role == "agent"
    assert msg.get_text() == "done"


def test_from_parts_requires_at_least_one():
    import largestack._a2a.multimodal  # noqa
    from largestack._a2a import A2AMessage
    with pytest.raises(ValueError, match="at least one"):
        A2AMessage.from_parts("user")


def test_image_classmethod_with_path(tmp_path):
    import largestack._a2a.multimodal  # noqa
    from largestack._a2a import A2AMessage
    img = tmp_path / "x.png"
    img.write_bytes(b"PNG")
    msg = A2AMessage.image("user", text="see this", image_path=img)
    assert len(msg.parts) == 2  # text + image


def test_file_classmethod_with_path(tmp_path):
    import largestack._a2a.multimodal  # noqa
    from largestack._a2a import A2AMessage
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"PDF")
    msg = A2AMessage.file(
        "user", text="here's the doc", file_path=f, media_type="application/pdf",
    )
    assert len(msg.parts) == 2


# -------------------- Accessors --------------------

def test_message_get_images_filters():
    from largestack._a2a.multimodal import (
        message_from_parts, text_part, image_part, message_get_images,
    )
    msg = message_from_parts(
        "user", text_part("hi"),
        image_part(data=b"img1", media_type="image/png"),
        image_part(data=b"img2", media_type="image/jpeg"),
    )
    images = message_get_images(msg)
    assert len(images) == 2


def test_message_get_files_filters():
    from largestack._a2a.multimodal import (
        message_from_parts, text_part, file_part, message_get_files,
    )
    msg = message_from_parts(
        "user", text_part("hi"),
        file_part(data=b"pdf", media_type="application/pdf"),
    )
    files = message_get_files(msg)
    assert len(files) == 1


def test_message_get_data_filters():
    from largestack._a2a.multimodal import (
        message_from_parts, data_part, message_get_data,
    )
    msg = message_from_parts(
        "agent",
        data_part(data={"x": 1}),
        data_part(data={"y": 2}),
    )
    data = message_get_data(msg)
    assert len(data) == 2


def test_part_get_bytes_roundtrip():
    from largestack._a2a.multimodal import image_part, part_get_bytes
    raw = b"raw bytes \x00\xff"
    part = image_part(data=raw, media_type="image/png")
    assert part_get_bytes(part) == raw


def test_part_get_bytes_rejects_text_part():
    from largestack._a2a.multimodal import text_part, part_get_bytes
    with pytest.raises(ValueError, match="image.*file"):
        part_get_bytes(text_part("hi"))
