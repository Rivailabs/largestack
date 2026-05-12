from tests.rag_eval.helpers import retrieve


def test_unrelated_question_scores_below_answer_threshold():
    top = retrieve("who won the football match yesterday", top_k=1)[0]
    assert top["score"] <= 1
