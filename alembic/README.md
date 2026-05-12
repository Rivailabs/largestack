# LARGESTACK Alembic Migrations

## Quick start

```bash
# Set DB URL (or LARGESTACK_POSTGRES_DSN as alias):
export LARGESTACK_DATABASE_URL=postgresql://largestack:pwd@host:5432/largestack

# Apply all migrations:
alembic upgrade head

# Roll back one:
alembic downgrade -1

# Create a new migration (handwritten — review before applying):
alembic revision -m "add_user_table"
# edit alembic/versions/<rev>_add_user_table.py
alembic upgrade head
```

## Why both Alembic and `Database.run_migrations()`?

LARGESTACK originally shipped with `Database.run_migrations()` (in `largestack/_core/database.py`)
which executes SQL DDL strings from `MIGRATIONS` dict. That is preserved for
backward compatibility — existing deployments can keep using it. **All NEW
schema changes must go through Alembic.**

The baseline migration `0001_baseline.py` mirrors `MIGRATIONS["001_core_tables"]`
exactly, so a fresh deployment using `alembic upgrade head` produces the same
schema as the legacy path. Operators upgrading from v0.3.5 should run:

```bash
# Mark the baseline as already applied (do NOT re-execute the DDL on existing data):
alembic stamp 0001_baseline

# Then future migrations apply normally:
alembic upgrade head
```

## Schema notes

- `largestack_audit_log.id` and `largestack_usage.id` use portable `Integer + autoincrement=True`.
  On SQLite this becomes `INTEGER PRIMARY KEY`; on Postgres, `BIGSERIAL`.
- `largestack_audit_log` is append-only with a hash chain (`prev_hash` → `entry_hash`) for
  tamper detection. Do NOT add UPDATE migrations against this table.
- All timestamps are `REAL` (Unix epoch seconds, float) for cross-DB consistency.
