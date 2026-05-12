from tests.rag_eval.helpers import retrieve


def test_tenant_filter_prevents_cross_tenant_policy_retrieval():
    docs = retrieve("Tenant A supplier onboarding docs", top_k=5, tenant_id="tenant-b")
    assert "tenant_a_policy.md" not in {doc["id"] for doc in docs}
