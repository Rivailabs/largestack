from tests.rag_eval.helpers import answer_with_citation, load_questions


def test_answers_include_expected_citations():
    for case in load_questions():
        assert case["citation"] in answer_with_citation(case["query"])
