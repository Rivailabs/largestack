from pathlib import Path

import pytest

from largestack._core.parsers import OutputParseError, parse_xml
from largestack._loaders import load_xml


def test_parse_xml_basic():
    assert parse_xml("<root><item>hello</item></root>") == {"root": {"item": "hello"}}


def test_parse_xml_rejects_dtd_entity_attack():
    malicious = """<?xml version="1.0"?>
<!DOCTYPE root [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>
"""
    with pytest.raises(OutputParseError):
        parse_xml(malicious)


@pytest.mark.asyncio
async def test_load_xml_basic(tmp_path: Path):
    p = tmp_path / "sample.xml"
    p.write_text("<root><item>hello</item></root>", encoding="utf-8")

    docs = await load_xml(str(p))

    assert docs[0]["metadata"]["format"] == "xml"
    assert docs[0]["metadata"]["root_tag"] == "root"
    assert "hello" in docs[0]["metadata"]["text_only"]


@pytest.mark.asyncio
async def test_load_xml_rejects_dtd_entity_attack(tmp_path: Path):
    p = tmp_path / "bad.xml"
    p.write_text(
        """<?xml version="1.0"?>
<!DOCTYPE root [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>
""",
        encoding="utf-8",
    )

    docs = await load_xml(str(p))

    assert "XML parse error" in docs[0]["metadata"]["error"]
