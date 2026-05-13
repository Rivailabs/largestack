from hr_interview import generate_questions, score_answer

def test_generate_questions_returns_at_least_three():
    questions = generate_questions('QA engineer')
    assert len(questions) >= 3

def test_score_answer_fairness_warning_true():
    result = score_answer('I tested APIs and improved automation quality')
    assert result['fairness_warning'] is True

def test_score_answer_recommendation_contains_next_round():
    result = score_answer('I tested APIs and improved automation quality')
    assert 'next round' in result['recommendation'].lower()

def test_score_answer_recommendation_no_final_hire():
    result = score_answer('I tested APIs and improved automation quality')
    assert 'final hire' not in result['recommendation'].lower()

def test_generate_questions_default_role():
    questions = generate_questions('unknown role')
    assert len(questions) >= 1
    assert 'good fit' in questions[0].lower()