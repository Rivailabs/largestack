"""v0.7.0: Document loader tests."""
from __future__ import annotations

import json
import pytest


@pytest.mark.asyncio
async def test_load_text(tmp_path):
    from largestack._loaders import load_text
    p = tmp_path / "t.txt"
    p.write_text("Hello world\nLine 2", encoding="utf-8")
    docs = await load_text(str(p))
    assert len(docs) == 1
    assert docs[0]["content"] == "Hello world\nLine 2"
    assert docs[0]["metadata"]["format"] == "text"
    assert docs[0]["metadata"]["source"] == str(p)


@pytest.mark.asyncio
async def test_load_text_missing_file(tmp_path):
    from largestack._loaders import load_text
    docs = await load_text(str(tmp_path / "no.txt"))
    assert "error" in docs[0]["metadata"]


@pytest.mark.asyncio
async def test_load_markdown_basic(tmp_path):
    from largestack._loaders import load_markdown
    p = tmp_path / "doc.md"
    p.write_text("# Title\n\nSome body.", encoding="utf-8")
    docs = await load_markdown(str(p))
    assert "# Title" in docs[0]["content"]
    assert docs[0]["metadata"]["format"] == "markdown"


@pytest.mark.asyncio
async def test_load_markdown_with_frontmatter(tmp_path):
    """YAML frontmatter must be parsed into metadata, body kept as content."""
    pytest.importorskip("yaml")
    from largestack._loaders import load_markdown
    p = tmp_path / "fm.md"
    p.write_text(
        "---\ntitle: My Post\nauthor: Sachith\ntags:\n  - ai\n  - largestack\n---\n\nBody text.",
        encoding="utf-8",
    )
    docs = await load_markdown(str(p))
    assert "Body text" in docs[0]["content"]
    assert "title" not in docs[0]["content"]  # stripped
    assert docs[0]["metadata"].get("title") == "My Post"
    assert docs[0]["metadata"].get("author") == "Sachith"


@pytest.mark.asyncio
async def test_load_csv_with_header(tmp_path):
    from largestack._loaders import load_csv
    p = tmp_path / "data.csv"
    p.write_text("name,age,city\nAlice,30,Bengaluru\nBob,25,Mumbai\n", encoding="utf-8")
    docs = await load_csv(str(p))
    assert len(docs) == 2
    assert docs[0]["metadata"]["row"] == 0
    assert docs[0]["metadata"]["fields"]["name"] == "Alice"
    assert "Bengaluru" in docs[0]["content"]


@pytest.mark.asyncio
async def test_load_csv_no_header(tmp_path):
    from largestack._loaders import load_csv
    p = tmp_path / "raw.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    docs = await load_csv(str(p), has_header=False)
    assert len(docs) == 2  # both rows treated as data
    assert "a | b | c" in docs[0]["content"]


@pytest.mark.asyncio
async def test_load_json_object(tmp_path):
    from largestack._loaders import load_json
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"name": "Sachith"}), encoding="utf-8")
    docs = await load_json(str(p))
    assert len(docs) == 1
    assert "Sachith" in docs[0]["content"]


@pytest.mark.asyncio
async def test_load_json_array_creates_doc_per_item(tmp_path):
    from largestack._loaders import load_json
    p = tmp_path / "arr.json"
    p.write_text(json.dumps([{"id": 1}, {"id": 2}, {"id": 3}]), encoding="utf-8")
    docs = await load_json(str(p))
    assert len(docs) == 3
    assert docs[0]["metadata"]["index"] == 0
    assert docs[2]["metadata"]["index"] == 2


@pytest.mark.asyncio
async def test_load_jsonl(tmp_path):
    from largestack._loaders import load_jsonl
    p = tmp_path / "lines.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}\n\n{"a": 3}\n', encoding="utf-8")
    docs = await load_jsonl(str(p))
    assert len(docs) == 3  # blank line skipped


@pytest.mark.asyncio
async def test_load_jsonl_skips_malformed_lines(tmp_path):
    from largestack._loaders import load_jsonl
    p = tmp_path / "mixed.jsonl"
    p.write_text('{"ok": 1}\nBAD LINE\n{"ok": 2}\n', encoding="utf-8")
    docs = await load_jsonl(str(p))
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_load_yaml(tmp_path):
    pytest.importorskip("yaml")
    from largestack._loaders import load_yaml
    p = tmp_path / "config.yaml"
    p.write_text("name: LARGESTACK\nversion: 0.7.0\nfeatures:\n  - litellm\n  - langchain\n",
                 encoding="utf-8")
    docs = await load_yaml(str(p))
    assert "LARGESTACK" in docs[0]["content"]
    assert docs[0]["metadata"]["format"] == "yaml"


@pytest.mark.asyncio
async def test_load_yaml_invalid(tmp_path):
    pytest.importorskip("yaml")
    from largestack._loaders import load_yaml
    p = tmp_path / "bad.yaml"
    p.write_text("[invalid: : :", encoding="utf-8")
    docs = await load_yaml(str(p))
    assert "error" in docs[0]["metadata"]


@pytest.mark.asyncio
async def test_load_xml(tmp_path):
    from largestack._loaders import load_xml
    p = tmp_path / "data.xml"
    p.write_text(
        '<?xml version="1.0"?><root><item>One</item><item>Two</item></root>',
        encoding="utf-8",
    )
    docs = await load_xml(str(p))
    assert docs[0]["metadata"]["root_tag"] == "root"
    assert "One" in docs[0]["metadata"]["text_only"]


@pytest.mark.asyncio
async def test_load_xml_invalid(tmp_path):
    from largestack._loaders import load_xml
    p = tmp_path / "bad.xml"
    p.write_text("not xml at all", encoding="utf-8")
    docs = await load_xml(str(p))
    assert "error" in docs[0]["metadata"]


@pytest.mark.asyncio
async def test_dispatcher_routes_by_extension(tmp_path):
    """The ``load()`` dispatcher must auto-route by extension."""
    from largestack._loaders import load

    # txt
    p = tmp_path / "t.txt"; p.write_text("hello")
    docs = await load(str(p))
    assert docs[0]["metadata"]["format"] == "text"

    # md
    p = tmp_path / "x.md"; p.write_text("# H")
    docs = await load(str(p))
    assert docs[0]["metadata"]["format"] == "markdown"

    # csv
    p = tmp_path / "x.csv"; p.write_text("a,b\n1,2")
    docs = await load(str(p))
    assert docs[0]["metadata"]["format"] == "csv"

    # json
    p = tmp_path / "x.json"; p.write_text('{"a":1}')
    docs = await load(str(p))
    assert docs[0]["metadata"]["format"] == "json"


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_text(tmp_path):
    from largestack._loaders import load
    p = tmp_path / "weird.unknown"
    p.write_text("plain text content")
    docs = await load(str(p))
    assert docs[0]["metadata"]["format"] == "text"
    assert "plain text content" in docs[0]["content"]


@pytest.mark.asyncio
async def test_load_pdf_when_pypdf_missing(monkeypatch, tmp_path):
    """If pypdf isn't installed, return graceful error doc."""
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\n")  # malformed but exists
    
    # Monkeypatch import to simulate missing pypdf
    import sys
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    
    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("Mocked: pypdf not installed")
        return real_import(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", fake_import)
    
    from largestack._loaders import load_pdf
    docs = await load_pdf(str(p))
    assert "pypdf" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_docx_when_python_docx_missing(monkeypatch, tmp_path):
    """If python-docx isn't installed, return graceful error doc."""
    p = tmp_path / "x.docx"
    p.write_bytes(b"fake docx")

    import sys
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    
    def fake_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("Mocked")
        return real_import(name, *args, **kwargs)
    
    monkeypatch.setattr("builtins.__import__", fake_import)
    
    from largestack._loaders import load_docx
    docs = await load_docx(str(p))
    assert "python-docx" in docs[0]["metadata"]["error"]


@pytest.mark.asyncio
async def test_load_html_strips_tags(tmp_path):
    pytest.importorskip("bs4")
    from largestack._loaders import load_html
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>Hi</title></head>"
        "<body><script>alert(1)</script>"
        "<p>Hello world</p>"
        "<style>body{color:red}</style></body></html>",
        encoding="utf-8",
    )
    docs = await load_html(str(p))
    assert "Hello world" in docs[0]["content"]
    assert "alert" not in docs[0]["content"]  # script stripped
    assert "color:red" not in docs[0]["content"]  # style stripped
    assert docs[0]["metadata"]["title"] == "Hi"
