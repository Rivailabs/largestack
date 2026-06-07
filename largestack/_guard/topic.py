"""Topic-based content filtering — allowlist/blocklist with semantic fallback."""

from __future__ import annotations
import re, logging
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.guard.topic")


class TopicGuard:
    """Block conversations on unwanted topics or enforce topic allowlist.

    Two modes:
      - blocklist: Block if content matches blocked topics
      - allowlist: Block if content doesn't match any allowed topic

    Detection layers:
      1. Keyword match (fast, always-on)
      2. Regex patterns for each topic
      3. Custom classifier (optional LLM-based)

        # Block competitor topics
        guard = TopicGuard(blocklist=["competitor_a", "competitor_b"])

        # Only allow work topics
        guard = TopicGuard(allowlist=["software", "engineering", "product"])

        # With semantic matching
        guard = TopicGuard(blocklist=["politics"], mode="semantic", classifier=llm_fn)
    """

    # Predefined topic patterns
    TOPIC_PATTERNS = {
        "politics": [
            r"\b(election|president|congress|senate|vote|voting|political|democrat|republican)\b",
            r"\b(liberal|conservative|left\-?wing|right\-?wing|partisan)\b",
        ],
        "medical_advice": [
            r"\b(diagnos(e|is)|prescribe|medication|dosage|treat(ment)?)\b",
            r"\b(cure|symptom|disease|illness|medical condition)\b",
        ],
        "legal_advice": [
            r"\b(lawyer|attorney|lawsuit|legal advice|sue|litigation|contract)\b",
            r"\b(court|judge|jury|plea|verdict|settlement)\b",
        ],
        "financial_advice": [
            r"\b(invest(ment)?|stock|portfolio|buy|sell|trade) .{0,20}(advice|recommend)\b",
            r"\b(should I (buy|sell|invest))\b",
        ],
        "adult_content": [
            r"\b(explicit|nsfw|adult|porn|sexual content)\b",
        ],
        "gambling": [
            r"\b(bet|gambling|casino|poker|blackjack|wager)\b",
        ],
        "weapons": [
            r"\b(firearm|handgun|rifle|ammo|ammunition|firearm purchase)\b",
        ],
    }

    def __init__(
        self,
        blocklist: list[str] = None,
        allowlist: list[str] = None,
        mode: str = "keyword",
        classifier=None,
        check_output: bool = True,
        check_input: bool = True,
        sensitivity: str = "medium",
    ):
        """
        Args:
          blocklist: Topics to block (either predefined names or keywords)
          allowlist: Only allow these topics (mutually exclusive with blocklist)
          mode: "keyword" (regex) or "semantic" (classifier function)
          classifier: Callable(text) → list of topics (for semantic mode)
          sensitivity: "low" (3+ matches), "medium" (1+), "high" (1+)
        """
        if blocklist and allowlist:
            raise ValueError("Cannot use both blocklist and allowlist")

        self.blocklist = blocklist or []
        self.allowlist = allowlist or []
        self.mode = mode
        self.classifier = classifier
        self.should_check_output = check_output
        self.should_check_input = check_input
        self.sensitivity = sensitivity
        self._violation_count = 0

        # Compile patterns for each topic
        self._compiled: dict[str, list] = {}
        for topic in self.blocklist + self.allowlist:
            patterns = self.TOPIC_PATTERNS.get(topic, [rf"\b{re.escape(topic)}\b"])
            self._compiled[topic] = [re.compile(p, re.I) for p in patterns]

    def _min_matches(self) -> int:
        return {"low": 3, "medium": 1, "high": 1}.get(self.sensitivity, 1)

    async def check_input(self, messages):
        if not self.should_check_input:
            return
        for m in messages:
            c = m.get("content", "")
            if isinstance(c, str):
                self._verify(c, "input")

    async def check_output(self, response) -> None:
        if not self.should_check_output:
            return
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, str):
            self._verify(content, "output")

    def _verify(self, text: str, direction: str):
        """Check text against topic policies."""
        detected = self._detect_topics(text)

        if self.blocklist:
            # Blocklist: raise if any blocked topic found
            blocked = [t for t in detected if t in self.blocklist]
            if blocked:
                self._violation_count += 1
                raise GuardrailBlockedError(
                    "topic", f"Blocked topic(s) detected in {direction}: {blocked}"
                )

        if self.allowlist:
            # Allowlist: raise if NO allowed topic found
            allowed_found = [t for t in detected if t in self.allowlist]
            if not allowed_found and detected:
                # Content has topics but none are allowed
                self._violation_count += 1
                raise GuardrailBlockedError(
                    "topic", f"Content not in allowlist (detected: {detected})"
                )

    def _detect_topics(self, text: str) -> list[str]:
        """Detect which topics appear in text."""
        detected = []
        min_matches = self._min_matches()

        # Keyword/regex layer
        for topic, patterns in self._compiled.items():
            matches = sum(1 for p in patterns if p.search(text))
            if matches >= min_matches:
                detected.append(topic)

        # Semantic classifier layer (if configured)
        if self.mode == "semantic" and self.classifier:
            try:
                semantic_topics = self.classifier(text)
                if isinstance(semantic_topics, list):
                    detected.extend(t for t in semantic_topics if t not in detected)
            except Exception as e:
                log.warning(f"Semantic classifier failed: {e}")

        return detected

    def detect(self, text: str) -> list[str]:
        """Public topic detection (no enforcement)."""
        return self._detect_topics(text)

    def add_topic_pattern(self, topic: str, pattern: str):
        """Register a custom topic pattern."""
        compiled = re.compile(pattern, re.I)
        if topic in self._compiled:
            self._compiled[topic].append(compiled)
        else:
            self._compiled[topic] = [compiled]

    @property
    def stats(self) -> dict:
        return {
            "blocklist": self.blocklist,
            "allowlist": self.allowlist,
            "mode": self.mode,
            "violation_count": self._violation_count,
            "topics_configured": list(self._compiled.keys()),
        }
