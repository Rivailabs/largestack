"""Pandas Toolkit (v0.9.0) — DataFrame analysis tools.

Provides tools for an agent to interact with a pandas DataFrame:
- ``info`` — shape, dtypes, nulls
- ``head`` — first N rows
- ``query`` — run pandas .query() expression (safe subset)
- ``aggregate`` — groupby + agg
- ``describe`` — statistics

Auto-rejects code-execution-style queries (no ``eval`` / ``exec``).

Usage:
    import pandas as pd
    df = pd.read_csv("sales.csv")
    toolkit = PandasToolkit(df)
    agent = Agent(name="analyst", llm="...", tools=toolkit.get_tools())
"""

from __future__ import annotations
import json
import logging
from typing import Any, Callable

from largestack._core.tools import tool

log = logging.getLogger("largestack.pandas_toolkit")


class PandasToolkit:
    """Toolkit for analyzing a pandas DataFrame.

    Args:
        df: pandas DataFrame.
        max_rows: cap on rows returned per call.
        max_cell_chars: truncate large cells.
    """

    def __init__(
        self,
        df: Any,
        *,
        max_rows: int = 100,
        max_cell_chars: int = 500,
    ):
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("PandasToolkit needs: pip install pandas") from e
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"df must be a pandas.DataFrame, got {type(df)}")
        self._pd = pd
        self.df = df
        self.max_rows = max_rows
        self.max_cell_chars = max_cell_chars
        self._tools: list[Callable] = self._build_tools()

    def _to_records(self, frame) -> list[dict]:
        """Convert subset of DataFrame to JSON-serializable list of dicts."""
        out = []
        for _, row in frame.head(self.max_rows).iterrows():
            d = {}
            for k, v in row.items():
                s = str(v) if not self._pd.isna(v) else None
                if isinstance(s, str) and len(s) > self.max_cell_chars:
                    s = s[: self.max_cell_chars] + "...[truncated]"
                d[str(k)] = s
            out.append(d)
        return out

    def _build_tools(self) -> list[Callable]:
        toolkit = self

        @tool(name="dataframe_info", description="Show shape, columns, dtypes, null counts")
        async def df_info() -> str:
            df = toolkit.df
            return json.dumps(
                {
                    "shape": list(df.shape),
                    "columns": [str(c) for c in df.columns],
                    "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
                    "null_counts": {str(c): int(df[c].isna().sum()) for c in df.columns},
                    "memory_bytes": int(df.memory_usage(deep=True).sum()),
                }
            )

        @tool(name="dataframe_head", description="Show first N rows of the DataFrame")
        async def df_head(n: int = 10) -> str:
            n = min(int(n), toolkit.max_rows)
            return json.dumps(
                {
                    "rows": toolkit._to_records(toolkit.df.head(n)),
                    "n": n,
                }
            )

        @tool(
            name="dataframe_describe",
            description="Show summary statistics (count, mean, std, min, max, percentiles)",
        )
        async def df_describe(include: str = "number") -> str:
            try:
                if include == "all":
                    desc = toolkit.df.describe(include="all")
                elif include == "object":
                    desc = toolkit.df.describe(include=["object"])
                else:
                    desc = toolkit.df.describe()
                return desc.to_json()
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="dataframe_query",
            description=(
                "Run a pandas .query() expression on the DataFrame. "
                "Examples: 'age > 30', 'name == \"Alice\"', "
                "'price > 100 and category == \"electronics\"'. "
                "Returns matching rows."
            ),
        )
        async def df_query(expression: str) -> str:
            try:
                result = toolkit.df.query(expression)
                return json.dumps(
                    {
                        "rows": toolkit._to_records(result),
                        "matched_count": len(result),
                        "truncated": len(result) > toolkit.max_rows,
                    }
                )
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="dataframe_aggregate",
            description=(
                "Group by column(s) and aggregate. "
                "group_by: comma-separated column names. "
                "agg_col: column to aggregate. "
                "agg_func: one of sum, mean, count, min, max, median, std."
            ),
        )
        async def df_aggregate(group_by: str, agg_col: str, agg_func: str = "sum") -> str:
            allowed = {"sum", "mean", "count", "min", "max", "median", "std", "var"}
            if agg_func not in allowed:
                return f"error: agg_func must be one of {sorted(allowed)}"
            try:
                cols = [c.strip() for c in group_by.split(",") if c.strip()]
                grouped = toolkit.df.groupby(cols)[agg_col]
                result = getattr(grouped, agg_func)()
                # Convert to list of dicts
                df_out = result.reset_index()
                return json.dumps(
                    {
                        "group_by": cols,
                        "agg_col": agg_col,
                        "agg_func": agg_func,
                        "rows": toolkit._to_records(df_out),
                    }
                )
            except Exception as e:
                return f"error: {e}"

        return [df_info, df_head, df_describe, df_query, df_aggregate]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)
