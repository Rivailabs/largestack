"""v0.9.0: Tests for 6 new toolkits."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

respx = pytest.importorskip("respx")


# -------------------- SQLToolkit --------------------

@pytest.mark.asyncio
async def test_sql_toolkit_lists_tables():
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine, text
    from largestack._integrations import SQLToolkit
    import tempfile
    import os

    db_path = tempfile.mktemp(suffix=".db")
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INT, name TEXT)"))
        conn.execute(text("CREATE TABLE orders (id INT, user_id INT)"))
        conn.commit()
    eng.dispose()

    try:
        tk = SQLToolkit(f"sqlite:///{db_path}")
        list_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "list_tables")
        result = await list_tool()
        data = json.loads(result)
        assert "users" in data["tables"]
        assert "orders" in data["tables"]
        assert data["dialect"] == "sqlite"
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_sql_toolkit_describe_table():
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine, text
    from largestack._integrations import SQLToolkit
    import tempfile, os

    db_path = tempfile.mktemp(suffix=".db")
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as conn:
        conn.execute(text(
            "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price REAL)"
        ))
        conn.commit()
    eng.dispose()

    try:
        tk = SQLToolkit(f"sqlite:///{db_path}")
        desc_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "describe_table")
        result = await desc_tool("products")
        data = json.loads(result)
        col_names = [c["name"] for c in data["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "price" in col_names
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_sql_toolkit_query_runs_select():
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine, text
    from largestack._integrations import SQLToolkit
    import tempfile, os

    db_path = tempfile.mktemp(suffix=".db")
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as conn:
        conn.execute(text("CREATE TABLE u (id INT, name TEXT)"))
        conn.execute(text("INSERT INTO u VALUES (1, 'Alice'), (2, 'Bob')"))
        conn.commit()
    eng.dispose()

    try:
        tk = SQLToolkit(f"sqlite:///{db_path}")
        q_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "query")
        result = await q_tool("SELECT * FROM u ORDER BY id")
        data = json.loads(result)
        assert data["row_count"] == 2
        assert data["rows"][0]["name"] == "Alice"
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_sql_toolkit_blocks_writes_in_read_only_mode():
    pytest.importorskip("sqlalchemy")
    from largestack._integrations import SQLToolkit
    tk = SQLToolkit("sqlite:///:memory:", read_only=True)
    q_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "query")
    result = await q_tool("INSERT INTO users VALUES (1, 'x')")
    assert "rejected" in result.lower()
    assert "read-only" in result


@pytest.mark.asyncio
async def test_sql_toolkit_blocks_multistatement():
    pytest.importorskip("sqlalchemy")
    from largestack._integrations import SQLToolkit
    tk = SQLToolkit("sqlite:///:memory:")
    q_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "query")
    result = await q_tool("SELECT 1; SELECT 2; SELECT 3")
    assert "multi-statement" in result.lower()


# -------------------- PandasToolkit --------------------

@pytest.mark.asyncio
async def test_pandas_toolkit_info():
    pd = pytest.importorskip("pandas")
    from largestack._integrations import PandasToolkit
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    tk = PandasToolkit(df)
    info_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "dataframe_info")
    result = await info_tool()
    data = json.loads(result)
    assert data["shape"] == [3, 2]
    assert "a" in data["columns"]
    assert data["null_counts"]["a"] == 0


@pytest.mark.asyncio
async def test_pandas_toolkit_query():
    pd = pytest.importorskip("pandas")
    from largestack._integrations import PandasToolkit
    df = pd.DataFrame({"age": [25, 35, 45], "name": ["A", "B", "C"]})
    tk = PandasToolkit(df)
    q_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "dataframe_query")
    result = await q_tool("age > 30")
    data = json.loads(result)
    assert data["matched_count"] == 2
    names = [r["name"] for r in data["rows"]]
    assert "B" in names
    assert "C" in names


@pytest.mark.asyncio
async def test_pandas_toolkit_aggregate():
    pd = pytest.importorskip("pandas")
    from largestack._integrations import PandasToolkit
    df = pd.DataFrame({
        "category": ["A", "A", "B", "B"],
        "value": [10, 20, 30, 40],
    })
    tk = PandasToolkit(df)
    agg_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "dataframe_aggregate")
    result = await agg_tool("category", "value", "sum")
    data = json.loads(result)
    assert data["agg_func"] == "sum"
    rows = {r["category"]: int(r["value"]) for r in data["rows"]}
    assert rows["A"] == 30
    assert rows["B"] == 70


@pytest.mark.asyncio
async def test_pandas_toolkit_rejects_invalid_aggfunc():
    pd = pytest.importorskip("pandas")
    from largestack._integrations import PandasToolkit
    df = pd.DataFrame({"a": [1], "b": [2]})
    tk = PandasToolkit(df)
    agg_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "dataframe_aggregate")
    result = await agg_tool("a", "b", "eval")  # dangerous
    assert "must be one of" in result


def test_pandas_toolkit_rejects_non_dataframe():
    pytest.importorskip("pandas")
    from largestack._integrations import PandasToolkit
    with pytest.raises(TypeError):
        PandasToolkit("not a dataframe")


# -------------------- StripeToolkit --------------------

@pytest.mark.asyncio
async def test_stripe_toolkit_no_key(monkeypatch):
    monkeypatch.delenv("LARGESTACK_STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    from largestack._integrations import StripeToolkit
    tk = StripeToolkit()
    fp_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "stripe_fetch_payment_intent")
    result = await fp_tool("pi_test")
    assert "LARGESTACK_STRIPE_API_KEY" in result


@pytest.mark.asyncio
async def test_stripe_toolkit_fetch_payment_intent():
    from largestack._integrations import StripeToolkit
    tk = StripeToolkit(api_key="sk_test_fake")
    fp_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "stripe_fetch_payment_intent")

    with respx.mock() as mock:
        mock.get("https://api.stripe.com/v1/payment_intents/pi_123").respond(
            200, json={
                "id": "pi_123",
                "status": "succeeded",
                "amount": 1000,
                "currency": "usd",
                "customer": "cus_x",
                "created": 1700000000,
            }
        )
        result = await fp_tool("pi_123")
    data = json.loads(result)
    assert data["status"] == "succeeded"
    assert data["amount"] == 1000


@pytest.mark.asyncio
async def test_stripe_create_refund():
    from largestack._integrations import StripeToolkit
    tk = StripeToolkit(api_key="sk_test")
    refund_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "stripe_create_refund")

    with respx.mock() as mock:
        mock.post("https://api.stripe.com/v1/refunds").respond(
            200, json={
                "id": "re_x", "amount": 500, "status": "succeeded", "charge": "ch_y",
            }
        )
        result = await refund_tool("ch_y", 500)
    data = json.loads(result)
    assert data["status"] == "succeeded"
    assert data["amount"] == 500


@pytest.mark.asyncio
async def test_stripe_list_charges():
    from largestack._integrations import StripeToolkit
    tk = StripeToolkit(api_key="sk_test")
    list_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "stripe_list_charges")
    with respx.mock() as mock:
        mock.get("https://api.stripe.com/v1/charges").respond(
            200, json={
                "data": [
                    {"id": "ch1", "amount": 100, "currency": "usd",
                     "status": "succeeded", "created": 1, "customer": "c1"}
                ],
                "has_more": False,
            }
        )
        result = await list_tool(5)
    data = json.loads(result)
    assert len(data["charges"]) == 1


# -------------------- TwilioToolkit --------------------

@pytest.mark.asyncio
async def test_twilio_no_creds(monkeypatch):
    for v in ["LARGESTACK_TWILIO_ACCOUNT_SID", "TWILIO_ACCOUNT_SID",
              "LARGESTACK_TWILIO_AUTH_TOKEN", "TWILIO_AUTH_TOKEN"]:
        monkeypatch.delenv(v, raising=False)
    from largestack._integrations import TwilioToolkit
    tk = TwilioToolkit()
    sms = next(t for t in tk.get_tools() if t._tool_schema["name"] == "twilio_send_sms")
    result = await sms("+15551234567", "hi")
    assert "TWILIO" in result


@pytest.mark.asyncio
async def test_twilio_send_sms_success():
    from largestack._integrations import TwilioToolkit
    tk = TwilioToolkit(account_sid="ACtest", auth_token="auth_test")
    sms = next(t for t in tk.get_tools() if t._tool_schema["name"] == "twilio_send_sms")
    with respx.mock() as mock:
        mock.post(
            "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
        ).respond(
            201, json={
                "sid": "SMabc", "status": "queued",
                "to": "+15551234567", "from": "+15550001234",
            }
        )
        result = await sms("+15551234567", "hello", "+15550001234")
    data = json.loads(result)
    assert data["sid"] == "SMabc"
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_twilio_whatsapp_adds_prefix():
    from largestack._integrations import TwilioToolkit
    tk = TwilioToolkit(account_sid="AC1", auth_token="t1")
    wa = next(t for t in tk.get_tools() if t._tool_schema["name"] == "twilio_send_whatsapp")
    with respx.mock() as mock:
        route = mock.post(
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Messages.json"
        ).respond(201, json={"sid": "x", "status": "ok", "to": "x", "from": "y"})
        await wa("+15551234567", "hi", "+15559876543")
    # Verify "whatsapp:" prefix was added
    sent = route.calls.last.request.content.decode()
    assert "whatsapp" in sent.lower()


# -------------------- GitHubFullToolkit --------------------

@pytest.mark.asyncio
async def test_github_full_list_prs():
    from largestack._integrations import GitHubFullToolkit
    tk = GitHubFullToolkit("owner", "repo", api_token="x")
    list_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "github_list_prs")
    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/owner/repo/pulls").respond(
            200, json=[
                {
                    "number": 42, "title": "Add feature", "state": "open",
                    "user": {"login": "alice"}, "created_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://github.com/owner/repo/pull/42",
                }
            ]
        )
        result = await list_tool()
    data = json.loads(result)
    assert data["prs"][0]["number"] == 42


@pytest.mark.asyncio
async def test_github_full_create_pr_no_token(monkeypatch):
    for v in ["LARGESTACK_GITHUB_TOKEN", "GITHUB_TOKEN"]:
        monkeypatch.delenv(v, raising=False)
    from largestack._integrations import GitHubFullToolkit
    tk = GitHubFullToolkit("o", "r")
    create = next(t for t in tk.get_tools() if t._tool_schema["name"] == "github_create_pr")
    result = await create("Title", "feature-branch")
    assert "LARGESTACK_GITHUB_TOKEN" in result


@pytest.mark.asyncio
async def test_github_full_get_file_decodes_base64():
    import base64 as _b64
    from largestack._integrations import GitHubFullToolkit
    tk = GitHubFullToolkit("o", "r", api_token="x")
    get_tool = next(t for t in tk.get_tools() if t._tool_schema["name"] == "github_get_file")
    with respx.mock() as mock:
        mock.get("https://api.github.com/repos/o/r/contents/README.md").respond(
            200, json={
                "path": "README.md", "size": 6, "sha": "abc",
                "encoding": "base64",
                "content": _b64.b64encode(b"# Hi\n").decode(),
            }
        )
        result = await get_tool("README.md")
    data = json.loads(result)
    assert "# Hi" in data["content"]


# -------------------- ConfluenceToolkit --------------------

@pytest.mark.asyncio
async def test_confluence_create_page_no_creds(monkeypatch):
    for v in ["LARGESTACK_CONFLUENCE_USER", "CONFLUENCE_USER",
              "LARGESTACK_CONFLUENCE_TOKEN", "CONFLUENCE_TOKEN"]:
        monkeypatch.delenv(v, raising=False)
    from largestack._integrations import ConfluenceToolkit
    tk = ConfluenceToolkit("https://x.atlassian.net/wiki")
    cr = next(t for t in tk.get_tools() if t._tool_schema["name"] == "confluence_create_page")
    result = await cr("SPC", "Title", "<p>x</p>")
    assert "creds required" in result


@pytest.mark.asyncio
async def test_confluence_create_page_success():
    from largestack._integrations import ConfluenceToolkit
    tk = ConfluenceToolkit(
        "https://x.atlassian.net/wiki",
        username="u@e.com", api_token="t",
    )
    cr = next(t for t in tk.get_tools() if t._tool_schema["name"] == "confluence_create_page")
    with respx.mock() as mock:
        mock.post("https://x.atlassian.net/wiki/rest/api/content").respond(
            200, json={
                "id": "12345", "title": "New Page",
                "_links": {"base": "https://x.atlassian.net/wiki", "webui": "/spaces/SPC/pages/12345"},
            }
        )
        result = await cr("SPC", "New Page", "<p>Content</p>")
    data = json.loads(result)
    assert data["id"] == "12345"
    assert data["title"] == "New Page"
