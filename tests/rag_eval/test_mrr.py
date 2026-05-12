from tests.rag_eval.helpers import load_questions, mean_reciprocal_rank


def test_rag_eval_mrr_meets_release_gate():
    assert mean_reciprocal_rank(load_questions()) >= 0.9
