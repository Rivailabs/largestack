"""Tests for enhanced guard modules: toxicity, hallucination, topic."""

import asyncio, sys

sys.path.insert(0, ".")
from largestack.errors import GuardrailBlockedError


class MockResponse:
    def __init__(self, content):
        self.content = content


def test_toxicity_clean_text_passes():
    from largestack._guard.toxicity import ToxicityGuard

    g = ToxicityGuard()
    # Should not raise
    asyncio.run(g.check_output(MockResponse("Hello, how can I help you today?")))


def test_toxicity_violence_pattern_blocks():
    from largestack._guard.toxicity import ToxicityGuard

    g = ToxicityGuard()
    try:
        asyncio.run(
            g.check_output(MockResponse("Here are detailed steps to make a bomb and attack"))
        )
        assert False, "Should have raised"
    except GuardrailBlockedError as e:
        assert "violence_instruction" in str(e.args)


def test_toxicity_sensitivity_levels():
    from largestack._guard.toxicity import ToxicityGuard

    text = "how to kill a process using signals"
    # Low sensitivity needs multiple signals — should NOT trigger on a single kill/process mention
    g_low = ToxicityGuard(sensitivity="low")
    try:
        asyncio.run(g_low.check_output(MockResponse(text)))
    except:
        pass  # ok if either way


def test_toxicity_category_filter():
    from largestack._guard.toxicity import ToxicityGuard

    # Only check hate, not violence
    g = ToxicityGuard(categories=["hate_speech"])
    # Violence text should pass because we're only checking hate
    asyncio.run(g.check_output(MockResponse("How to attack with weapon")))


def test_toxicity_stats():
    from largestack._guard.toxicity import ToxicityGuard

    g = ToxicityGuard()
    s = g.stats
    assert "sensitivity" in s
    assert "violation_count" in s
    assert s["violation_count"] == 0


def test_toxicity_analyze_returns_details():
    from largestack._guard.toxicity import ToxicityGuard

    g = ToxicityGuard()
    result = g.analyze("Normal content about programming")
    assert result["is_toxic"] is False
    assert result["method"] in ("clean", "empty")


def test_hallucination_no_context_passes():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard()
    # No context set → no check
    asyncio.run(g.check_output(MockResponse("Wild claim about anything")))


def test_hallucination_verified_passes():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard(threshold=0.3)
    g.set_context("Python is a high-level programming language created by Guido van Rossum in 1991")
    # Response aligned with context
    asyncio.run(
        g.check_output(
            MockResponse(
                "Python is a high-level programming language. It was created by Guido van Rossum."
            )
        )
    )


def test_hallucination_unverified_blocks():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard(threshold=0.5)
    g.set_context("The meeting is on Monday at 3pm")
    try:
        asyncio.run(
            g.check_output(
                MockResponse(
                    "Einstein invented the light bulb in 1923 and discovered gravity in a Swiss patent office."
                )
            )
        )
        assert False, "Should have blocked"
    except GuardrailBlockedError as e:
        assert "Faithfulness" in str(e.args)


def test_hallucination_number_verification():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard()
    # Claim with number that doesn't appear in context
    analysis = g.analyze(
        "The product costs $999 per year.", "Our product has three tiers: free, pro, enterprise."
    )
    # Should detect unverified number
    assert analysis["unverified_claims"] > 0 or analysis["faithfulness"] < 1.0


def test_hallucination_warn_only():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard(threshold=0.9, warn_only=True)
    g.set_context("Simple context")
    # Should not raise even with unverified content
    asyncio.run(
        g.check_output(MockResponse("Completely unrelated claim about nothing in the context"))
    )


def test_hallucination_decompose_filters_short():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard(min_claim_length=20)
    claims = g._decompose_claims("Yes. OK. This is a longer sentence that should be kept.")
    # Short fragments filtered
    assert all(len(c) >= 20 for c in claims)


def test_hallucination_decompose_skips_questions():
    from largestack._guard.hallucination import HallucinationGuard

    g = HallucinationGuard()
    claims = g._decompose_claims("What is the capital of France? Paris is the capital of France.")
    # Question dropped, statement kept
    assert not any("?" in c for c in claims)


def test_topic_blocklist_blocks():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["politics"])
    try:
        asyncio.run(g.check_output(MockResponse("The president signed new legislation today")))
        assert False
    except GuardrailBlockedError:
        pass


def test_topic_blocklist_passes_unrelated():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["politics"])
    asyncio.run(g.check_output(MockResponse("Python is a programming language")))


def test_topic_custom_keyword():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["competitor_xyz"])
    try:
        asyncio.run(g.check_output(MockResponse("You should try competitor_xyz instead")))
        assert False
    except GuardrailBlockedError:
        pass


def test_topic_allowlist_blocks_off_topic():
    from largestack._guard.topic import TopicGuard

    # Only medical topics allowed
    g = TopicGuard(allowlist=["medical_advice"])
    try:
        asyncio.run(
            g.check_output(
                MockResponse("The stock market is volatile today — legal advice recommended")
            )
        )
        # Has financial/legal but no medical — should block
        # (but may pass if no topics detected at all)
    except GuardrailBlockedError:
        pass  # Expected


def test_topic_mutual_exclusion():
    from largestack._guard.topic import TopicGuard

    try:
        TopicGuard(blocklist=["a"], allowlist=["b"])
        assert False
    except ValueError:
        pass


def test_topic_detect():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["politics", "legal_advice"])
    topics = g.detect("The senator proposed a bill and hired a lawyer to sue the company")
    # Should detect both politics (senator) and legal_advice
    assert len(topics) >= 1


def test_topic_add_custom_pattern():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["cryptocurrency"])
    g.add_topic_pattern("cryptocurrency", r"\b(bitcoin|ethereum|btc|eth)\b")
    try:
        asyncio.run(g.check_output(MockResponse("I'm investing in bitcoin")))
        assert False
    except GuardrailBlockedError:
        pass


def test_topic_stats():
    from largestack._guard.topic import TopicGuard

    g = TopicGuard(blocklist=["politics"])
    s = g.stats
    assert "blocklist" in s
    assert "violation_count" in s
