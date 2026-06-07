"""SQL Toolkit (v0.9.0) — universal database access.

Provides 4 core tools for any SQL database:
- ``list_tables`` — enumerate tables/views
- ``describe_table`` — show schema for a table
- ``query`` — execute a SELECT and return results
- ``explain`` — show query plan

Supports any SQLAlchemy-compatible URL (Postgres, MySQL, SQLite,
SQL Server, Oracle, etc.) with read-only safety checks.

Usage:
    toolkit = SQLToolkit("postgresql://user:pw@host/db")
    agent = Agent(name="dba", llm="...", tools=toolkit.get_tools())
"""

from __future__ import annotations
import asyncio
import json
import logging
import re
from typing import Any, Callable

from largestack._core.tools import tool

log = logging.getLogger("largestack.sql_toolkit")


# Patterns that indicate write/DDL operations — disallowed in read-only mode
_DANGEROUS_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|"
    r"COMMIT|ROLLBACK|BEGIN|EXEC|EXECUTE|MERGE|REPLACE)\b",
    re.IGNORECASE,
)


class SQLToolkit:
    """Toolkit for SQL database operations.

    Args:
        connection_url: SQLAlchemy connection URL.
        read_only: if True (default), reject INSERT/UPDATE/DELETE/DDL.
        max_rows: cap on rows returned per query (default 100).
        max_cell_chars: truncate large cells (default 1000).
        engine_kwargs: passed to ``sqlalchemy.create_engine``.
    """

    def __init__(
        self,
        connection_url: str,
        *,
        read_only: bool = True,
        max_rows: int = 100,
        max_cell_chars: int = 1000,
        engine_kwargs: dict | None = None,
    ):
        self.connection_url = connection_url
        self.read_only = read_only
        self.max_rows = max_rows
        self.max_cell_chars = max_cell_chars
        self.engine_kwargs = engine_kwargs or {}
        self._engine = None
        self._dialect = ""
        self._tools: list[Callable] = self._build_tools()

    def _connect(self):
        if self._engine is not None:
            return
        try:
            from sqlalchemy import create_engine
        except ImportError as e:
            raise ImportError("SQLToolkit needs: pip install 'sqlalchemy>=2.0'") from e
        self._engine = create_engine(self.connection_url, **self.engine_kwargs)
        self._dialect = self._engine.dialect.name

    def _check_safety(self, sql: str) -> str | None:
        """Return error string if SQL is unsafe, else None."""
        if self.read_only and _DANGEROUS_SQL.search(sql):
            return "rejected: read-only mode disallows write/DDL"
        # Block multi-statement (basic)
        if sql.count(";") > 1:
            return "rejected: multi-statement queries not allowed"
        return None

    def _build_tools(self) -> list[Callable]:
        toolkit = self

        @tool(name="list_tables", description="List all tables in the database")
        async def list_tables() -> str:
            try:
                return await asyncio.to_thread(toolkit._list_tables_sync)
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="describe_table",
            description="Return schema for a table: columns, types, indexes",
        )
        async def describe_table(table_name: str) -> str:
            try:
                return await asyncio.to_thread(toolkit._describe_sync, table_name)
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="query",
            description=(
                "Run a read-only SELECT and return results as JSON. "
                "Multi-statement queries are blocked. Capped to "
                f"{toolkit.max_rows} rows."
            ),
            timeout=30,
        )
        async def query(sql: str) -> str:
            err = toolkit._check_safety(sql)
            if err:
                return err
            try:
                return await asyncio.to_thread(toolkit._query_sync, sql)
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="explain",
            description="Return query execution plan via EXPLAIN",
        )
        async def explain(sql: str) -> str:
            err = toolkit._check_safety(sql)
            if err:
                return err
            try:
                return await asyncio.to_thread(toolkit._explain_sync, sql)
            except Exception as e:
                return f"error: {e}"

        return [list_tables, describe_table, query, explain]

    def _list_tables_sync(self) -> str:
        from sqlalchemy import inspect

        self._connect()
        insp = inspect(self._engine)
        tables = insp.get_table_names()
        views = insp.get_view_names() if hasattr(insp, "get_view_names") else []
        return json.dumps(
            {
                "dialect": self._dialect,
                "tables": tables,
                "views": views,
            }
        )

    def _describe_sync(self, table_name: str) -> str:
        from sqlalchemy import inspect

        self._connect()
        insp = inspect(self._engine)
        try:
            cols = insp.get_columns(table_name)
            indexes = insp.get_indexes(table_name)
            pk = insp.get_pk_constraint(table_name)
        except Exception as e:
            return f"error: table {table_name!r} not found: {e}"
        return json.dumps(
            {
                "table": table_name,
                "columns": [
                    {
                        "name": c.get("name"),
                        "type": str(c.get("type")),
                        "nullable": c.get("nullable", True),
                        "default": str(c.get("default")) if c.get("default") is not None else None,
                    }
                    for c in cols
                ],
                "indexes": [
                    {"name": i.get("name"), "columns": list(i.get("column_names") or [])}
                    for i in indexes
                ],
                "primary_key": list(pk.get("constrained_columns") or []),
            }
        )

    def _query_sync(self, sql: str) -> str:
        from sqlalchemy import text

        self._connect()
        with self._engine.connect() as conn:
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = []
            for i, row in enumerate(result):
                if i >= self.max_rows:
                    break
                cell_dict = {}
                for k, v in zip(cols, row):
                    s = str(v) if v is not None else None
                    if isinstance(s, str) and len(s) > self.max_cell_chars:
                        s = s[: self.max_cell_chars] + "...[truncated]"
                    cell_dict[k] = s
                rows.append(cell_dict)
        return json.dumps(
            {
                "columns": cols,
                "rows": rows,
                "row_count": len(rows),
                "truncated": len(rows) >= self.max_rows,
            }
        )

    def _explain_sync(self, sql: str) -> str:
        from sqlalchemy import text

        self._connect()
        # Different dialects use different EXPLAIN syntax
        if self._dialect == "postgresql":
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
        elif self._dialect == "mysql":
            explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
        elif self._dialect == "sqlite":
            explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        else:
            explain_sql = f"EXPLAIN {sql}"
        with self._engine.connect() as conn:
            result = conn.execute(text(explain_sql))
            rows = [dict(zip(result.keys(), row)) for row in result]
        return json.dumps({"dialect": self._dialect, "plan": rows}, default=str)

    def get_tools(self) -> list[Callable]:
        return list(self._tools)
