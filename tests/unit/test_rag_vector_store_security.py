import pytest

from largestack._rag.vector_store import PgVectorStore, _validate_identifier


def test_validate_identifier_accepts_safe_names():
    assert _validate_identifier("largestack_vectors") == "largestack_vectors"


@pytest.mark.parametrize(
    "bad",
    [
        "bad-name",
        "bad name",
        "vectors; DROP TABLE users;",
        "1bad",
        "",
    ],
)
def test_validate_identifier_rejects_unsafe_names(bad):
    with pytest.raises(ValueError):
        _validate_identifier(bad)


def test_pgvector_store_rejects_unsafe_table_name():
    with pytest.raises(ValueError):
        PgVectorStore("postgresql://example", table="vectors;DROP TABLE users")


def test_pgvector_store_accepts_safe_table_name():
    store = PgVectorStore("postgresql://example", table="largestack_vectors")
    assert store.table == "largestack_vectors"
