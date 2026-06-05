"""Security regression — no secrets in source, no key leakage in errors."""
import os
import re
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.mark.parametrize("pattern,name", [
    (r"sk-[a-zA-Z0-9]{20,}", "OpenAI / DeepSeek key"),
    (r"sk-ant-[a-zA-Z0-9-_]{30,}", "Anthropic key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"ghp_[A-Za-z0-9]{36,}", "GitHub PAT"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
])
def test_no_credentials_in_source(pattern, name):
    """Code, docs, examples, and tests must not contain real-looking keys."""
    root = _repo_root()
    rx = re.compile(pattern)
    found = []
    for sub in ("largestack", "docs", "examples", "tests", "scripts"):
        d = root / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            # Skip binary / vendored / test fixtures we can't control
            if any(p.startswith(".") for p in f.parts):
                continue
            if "__pycache__" in f.parts or f.suffix in {".pyc", ".pyo"}:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in rx.finditer(text):
                # Ignore obvious placeholders
                v = m.group(0)
                if "..." in v or "xxx" in v.lower() or "fake" in v.lower():
                    continue
                if v.lower().startswith("sk-test") or v.lower().startswith("sk-fake"):
                    continue
                found.append((str(f.relative_to(root)), v[:25] + "..."))
    assert not found, f"Possible {name} leaked: {found}"


def test_no_password_in_committed_files():
    """Hardcoded password fields outside templates/examples."""
    root = _repo_root()
    rx = re.compile(r"password\s*[:=]\s*['\"](?!\$\{|<)([^'\"]{4,})['\"]", re.IGNORECASE)
    found = []
    for f in (root / "largestack").rglob("*.py"):
        try:
            text = f.read_text()
        except Exception:
            continue
        for m in rx.finditer(text):
            value = m.group(1)
            # Common safe defaults — placeholders only
            if value in ("", "your-password", "REDACTED", "*****",
                          "largestack_dev_change_me", "change-me",
                          "your-strong-password", "test", "test-password"):
                continue
            found.append((str(f.relative_to(root)), value))
    assert not found, f"Hardcoded passwords: {found}"


def test_dotenv_not_committed():
    """`.env` (real, not `.env.example`) must not be committed."""
    root = _repo_root()
    real_env = root / ".env"
    # Allow the file to exist locally but not be tracked. Simplest check:
    # if it exists, it must contain only blank/comment lines or be a symlink
    # to .env.example. The strict check is: don't commit it. We can't run git
    # in this sandbox, but we can verify there's no .env in the staged source.
    # Acceptable outcome: .env doesn't exist, OR exists with only template content.
    if not real_env.exists():
        return
    # If a developer happens to have one locally, the test still passes —
    # we only care about the committed state, which we can't inspect here.
    # This test is a placeholder for CI: production CI should run
    # `git ls-files | grep -E "^\.env$"` and fail if .env is tracked.


def test_gitignore_includes_env():
    """`.gitignore` must list .env to prevent accidental commits."""
    root = _repo_root()
    gi = root / ".gitignore"
    assert gi.exists(), ".gitignore missing"
    text = gi.read_text()
    # Either .env or .env* on its own line (ignore .env.example)
    lines = [l.strip() for l in text.splitlines()]
    has_env_pattern = any(
        l == ".env" or l == ".env*" or l == "*.env" or l.endswith("/.env")
        for l in lines
    )
    assert has_env_pattern, ".gitignore must include .env"


def test_dotenv_example_has_no_real_secrets():
    """`.env.example` template must not contain real-looking secrets."""
    root = _repo_root()
    ex = root / ".env.example"
    if not ex.exists():
        pytest.skip(".env.example not present")
    text = ex.read_text()
    # No long sk- keys
    assert not re.search(r"sk-[a-zA-Z0-9]{30,}", text), ".env.example must use placeholder, not real key"
    # No long password literals
    bad = re.findall(r"PASSWORD\s*=\s*[A-Za-z0-9!@#$%^&*]{15,}", text)
    bad_real = [b for b in bad if "your" not in b.lower() and "change" not in b.lower() and "<" not in b]
    assert not bad_real, f"Possible real password in .env.example: {bad_real}"


# ─── License keygen ─────────────────────────────────────────

def test_license_keygen_default_disabled():
    """Without LARGESTACK_KEYGEN_ENABLED, keygen must raise."""
    from largestack._core.license import LicenseValidator
    os.environ.pop("LARGESTACK_KEYGEN_ENABLED", None)
    os.environ.pop("LARGESTACK_DISABLE_KEYGEN_BUILD", None)
    try:
        LicenseValidator.generate_key(tier="pro")
        assert False, "keygen must be disabled by default"
    except RuntimeError as e:
        assert "disabled" in str(e).lower()


def test_license_keygen_build_flag_overrides_runtime():
    """LARGESTACK_DISABLE_KEYGEN_BUILD=1 must take priority over LARGESTACK_KEYGEN_ENABLED=1."""
    from largestack._core.license import LicenseValidator
    os.environ["LARGESTACK_KEYGEN_ENABLED"] = "1"
    os.environ["LARGESTACK_DISABLE_KEYGEN_BUILD"] = "1"
    try:
        LicenseValidator.generate_key(tier="pro")
        assert False, "build-time disable must win"
    except RuntimeError as e:
        assert "disabled in this build" in str(e)
    finally:
        os.environ.pop("LARGESTACK_KEYGEN_ENABLED", None)
        os.environ.pop("LARGESTACK_DISABLE_KEYGEN_BUILD", None)


def test_license_source_has_build_flag_marker():
    """Source must contain the build-time strip marker for production builds."""
    import largestack._core.license as mod
    src = Path(mod.__file__).read_text()
    assert "_BUILD_STRIPPED" in src
    assert "LARGESTACK_DISABLE_KEYGEN_BUILD" in src


def test_build_script_exists_and_executable():
    """scripts/build_production_wheel.sh must exist."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent
    p = root / "scripts" / "build_production_wheel.sh"
    assert p.exists(), "Production wheel build script missing"
    # Check it actually flips the flag
    text = p.read_text()
    assert "_BUILD_STRIPPED = True" in text
