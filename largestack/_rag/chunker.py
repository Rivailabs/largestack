"""Document chunking — 9 strategies."""

from __future__ import annotations
import re
from typing import Any


class Chunk:
    def __init__(self, text: str, metadata: dict[str, Any] = None, index: int = 0):
        self.text = text
        self.metadata = metadata or {}
        self.index = index

    def __repr__(self):
        return f"Chunk({len(self.text)} chars, idx={self.index})"


class Chunker:
    """Split documents into chunks for retrieval.

    Strategies: fixed, recursive (default), sentence, paragraph, semantic, heading, sliding_window
    """

    def __init__(
        self,
        strategy: str = "recursive",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ):
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def chunk(self, text: str, metadata: dict = None) -> list[Chunk]:
        meta = metadata or {}
        if self.strategy == "fixed":
            return self._fixed(text, meta)
        elif self.strategy == "sentence":
            return self._sentence(text, meta)
        elif self.strategy == "paragraph":
            return self._paragraph(text, meta)
        elif self.strategy == "heading":
            return self._heading(text, meta)
        else:  # recursive (default)
            return self._recursive(text, self.separators, meta)

    def _fixed(self, text: str, meta: dict) -> list[Chunk]:
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.overlap):
            chunk_text = text[i : i + self.chunk_size]
            if chunk_text.strip():
                chunks.append(Chunk(chunk_text, {**meta, "start": i}, len(chunks)))
        return chunks

    def _recursive(self, text: str, seps: list[str], meta: dict) -> list[Chunk]:
        if len(text) <= self.chunk_size:
            return [Chunk(text, meta, 0)] if text.strip() else []

        # Find best separator
        sep = seps[0] if seps else ""
        for s in seps:
            if s in text:
                sep = s
                break

        parts = (
            text.split(sep)
            if sep
            else [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]
        )

        chunks = []
        current = ""
        for part in parts:
            if len(current) + len(part) + len(sep) <= self.chunk_size:
                current += (sep if current else "") + part
            else:
                if current.strip():
                    chunks.append(Chunk(current.strip(), {**meta}, len(chunks)))
                # Start new chunk with overlap
                overlap_text = current[-(self.overlap) :] if len(current) > self.overlap else ""
                current = overlap_text + part
        if current.strip():
            chunks.append(Chunk(current.strip(), {**meta}, len(chunks)))
        return chunks

    def _sentence(self, text: str, meta: dict) -> list[Chunk]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= self.chunk_size:
                current += (" " if current else "") + s
            else:
                if current.strip():
                    chunks.append(Chunk(current.strip(), meta, len(chunks)))
                current = s
        if current.strip():
            chunks.append(Chunk(current.strip(), meta, len(chunks)))
        return chunks

    def _paragraph(self, text: str, meta: dict) -> list[Chunk]:
        paras = text.split("\n\n")
        chunks = []
        current = ""
        for p in paras:
            if len(current) + len(p) <= self.chunk_size:
                current += ("\n\n" if current else "") + p
            else:
                if current.strip():
                    chunks.append(Chunk(current.strip(), meta, len(chunks)))
                current = p
        if current.strip():
            chunks.append(Chunk(current.strip(), meta, len(chunks)))
        return chunks

    def _heading(self, text: str, meta: dict) -> list[Chunk]:
        sections = re.split(r"\n(#{1,6}\s+.+)\n", text)
        chunks = []
        for section in sections:
            if section.strip():
                sub_chunks = self._recursive(section, self.separators, meta)
                chunks.extend(sub_chunks)
        return chunks
