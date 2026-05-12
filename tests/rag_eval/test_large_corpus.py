from tests.rag_eval.helpers import build_large_corpus, retrieve


def test_large_corpus_keeps_relevant_doc_in_top_three():
    corpus = build_large_corpus(400)
    docs = retrieve("demand supply publish negative quantity", corpus, top_k=3)
    assert "dsd_validation.md" in {doc["id"] for doc in docs}
