"""A2A multi-modal message parts (v0.14.0).

Closes Tier A #21 (audit Step 21: multi-modal task content). Extends
``A2AMessage`` with helpers for image / file / data parts per the A2A
spec ``parts[]`` schema.

A2A message parts shape::

    {"type": "text", "text": "..."}
    {"type": "image", "media_type": "image/png",
     "data": "<base64>", "alt_text": "..."}
    {"type": "file", "media_type": "application/pdf",
     "data": "<base64>", "filename": "..."}
    {"type": "data", "data": {...arbitrary JSON...}, "schema": "..."}
    {"type": "uri", "uri": "https://...",
     "media_type": "image/jpeg", "name": "..."}

These helpers DO NOT modify the existing ``A2AMessage.text()`` API —
they're additive constructors plus accessor helpers.
"""

from __future__ import annotations
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Literal

from largestack._a2a import A2AMessage

log = logging.getLogger("largestack.a2a.multimodal")


PartType = Literal["text", "image", "file", "data", "uri"]


# -------------------- Constructors --------------------


def text_part(text: str) -> dict[str, Any]:
    """Build a text part."""
    return {"type": "text", "text": text}


def image_part(
    *,
    data: bytes | str | None = None,
    path: str | Path | None = None,
    media_type: str = "",
    alt_text: str = "",
) -> dict[str, Any]:
    """Build an image part. Provide either ``data`` (bytes/base64) or
    ``path`` (file on disk).
    """
    encoded, mt = _resolve_binary(data, path, media_type, default="image/png")
    return {
        "type": "image",
        "media_type": mt,
        "data": encoded,
        "alt_text": alt_text,
    }


def file_part(
    *,
    data: bytes | str | None = None,
    path: str | Path | None = None,
    media_type: str = "",
    filename: str = "",
) -> dict[str, Any]:
    """Build a file part."""
    encoded, mt = _resolve_binary(
        data,
        path,
        media_type,
        default="application/octet-stream",
    )
    if not filename and path is not None:
        filename = Path(path).name
    return {
        "type": "file",
        "media_type": mt,
        "data": encoded,
        "filename": filename,
    }


def data_part(
    data: dict[str, Any],
    *,
    schema: str = "",
) -> dict[str, Any]:
    """Build a structured-data part (arbitrary JSON)."""
    if not isinstance(data, dict):
        raise ValueError("data must be a dict")
    part: dict[str, Any] = {"type": "data", "data": data}
    if schema:
        part["schema"] = schema
    return part


def uri_part(
    uri: str,
    *,
    media_type: str = "",
    name: str = "",
) -> dict[str, Any]:
    """Build a URI reference part — for very large files."""
    if not uri:
        raise ValueError("uri is required")
    if not uri.startswith(("http://", "https://", "s3://", "gs://", "azure://")):
        raise ValueError(f"uri must use http/https/s3/gs/azure scheme: {uri}")
    part: dict[str, Any] = {"type": "uri", "uri": uri}
    if media_type:
        part["media_type"] = media_type
    if name:
        part["name"] = name
    return part


def _resolve_binary(
    data: bytes | str | None,
    path: str | Path | None,
    media_type: str,
    *,
    default: str,
) -> tuple[str, str]:
    """Return (base64_string, media_type)."""
    if data is None and path is None:
        raise ValueError("provide either 'data' or 'path'")
    if data is not None and path is not None:
        raise ValueError("provide 'data' OR 'path', not both")

    raw: bytes
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"file not found: {p}")
        raw = p.read_bytes()
        if not media_type:
            guessed, _ = mimetypes.guess_type(str(p))
            media_type = guessed or default
    else:
        if isinstance(data, bytes):
            raw = data
        elif isinstance(data, str):
            # Assume already base64-encoded
            return data, media_type or default
        else:
            raise TypeError("data must be bytes or base64 string")
        if not media_type:
            media_type = default

    encoded = base64.b64encode(raw).decode("ascii")
    return encoded, media_type


# -------------------- A2AMessage helpers --------------------


def message_from_parts(
    role: Literal["user", "agent"],
    *parts: dict[str, Any],
) -> A2AMessage:
    """Build an ``A2AMessage`` from one or more parts.

    Equivalent to ``A2AMessage(role=role, parts=[...])`` but shorter::

        A2AMessage.from_parts("user",
            text_part("here is the doc"),
            file_part(path="contract.pdf"),
        )
    """
    if not parts:
        raise ValueError("at least one part required")
    return A2AMessage(role=role, parts=list(parts))


def message_image(
    role: Literal["user", "agent"],
    *,
    text: str = "",
    image_path: str | Path | None = None,
    image_data: bytes | str | None = None,
    media_type: str = "",
    alt_text: str = "",
) -> A2AMessage:
    """Convenience: build a message with text + image part."""
    parts: list[dict[str, Any]] = []
    if text:
        parts.append(text_part(text))
    parts.append(
        image_part(
            data=image_data,
            path=image_path,
            media_type=media_type,
            alt_text=alt_text or text,
        )
    )
    return A2AMessage(role=role, parts=parts)


def message_file(
    role: Literal["user", "agent"],
    *,
    text: str = "",
    file_path: str | Path | None = None,
    file_data: bytes | str | None = None,
    media_type: str = "",
    filename: str = "",
) -> A2AMessage:
    """Convenience: build a message with text + file part."""
    parts: list[dict[str, Any]] = []
    if text:
        parts.append(text_part(text))
    parts.append(
        file_part(
            data=file_data,
            path=file_path,
            media_type=media_type,
            filename=filename,
        )
    )
    return A2AMessage(role=role, parts=parts)


# -------------------- Accessors --------------------


def message_get_images(msg: A2AMessage) -> list[dict[str, Any]]:
    """Return all image parts."""
    return [p for p in msg.parts if p.get("type") == "image"]


def message_get_files(msg: A2AMessage) -> list[dict[str, Any]]:
    """Return all file parts."""
    return [p for p in msg.parts if p.get("type") == "file"]


def message_get_data(msg: A2AMessage) -> list[dict[str, Any]]:
    """Return all structured-data parts."""
    return [p for p in msg.parts if p.get("type") == "data"]


def part_get_bytes(part: dict[str, Any]) -> bytes:
    """Decode an image/file part's base64 ``data`` to bytes."""
    if part.get("type") not in ("image", "file"):
        raise ValueError(f"part must be 'image' or 'file', got '{part.get('type')}'")
    data = part.get("data", "")
    if not isinstance(data, str):
        raise ValueError("part data must be a base64 string")
    try:
        return base64.b64decode(data, validate=True)
    except Exception as e:
        raise ValueError(f"invalid base64 data: {e}") from e


# -------------------- Monkey-patch A2AMessage with classmethods --------------------

# Add the new helpers to A2AMessage class so callers can do
# ``A2AMessage.from_parts(...)`` and ``A2AMessage.image(...)``.
# This is module-import-time only; idempotent.

if not hasattr(A2AMessage, "from_parts"):
    A2AMessage.from_parts = classmethod(  # type: ignore[attr-defined]
        lambda cls, role, *parts: message_from_parts(role, *parts)
    )
if not hasattr(A2AMessage, "image"):
    A2AMessage.image = classmethod(  # type: ignore[attr-defined]
        lambda cls, role, **kw: message_image(role, **kw)
    )
if not hasattr(A2AMessage, "file"):
    A2AMessage.file = classmethod(  # type: ignore[attr-defined]
        lambda cls, role, **kw: message_file(role, **kw)
    )


__all__ = [
    "PartType",
    "text_part",
    "image_part",
    "file_part",
    "data_part",
    "uri_part",
    "message_from_parts",
    "message_image",
    "message_file",
    "message_get_images",
    "message_get_files",
    "message_get_data",
    "part_get_bytes",
]
