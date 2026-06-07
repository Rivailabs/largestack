"""v1.1.1 onboarding UX: .env auto-load, standard-key fallback, `largestack setup`.

All offline, no network. Each pins one behavior so it can't silently regress.
"""
from __future__ import annotations

import os

from largestack._core.env import STANDARD_KEY_ENV, load_dotenv, resolve_provider_key


# ---- .env auto-load ----
def test_load_dotenv_sets_new_but_not_override(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# comment\n"
        "LS_TEST_NEW=fromfile\n"
        'export LS_TEST_QUOTED="quoted val"\n'
        "LS_TEST_EXISTING=fromfile\n"
        "blank line below\n\n"
    )
    monkeypatch.setenv("LS_TEST_EXISTING", "fromenv")  # already set → must NOT be overridden
    monkeypatch.delenv("LS_TEST_NEW", raising=False)
    monkeypatch.delenv("LS_TEST_QUOTED", raising=False)
    monkeypatch.delenv("LARGESTACK_NO_DOTENV", raising=False)

    n = load_dotenv(tmp_path / ".env")
    assert n >= 2
    assert os.environ["LS_TEST_NEW"] == "fromfile"
    assert os.environ["LS_TEST_QUOTED"] == "quoted val"  # quotes stripped
    assert os.environ["LS_TEST_EXISTING"] == "fromenv"  # real env wins
    for k in ("LS_TEST_NEW", "LS_TEST_QUOTED"):
        os.environ.pop(k, None)


def test_load_dotenv_disabled(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("LS_TEST_DISABLED=x\n")
    monkeypatch.setenv("LARGESTACK_NO_DOTENV", "1")
    monkeypatch.delenv("LS_TEST_DISABLED", raising=False)
    assert load_dotenv(tmp_path / ".env") == 0
    assert "LS_TEST_DISABLED" not in os.environ


def test_load_dotenv_missing_file_is_noop(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == 0


# ---- standard-key fallback ----
def test_resolve_largestack_prefix_wins(monkeypatch):
    monkeypatch.setenv("LARGESTACK_OPENAI_API_KEY", "ls-key")
    monkeypatch.setenv("OPENAI_API_KEY", "std-key")
    assert resolve_provider_key("openai") == "ls-key"


def test_resolve_falls_back_to_standard_name(monkeypatch):
    monkeypatch.delenv("LARGESTACK_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "std-key")
    assert resolve_provider_key("openai") == "std-key"


def test_resolve_gemini_alias(monkeypatch):
    monkeypatch.delenv("LARGESTACK_GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    assert resolve_provider_key("google") == "gem"


def test_resolve_empty_when_unset(monkeypatch):
    monkeypatch.delenv("LARGESTACK_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert resolve_provider_key("deepseek") == ""
    assert "openai" in STANDARD_KEY_ENV and "deepseek" in STANDARD_KEY_ENV


# ---- `largestack setup` (non-interactive) ----
def test_setup_writes_env_and_gitignore(tmp_path):
    from typer.testing import CliRunner

    from largestack._cli.main import app

    r = CliRunner().invoke(
        app,
        ["setup", "--provider", "deepseek", "--api-key", "sk-xyz",
         "--model", "deepseek/deepseek-chat", "--path", str(tmp_path), "--no-verify"],
    )
    assert r.exit_code == 0, r.output
    env_text = (tmp_path / ".env").read_text()
    assert "LARGESTACK_DEEPSEEK_API_KEY=sk-xyz" in env_text
    assert "LARGESTACK_DEFAULT_MODEL=deepseek/deepseek-chat" in env_text
    assert ".env" in (tmp_path / ".gitignore").read_text().split()


def test_setup_updates_in_place_preserves_other_lines(tmp_path):
    from typer.testing import CliRunner

    from largestack._cli.main import app

    (tmp_path / ".env").write_text("KEEP_ME=1\nLARGESTACK_DEEPSEEK_API_KEY=old\n")
    r = CliRunner().invoke(
        app,
        ["setup", "--provider", "deepseek", "--api-key", "new", "--path", str(tmp_path), "--no-verify"],
    )
    assert r.exit_code == 0, r.output
    txt = (tmp_path / ".env").read_text()
    assert "KEEP_ME=1" in txt
    assert "LARGESTACK_DEEPSEEK_API_KEY=new" in txt
    assert "LARGESTACK_DEEPSEEK_API_KEY=old" not in txt


def test_setup_ollama_needs_no_key(tmp_path):
    from typer.testing import CliRunner

    from largestack._cli.main import app

    r = CliRunner().invoke(
        app, ["setup", "--provider", "ollama", "--path", str(tmp_path), "--no-verify"]
    )
    assert r.exit_code == 0, r.output
    txt = (tmp_path / ".env").read_text()
    assert "LARGESTACK_ENABLE_OLLAMA=1" in txt and "LARGESTACK_DEFAULT_MODEL=ollama/llama3.2" in txt


def test_setup_unknown_provider_errors(tmp_path):
    from typer.testing import CliRunner

    from largestack._cli.main import app

    r = CliRunner().invoke(
        app, ["setup", "--provider", "nope", "--api-key", "x", "--path", str(tmp_path), "--no-verify"]
    )
    assert r.exit_code != 0


def test_setup_noninteractive_requires_key(tmp_path):
    from typer.testing import CliRunner

    from largestack._cli.main import app

    r = CliRunner().invoke(
        app, ["setup", "--provider", "openai", "--path", str(tmp_path), "--no-verify"]
    )
    assert r.exit_code != 0  # key required when non-interactive
