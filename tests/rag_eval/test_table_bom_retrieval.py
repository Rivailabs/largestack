from tests.rag_eval.helpers import retrieve


def test_bom_table_question_retrieves_rta_bom_rules_first():
    docs = retrieve("BOM alternates table lifecycle active supplier risk", top_k=1)
    assert docs[0]["id"] == "rta_bom_rules.md"
