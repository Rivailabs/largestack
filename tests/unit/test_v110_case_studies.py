"""v0.11.0: Tests for case studies — credibility/marquee customer gap closer."""
from __future__ import annotations

from pathlib import Path

import pytest


CASE_DIR = Path(__file__).parent.parent.parent / "case_studies"


def test_case_studies_dir_exists():
    assert CASE_DIR.exists()
    assert CASE_DIR.is_dir()


def test_case_studies_index_present():
    readme = CASE_DIR / "README.md"
    assert readme.exists()
    content = readme.read_text()
    assert "LARGESTACK Case Studies" in content


def test_sri_rajeshwari_case_study():
    f = CASE_DIR / "sri_rajeshwari_nbfc.md"
    assert f.exists()
    content = f.read_text()
    # Must mention key features
    assert "KYCToolkit" in content
    assert "UPIToolkit" in content
    assert "Aadhaar" in content
    assert "DPDP" in content
    assert "RBI" in content
    # Must show concrete outcome
    assert "8 weeks" in content or "2 months" in content
    # Must explicitly reference real aggregators
    assert "Razorpay" in content
    assert "Signzy" in content


def test_legaldocs_case_study():
    f = CASE_DIR / "legaldocs_in.md"
    assert f.exists()
    content = f.read_text()
    assert "legaltech_app" in content
    assert "MCAToolkit" in content
    assert "eSign" in content.lower() or "esign" in content.lower()
    assert "Indian Contract Act" in content


def test_case_studies_have_substantial_content():
    """Each case study must be at least 800 chars (real, not stub)."""
    for f in CASE_DIR.glob("*.md"):
        if f.name == "README.md":
            continue
        size = len(f.read_text())
        assert size >= 800, f"{f.name} is too short: {size} chars"


def test_index_links_to_all_case_studies():
    readme = (CASE_DIR / "README.md").read_text()
    case_files = [
        f.name for f in CASE_DIR.glob("*.md") if f.name != "README.md"
    ]
    for case_file in case_files:
        assert case_file in readme, f"README doesn't link to {case_file}"
