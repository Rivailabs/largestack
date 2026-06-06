"""Output sanitization — OWASP LLM05 (Improper Output Handling).

LLM output is untrusted input to whatever renders/executes it. This helper
neutralizes the common ways model output causes downstream harm when injected
into HTML, a shell, or SQL. It does NOT replace context-appropriate escaping in
your app — it's a defense-in-depth pass you can run before handing output on.

    from largestack._guard.output_sanitizer import OutputSanitizer
    safe = OutputSanitizer().sanitize(llm_text, mode="html")   # HTML-escaped, scripts stripped
    findings = OutputSanitizer().scan(llm_text)                 # list of risky-pattern hits
"""
from __future__ import annotations
import html
import re

# Patterns that indicate output which is dangerous if rendered/executed downstream.
_RISKY = [
    ("script_tag", re.compile(r"<\s*script\b", re.I)),
    ("event_handler", re.compile(r"\bon\w+\s*=", re.I)),         # onclick=, onload=
    ("js_uri", re.compile(r"\b(javascript|vbscript)\s*:", re.I)),
    ("data_html_uri", re.compile(r"data:text/html", re.I)),
    ("iframe", re.compile(r"<\s*iframe\b", re.I)),
    ("sql_meta", re.compile(r"(;\s*drop\s+table|--\s|/\*|\bunion\s+select\b)", re.I)),
    ("shell_meta", re.compile(r"(\$\(|\bcurl\b.+\|\s*sh\b|;\s*rm\s+-rf)", re.I)),
]


class OutputSanitizer:
    """Sanitize / scan LLM output before downstream rendering or execution."""

    def scan(self, text: str) -> list[str]:
        """Return the names of risky patterns present (empty list = clean)."""
        if not text:
            return []
        return [name for name, pat in _RISKY if pat.search(text)]

    def sanitize(self, text: str, mode: str = "html") -> str:
        """Return a sanitized copy.

        mode='html'  → HTML-escape everything, then drop <script>/<iframe> blocks and
                       neutralize javascript:/vbscript: URIs (safe to render as HTML).
        mode='text'  → strip <script>/<iframe> blocks and inline event handlers, leave text.
        """
        if not text:
            return text
        if mode == "html":
            out = html.escape(text, quote=True)
            return out
        # text mode: remove the most dangerous constructs but keep readable text
        out = re.sub(r"<\s*script\b.*?<\s*/\s*script\s*>", "", text, flags=re.I | re.S)
        out = re.sub(r"<\s*iframe\b.*?<\s*/\s*iframe\s*>", "", out, flags=re.I | re.S)
        out = re.sub(r"\bon\w+\s*=\s*(\".*?\"|'.*?'|[^\s>]+)", "", out, flags=re.I | re.S)
        out = re.sub(r"\b(javascript|vbscript)\s*:", "blocked:", out, flags=re.I)
        return out

    def is_safe(self, text: str) -> bool:
        return not self.scan(text)
