import pytest

from largestack._vectorstores import (
    DuckDBVectorStore,
    PgVectorStore,
    _validate_metadata_key,
    _validate_vector_dim,
)


def test_validate_metadata_key_accepts_safe_key():
    assert _validate_metadata_key("tenant_id") == "tenant_id"


@pytest.mark.parametrize("bad", ["bad-key", "bad key", "x'); DROP TABLE t; --", "1bad", ""])
def test_validate_metadata_key_rejects_unsafe_key(bad):
    with pytest.raises(ValueError):
        _validate_metadata_key(bad)


@pytest.mark.parametrize("bad", [0, -1, 100001, "1536"])
def test_validate_vector_dim_rejects_invalid_dim(bad):
    with pytest.raises(ValueError):
        _validate_vector_dim(bad)


def test_pgvector_rejects_unsafe_table_name():
    with pytest.raises(ValueError):
        PgVectorStore("postgres://example", "vectors;DROP TABLE users")


def test_duckdb_rejects_unsafe_table_name(tmp_path):
    with pytest.raises(ValueError):
        DuckDBVectorStore(str(tmp_path / "v.duckdb"), "vectors;DROP TABLE users")


def test_pgvector_rejects_invalid_dim():
    with pytest.raises(ValueError):
        PgVectorStore("postgres://example", "vectors", dim=0)


def test_duckdb_rejects_invalid_dim(tmp_path):
    with pytest.raises(ValueError):
        DuckDBVectorStore(str(tmp_path / "v.duckdb"), "vectors", dim=0)
