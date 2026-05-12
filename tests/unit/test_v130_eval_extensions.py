"""v0.13.0: Tests for eval extensions (similarity + dataset versioning)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# -------------------- Dataset versioning --------------------

def test_hash_suite_yaml_stable():
    pytest.importorskip("yaml")
    from largestack._eval.extensions_v130 import hash_suite_yaml

    yaml = "name: test\ncases:\n  - name: c1\n    input: hi\n"
    h1 = hash_suite_yaml(yaml)
    h2 = hash_suite_yaml(yaml)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest


def test_hash_suite_yaml_ignores_whitespace_and_comments():
    pytest.importorskip("yaml")
    from largestack._eval.extensions_v130 import hash_suite_yaml

    yaml1 = "name: test\ncases:\n  - name: c1\n    input: hi"
    yaml2 = "# comment\nname: test\ncases:\n  - name: c1\n    input: hi\n\n"
    assert hash_suite_yaml(yaml1) == hash_suite_yaml(yaml2)


def test_hash_suite_yaml_changes_on_content_change():
    pytest.importorskip("yaml")
    from largestack._eval.extensions_v130 import hash_suite_yaml

    yaml1 = "name: a\ncases: []"
    yaml2 = "name: b\ncases: []"
    assert hash_suite_yaml(yaml1) != hash_suite_yaml(yaml2)


def test_version_suite_from_file(tmp_path):
    pytest.importorskip("yaml")
    from largestack._eval.extensions_v130 import version_suite

    p = tmp_path / "suite.yaml"
    p.write_text(textwrap.dedent("""\
        name: my-suite
        cases:
          - name: c1
            input: hi
          - name: c2
            input: bye
    """))

    v = version_suite(p)
    assert v.name == "my-suite"
    assert v.case_count == 2
    assert len(v.sha256) == 64
    assert "suite.yaml" in v.file_path


def test_version_suite_missing_file(tmp_path):
    from largestack._eval.extensions_v130 import version_suite
    with pytest.raises(FileNotFoundError):
        version_suite(tmp_path / "nope.yaml")


def test_short_hash():
    from largestack._eval.extensions_v130 import short_hash
    long_hash = "a" * 64
    assert short_hash(long_hash) == "a" * 12
    assert short_hash(long_hash, length=8) == "a" * 8


def test_enrich_report_adds_version():
    from largestack._eval.extensions_v130 import (
        enrich_report_with_version, SuiteVersion,
    )

    report = {"name": "x", "summary": {}}
    v = SuiteVersion(name="x", sha256="abc123" * 11, case_count=5)
    enriched = enrich_report_with_version(report, v)

    assert enriched["suite_version"]["sha256"] == v.sha256
    assert enriched["suite_short_hash"] == v.sha256[:12]


# -------------------- Embedding similarity assertion --------------------

@pytest.mark.asyncio
async def test_similarity_assertion_passes_for_identical():
    from largestack._eval.extensions_v130 import EmbeddingSimilarityAssertion

    a = EmbeddingSimilarityAssertion(
        expected="The user is in Bengaluru", threshold=0.95,
    )
    passed, sim, reason = await a.evaluate("The user is in Bengaluru")
    assert passed
    assert sim > 0.99


@pytest.mark.asyncio
async def test_similarity_assertion_fails_for_unrelated():
    from largestack._eval.extensions_v130 import EmbeddingSimilarityAssertion

    a = EmbeddingSimilarityAssertion(
        expected="machine learning research papers", threshold=0.5,
    )
    passed, sim, reason = await a.evaluate(
        "today's grocery shopping list",
    )
    assert not passed
    assert sim < 0.5


@pytest.mark.asyncio
async def test_similarity_assertion_partial_overlap_passes_with_low_threshold():
    from largestack._eval.extensions_v130 import EmbeddingSimilarityAssertion

    # Lower threshold catches partial paraphrases
    a = EmbeddingSimilarityAssertion(
        expected="The customer requested a loan",
        threshold=0.3,
    )
    passed, _, _ = await a.evaluate(
        "The customer asked about loans",
    )
    assert passed


@pytest.mark.asyncio
async def test_similarity_assertion_empty_actual_fails():
    from largestack._eval.extensions_v130 import EmbeddingSimilarityAssertion

    a = EmbeddingSimilarityAssertion(expected="x")
    passed, _, reason = await a.evaluate("")
    assert not passed
    assert "empty" in reason


# -------------------- parse_assertions --------------------

def test_parse_contains_assertion():
    from largestack._eval.extensions_v130 import parse_assertions

    assertions = parse_assertions({"contains": ["foo", "bar"]})
    assert len(assertions) == 2


def test_parse_equals_assertion():
    from largestack._eval.extensions_v130 import parse_assertions

    assertions = parse_assertions({"equals": "exactly this"})
    assert len(assertions) == 1


def test_parse_similarity_assertion_long_form():
    from largestack._eval.extensions_v130 import (
        parse_assertions, EmbeddingSimilarityAssertion,
    )

    assertions = parse_assertions({
        "similarity": {"expected": "ref text", "threshold": 0.85},
    })
    assert len(assertions) == 1
    assert isinstance(assertions[0], EmbeddingSimilarityAssertion)
    assert assertions[0].threshold == 0.85


def test_parse_similarity_assertion_shorthand():
    from largestack._eval.extensions_v130 import (
        parse_assertions, EmbeddingSimilarityAssertion,
    )

    assertions = parse_assertions({"similarity": "ref text"})
    assert len(assertions) == 1
    assert isinstance(assertions[0], EmbeddingSimilarityAssertion)
    assert assertions[0].expected == "ref text"


def test_parse_combined_assertions():
    """Multiple assertion types can coexist on a single case."""
    from largestack._eval.extensions_v130 import parse_assertions

    assertions = parse_assertions({
        "contains": "hello",
        "similarity": {"expected": "greeting", "threshold": 0.5},
    })
    assert len(assertions) == 2
