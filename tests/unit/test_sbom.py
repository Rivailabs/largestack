"""Tests for SBOM generator."""
import os, sys, tempfile; sys.path.insert(0, ".")

def test_cyclonedx_generation():
    from largestack._security.sbom import SBOMGenerator
    gen = SBOMGenerator()
    sbom = gen.generate("cyclonedx")
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert len(sbom["components"]) > 0

def test_spdx_generation():
    from largestack._security.sbom import SBOMGenerator
    gen = SBOMGenerator()
    sbom = gen.generate("spdx")
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert len(sbom["packages"]) > 0

def test_save_to_file():
    from largestack._security.sbom import SBOMGenerator
    gen = SBOMGenerator()
    path = os.path.join(tempfile.mkdtemp(), "sbom.json")
    gen.generate("cyclonedx", output_path=path)
    assert os.path.exists(path)

def test_summary():
    from largestack._security.sbom import SBOMGenerator
    gen = SBOMGenerator()
    s = gen.summary
    assert "direct_deps" in s
    assert "formats_supported" in s

def test_bad_format():
    from largestack._security.sbom import SBOMGenerator
    gen = SBOMGenerator()
    try:
        gen.generate("xml")
        assert False
    except ValueError:
        pass
