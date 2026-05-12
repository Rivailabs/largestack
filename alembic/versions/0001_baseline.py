"""baseline schema — matches Database.run_migrations() output

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-30

This baseline matches the schema produced by `MIGRATIONS["001_core_tables"]`
in largestack/_core/database.py exactly. After this is applied, switch all
schema evolution to Alembic and stop modifying MIGRATIONS dict.

Tables created:
  - largestack_traces       (PRIMARY KEY trace_id)
  - largestack_audit_log    (autoincrement id; portable INTEGER PK)
  - largestack_licenses     (PRIMARY KEY id; UNIQUE key)
  - largestack_usage        (autoincrement id)
  - largestack_migrations   (tracking — applied via run_migrations() too)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name  # "sqlite", "postgresql", "mysql", ...

    # ─── largestack_traces ──────────────────────────────────────
    op.create_table(
        "largestack_traces",
        sa.Column("trace_id", sa.Text(), primary_key=True),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="completed"),
        sa.Column("total_cost", sa.Float(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("duration_ms", sa.Float(), server_default="0"),
        sa.Column("turns", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_largestack_traces_agent_name", "largestack_traces", ["agent_name"])
    op.create_index("ix_largestack_traces_created_at", "largestack_traces", ["created_at"])

    # ─── largestack_audit_log ───────────────────────────────────
    # Portable autoincrement primary key (SQLite uses INTEGER PRIMARY KEY,
    # Postgres uses BIGSERIAL via Identity()).
    op.create_table(
        "largestack_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("cost", sa.Float(), server_default="0"),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.Text(), nullable=True),
        sa.Column("entry_hash", sa.Text(), nullable=True),
    )
    op.create_index("ix_largestack_audit_log_timestamp", "largestack_audit_log", ["timestamp"])
    op.create_index("ix_largestack_audit_log_event_type", "largestack_audit_log", ["event_type"])
    op.create_index("ix_largestack_audit_log_user_id", "largestack_audit_log", ["user_id"])

    # ─── largestack_licenses ────────────────────────────────────
    op.create_table(
        "largestack_licenses",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active"),
        sa.Column("max_agents", sa.Integer(), server_default="3"),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("payment_provider", sa.Text(), nullable=True),
        sa.Column("payment_id", sa.Text(), nullable=True),
    )

    # ─── largestack_usage ───────────────────────────────────────
    op.create_table(
        "largestack_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0"),
        sa.Column("output_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost", sa.Float(), server_default="0"),
        sa.Column("timestamp", sa.Float(), nullable=False),
    )
    op.create_index("ix_largestack_usage_user_id", "largestack_usage", ["user_id"])
    op.create_index("ix_largestack_usage_tenant_id", "largestack_usage", ["tenant_id"])
    op.create_index("ix_largestack_usage_timestamp", "largestack_usage", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_largestack_usage_timestamp", table_name="largestack_usage")
    op.drop_index("ix_largestack_usage_tenant_id", table_name="largestack_usage")
    op.drop_index("ix_largestack_usage_user_id", table_name="largestack_usage")
    op.drop_table("largestack_usage")
    op.drop_table("largestack_licenses")
    op.drop_index("ix_largestack_audit_log_user_id", table_name="largestack_audit_log")
    op.drop_index("ix_largestack_audit_log_event_type", table_name="largestack_audit_log")
    op.drop_index("ix_largestack_audit_log_timestamp", table_name="largestack_audit_log")
    op.drop_table("largestack_audit_log")
    op.drop_index("ix_largestack_traces_created_at", table_name="largestack_traces")
    op.drop_index("ix_largestack_traces_agent_name", table_name="largestack_traces")
    op.drop_table("largestack_traces")
