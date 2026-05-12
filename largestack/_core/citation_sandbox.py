"""Citation engine + code interpreter sandbox (v0.9.0).

Two production utilities for advanced RAG and tool-using agents:

1. ``CitationEngine`` — given an answer + retrieved docs, finds which
   sentences came from which docs and produces inline citations.

2. ``CodeInterpreter`` — sandboxed Python execution via subprocess
   isolation with timeout + resource limits. Safer than exec().
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.citation_sandbox")


# -------------------- Citation Engine --------------------

async def _terminate_process_safely(proc):
    """Terminate subprocess and drain pipes to avoid ResourceWarning leaks."""
    import asyncio
    import contextlib

    if proc is None:
        return

    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.communicate(), timeout=2)

    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), timeout=2)

@dataclass
class CitationMatch:
    """One citation: a sentence in the answer mapped to source docs."""
    sentence: str
    source_doc_indices: list[int] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class CitedAnswer:
    """Answer with citations woven in."""
    text_with_citations: str
    citations: list[CitationMatch] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


class CitationEngine:
    """Add inline citations to an answer based on retrieved documents.

    Uses Jaccard token overlap as the matching heuristic — simple,
    deterministic, no extra LLM calls. For high-stakes citations,
    swap with ``RankGPTCitationEngine`` (LLM-based, more accurate).

    Usage:
        engine = CitationEngine()
        cited = engine.cite(
            answer="The product launched in 2024. It supports both modes.",
            documents=[
                {"id": "doc1", "content": "Launched June 2024 in beta"},
                {"id": "doc2", "content": "Supports two modes: A and B"},
            ],
        )
        # cited.text_with_citations = "The product launched in 2024 [1]. ..."
    """

    def __init__(
        self,
        *,
        min_overlap: float = 0.15,
        citation_format: str = "[{n}]",
    ):
        self.min_overlap = min_overlap
        self.citation_format = citation_format

    @staticmethod
    def _tokenize(text: str) -> set:
        # Simple lowercase word tokens, excluding stopwords
        tokens = re.findall(r"\b[a-z][a-z0-9]+\b", text.lower())
        stopwords = {
            "the", "a", "an", "is", "are", "was", "were", "of", "and", "or",
            "in", "on", "at", "to", "for", "with", "as", "by", "this", "that",
            "it", "be", "been", "have", "has", "had", "from", "but",
        }
        return set(t for t in tokens if t not in stopwords)

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))

    def cite(self, answer: str, documents: list[dict]) -> CitedAnswer:
        """Generate citations for an answer."""
        # Split answer into sentences (simple regex)
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        sentences = [s for s in sentences if s.strip()]

        doc_token_sets = [self._tokenize(d.get("content", "")) for d in documents]

        citations: list[CitationMatch] = []
        cited_parts: list[str] = []

        for sent in sentences:
            sent_tokens = self._tokenize(sent)
            scores = [
                (i, self._jaccard(sent_tokens, doc_tokens))
                for i, doc_tokens in enumerate(doc_token_sets)
            ]
            relevant = [
                (i, sc) for i, sc in scores if sc >= self.min_overlap
            ]
            relevant.sort(key=lambda x: x[1], reverse=True)

            if relevant:
                # Cite top 1-2 sources
                top_sources = [i for i, _ in relevant[:2]]
                citation_str = " ".join(
                    self.citation_format.format(n=i + 1) for i in top_sources
                )
                # Insert before final punctuation
                if sent and sent[-1] in ".!?":
                    cited = sent[:-1].rstrip() + " " + citation_str + sent[-1]
                else:
                    cited = sent + " " + citation_str
                cited_parts.append(cited)
                citations.append(CitationMatch(
                    sentence=sent,
                    source_doc_indices=top_sources,
                    confidence=relevant[0][1],
                ))
            else:
                cited_parts.append(sent)
                citations.append(CitationMatch(sentence=sent))

        text_with_cites = " ".join(cited_parts)

        # Build sources list (only docs actually cited)
        used_indices = set()
        for c in citations:
            used_indices.update(c.source_doc_indices)
        sources = [
            {
                "n": i + 1,
                "id": documents[i].get("id", ""),
                "content_preview": (documents[i].get("content", "") or "")[:200],
                "metadata": documents[i].get("metadata", {}),
            }
            for i in sorted(used_indices)
            if i < len(documents)
        ]

        return CitedAnswer(
            text_with_citations=text_with_cites,
            citations=citations,
            sources=sources,
        )


# -------------------- Code Interpreter Sandbox --------------------

@dataclass
class CodeExecResult:
    """Result of executing code in sandbox."""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False
    error: str = ""

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.error


class CodeInterpreter:
    """Subprocess-based Python sandbox.

    Safer than ``exec()`` because:
    - Runs in separate process (memory + os isolation)
    - Hard timeout (kills runaway code)
    - Captured stdout/stderr only (no shared state with parent)
    - Configurable Python path / extra packages

    NOT a replacement for proper isolation (Docker/gVisor/Firecracker).
    Suitable for: data analysis on trusted CSV files, math computations,
    code generation that you'll review before running on real data.

    NOT suitable for: untrusted user-submitted code, anything that needs
    real isolation. Use a Docker-based sandbox for those.

    Args:
        timeout_seconds: hard kill after N seconds (default 30).
        python_executable: path to Python interpreter.
        allowed_modules: if set, only these modules can be imported.
        max_output_chars: truncate stdout/stderr.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        python_executable: str | None = None,
        allowed_modules: list[str] | None = None,
        max_output_chars: int = 10_000,
    ):
        self.timeout = timeout_seconds
        self.python = python_executable or sys.executable
        self.allowed_modules = allowed_modules
        self.max_output_chars = max_output_chars

    def _wrap_code(self, code: str) -> str:
        """Optional preamble for restricting imports."""
        if not self.allowed_modules:
            return code
        allowed_set = set(self.allowed_modules)
        preamble = f"""import builtins
__largestack_real_import = builtins.__import__
__largestack_allowed = {sorted(allowed_set)!r}
def __largestack_safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top not in __largestack_allowed:
        raise ImportError(f"module {{name!r}} not in allowlist")
    return __largestack_real_import(name, *args, **kwargs)
builtins.__import__ = __largestack_safe_import
"""
        return preamble + "\n" + code

    async def execute(
        self,
        code: str,
        *,
        env: dict | None = None,
        cwd: str | None = None,
    ) -> CodeExecResult:
        """Execute Python code in a fresh subprocess.

        Args:
            code: Python source code.
            env: optional env vars (default: empty for safety).
            cwd: working directory.
        """
        if not isinstance(code, str) or not code.strip():
            return CodeExecResult(error="empty code")

        wrapped = self._wrap_code(code)

        # Write to temp file (avoids shell-quoting issues)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8",
        ) as f:
            f.write(wrapped)
            script_path = f.name

        try:
            # Restricted env by default — only PATH & HOME
            run_env = env if env is not None else {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME") or tempfile.gettempdir(),
                "PYTHONUNBUFFERED": "1",
            }

            try:
                proc = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        self.python, script_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=run_env,
                        cwd=cwd,
                    ),
                    timeout=5,  # process startup
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=self.timeout,
                    )
                except asyncio.TimeoutError:
                    if proc.returncode is None:
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass

                    try:
                        stdout, stderr = await proc.communicate()
                    except Exception:
                        try:
                            await proc.wait()
                        except Exception:
                            pass
                        stdout, stderr = b"", b""

                    return CodeExecResult(
                        stdout="", stderr="",
                        returncode=-9, timed_out=True,
                        error=f"timed out after {self.timeout}s",
                    )

                so = (stdout or b"").decode("utf-8", errors="replace")
                se = (stderr or b"").decode("utf-8", errors="replace")
                if len(so) > self.max_output_chars:
                    so = so[: self.max_output_chars] + "\n...[truncated]"
                if len(se) > self.max_output_chars:
                    se = se[: self.max_output_chars] + "\n...[truncated]"

                return CodeExecResult(
                    stdout=so, stderr=se,
                    returncode=proc.returncode or 0,
                )
            except asyncio.TimeoutError:
                return CodeExecResult(
                    error="subprocess startup timed out", timed_out=True,
                )
            except FileNotFoundError as e:
                return CodeExecResult(error=f"python executable not found: {e}")
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def execute_sync(self, code: str, **kw) -> CodeExecResult:
        """Synchronous helper for testing / non-async callers."""
        return asyncio.run(self.execute(code, **kw))
