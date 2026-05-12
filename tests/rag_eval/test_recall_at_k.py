from tests.rag_eval.helpers import load_questions, recall_at_k


def test_rag_eval_recall_at_3_meets_release_gate():
    assert recall_at_k(load_questions(), k=3) == 1.0
