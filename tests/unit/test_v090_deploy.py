"""v0.9.0: Tests for Docker Compose stack files."""

from __future__ import annotations

from pathlib import Path

import pytest


DEPLOY_DIR = Path(__file__).parent.parent.parent / "deploy"


def test_docker_compose_yaml_present():
    assert (DEPLOY_DIR / "docker-compose.yml").exists()


def test_docker_compose_has_required_services():
    pytest.importorskip("yaml")
    import yaml as _yaml

    with open(DEPLOY_DIR / "docker-compose.yml") as f:
        data = _yaml.safe_load(f)
    services = set(data.get("services", {}).keys())
    expected = {"largestack", "redis", "postgres", "qdrant", "prometheus", "grafana"}
    assert expected.issubset(services), f"Missing: {expected - services}"


def test_dockerfile_present():
    assert (DEPLOY_DIR / "Dockerfile").exists()


def test_dockerfile_uses_multistage_and_nonroot():
    df = (DEPLOY_DIR / "Dockerfile").read_text()
    # Multi-stage
    assert df.count("FROM ") >= 2
    # Non-root user
    assert "USER largestack" in df
    # Pinned base image
    assert "python:3.12-slim" in df


def test_init_db_sql_has_pgvector():
    sql = (DEPLOY_DIR / "init-db.sql").read_text()
    assert "CREATE EXTENSION" in sql
    assert "vector" in sql.lower()
    # Has documents table for vector store
    assert "documents" in sql
    # Has audit log
    assert "audit_log" in sql
    # Has tenants
    assert "tenants" in sql


def test_prometheus_config_scrapes_largestack():
    config = (DEPLOY_DIR / "prometheus.yml").read_text()
    assert "largestack:8000" in config
    assert "/metrics" in config


def test_env_example_has_openai_placeholder():
    env = (DEPLOY_DIR / ".env.example").read_text()
    assert "OPENAI_API_KEY" in env


def test_deploy_readme_exists():
    readme = DEPLOY_DIR / "README.md"
    assert readme.exists()
    content = readme.read_text()
    assert "docker compose" in content.lower()
    assert "production" in content.lower()
