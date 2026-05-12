"""Alembic environment for LARGESTACK Agentic AI.

Reads DB URL from LARGESTACK_DATABASE_URL or LARGESTACK_POSTGRES_DSN env vars.
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve database URL from env at runtime
db_url = (
    os.environ.get("LARGESTACK_DATABASE_URL")
    or os.environ.get("LARGESTACK_POSTGRES_DSN")
    or "sqlite:///./largestack_alembic.db"
)
config.set_main_option("sqlalchemy.url", db_url)

# Alembic auto-generation requires SQLAlchemy metadata. LARGESTACK uses raw SQL
# DDL via Database.run_migrations(), so we don't have a single MetaData
# object. Auto-generate is therefore informational only — operators should
# write migrations by hand and review carefully.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL without a DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
