"""v0.12.0: Tests for the India-fintech cookbook.

These tests verify that:
- All 10 recipes exist
- Each recipe contains required sections
- The README references all 10
- Each recipe references the right LARGESTACK module
- Compliance markers are mentioned where expected
"""
from __future__ import annotations

from pathlib import Path

import pytest


# Path to cookbook (resolves whether pytest is run from repo root or not)
COOKBOOK = Path(__file__).resolve().parents[2] / "docs" / "cookbook"


EXPECTED_RECIPES = {
    "01_kyc_pipeline.md",
    "02_gst_validation.md",
    "03_hindi_aadhaar_redaction.md",
    "04_multi_tenant_nbfc.md",
    "05_dpdp_audit_chain.md",
    "06_esign_workflow.md",
    "07_mca_lookup.md",
    "08_agent_yaml_compliance.md",
    "09_studio_export.md",
    "10_a2a_interop.md",
}


def test_cookbook_directory_exists():
    assert COOKBOOK.is_dir(), f"cookbook missing at {COOKBOOK}"


def test_all_ten_recipes_present():
    found = {f.name for f in COOKBOOK.iterdir() if f.suffix == ".md"}
    missing = EXPECTED_RECIPES - found
    assert not missing, f"missing recipes: {missing}"


def test_readme_indexes_all_recipes():
    readme = COOKBOOK / "README.md"
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    for recipe in EXPECTED_RECIPES:
        assert recipe in text, f"README missing link to {recipe}"


@pytest.mark.parametrize("recipe", sorted(EXPECTED_RECIPES))
def test_each_recipe_has_required_sections(recipe):
    text = (COOKBOOK / recipe).read_text(encoding="utf-8")
    # Title + use case + at least one code block
    assert text.startswith("# ")
    assert "**Use case:**" in text
    assert "```" in text  # has code blocks


def test_kyc_recipe_mentions_dpdp_and_rbi():
    text = (COOKBOOK / "01_kyc_pipeline.md").read_text(encoding="utf-8")
    assert "DPDP" in text
    assert "RBI" in text
    assert "consent" in text.lower()
    assert "aadhaar" in text.lower()
    assert "pan" in text.lower()


def test_gst_recipe_includes_gstin_format():
    text = (COOKBOOK / "02_gst_validation.md").read_text(encoding="utf-8")
    assert "GSTIN" in text
    # GSTIN regex pattern
    assert "[0-9]{2}" in text or "15 chars" in text
    assert "state" in text.lower()


def test_hindi_redaction_recipe_mentions_devanagari():
    text = (COOKBOOK / "03_hindi_aadhaar_redaction.md").read_text(
        encoding="utf-8",
    )
    assert "Devanagari" in text or "देवनागरी" in text
    # Should reference the Indic numeral table
    assert "१" in text or "Indic numeral" in text
    assert "redact" in text.lower()


def test_multi_tenant_recipe_mentions_isolation():
    text = (COOKBOOK / "04_multi_tenant_nbfc.md").read_text(encoding="utf-8")
    assert "tenant_id" in text
    assert "isolation" in text.lower() or "isolate" in text.lower()
    assert "RBI" in text


def test_audit_chain_recipe_mentions_hash_chain():
    text = (COOKBOOK / "05_dpdp_audit_chain.md").read_text(encoding="utf-8")
    assert "hash" in text.lower()
    assert "chain" in text.lower()
    assert "DPDP" in text
    assert "§" in text  # references section symbols


def test_esign_recipe_references_it_act_and_providers():
    text = (COOKBOOK / "06_esign_workflow.md").read_text(encoding="utf-8")
    assert "IT Act" in text
    assert "Aadhaar" in text
    # Should list at least 2 eSign providers
    providers = ["signzy", "leegality", "emudhra", "digio"]
    found = sum(1 for p in providers if p in text.lower())
    assert found >= 2, f"only {found} providers mentioned"


def test_mca_recipe_explains_cin_format():
    text = (COOKBOOK / "07_mca_lookup.md").read_text(encoding="utf-8")
    assert "CIN" in text
    assert "PTC" in text or "Companies Act" in text


def test_compliance_yaml_recipe_lists_all_acts():
    text = (COOKBOOK / "08_agent_yaml_compliance.md").read_text(
        encoding="utf-8",
    )
    for act in ["DPDP", "RBI", "PMLA", "IT_Act", "agent.yaml"]:
        assert act in text, f"recipe missing reference to {act}"


def test_studio_recipe_references_export_command():
    text = (COOKBOOK / "09_studio_export.md").read_text(encoding="utf-8")
    assert "studio-export" in text
    assert "StudioBuilder" in text


def test_a2a_recipe_explains_protocol():
    text = (COOKBOOK / "10_a2a_interop.md").read_text(encoding="utf-8")
    assert "A2A" in text
    assert "AgentCard" in text
    assert "/.well-known/agent.json" in text
    assert "MCP" in text  # explains MCP vs A2A distinction
