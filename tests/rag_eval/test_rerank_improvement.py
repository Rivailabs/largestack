from tests.rag_eval.helpers import retrieve


def test_rerank_does_not_degrade_relevant_top_result():
    baseline = retrieve("quote plan margin tax customer credit", top_k=1, rerank=False)[0]
    reranked = retrieve("quote plan margin tax customer credit", top_k=1, rerank=True)[0]
    assert baseline["id"] == "qp_plan_rules.md"
    assert reranked["id"] == "qp_plan_rules.md"
    assert reranked["score"] >= baseline["score"]
