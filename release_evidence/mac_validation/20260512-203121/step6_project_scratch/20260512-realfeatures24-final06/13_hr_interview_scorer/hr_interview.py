import re

def generate_questions(role: str) -> list:
    """Generate interview questions for a given role."""
    questions = {
        'QA engineer': [
            'How do you design test cases for a new feature?',
            'Describe your experience with automated testing frameworks.',
            'How do you handle a production bug that was missed in testing?'
        ],
        'software engineer': [
            'Explain the difference between a list and a tuple in Python.',
            'How do you approach debugging a complex issue?',
            'Describe a time you optimized a slow algorithm.'
        ],
        'data scientist': [
            'How do you handle missing data in a dataset?',
            'Explain overfitting and how to prevent it.',
            'Describe a project where you used machine learning to solve a business problem.'
        ]
    }
    return questions.get(role, ['What makes you a good fit for this role?'])

def score_answer(answer: str) -> dict:
    """Score an interview answer and return a result with fairness warning and recommendation."""
    # Simple scoring based on keyword presence
    keywords = ['test', 'automation', 'quality', 'api', 'improvement']
    score = sum(1 for word in keywords if word in answer.lower())
    
    # Fairness warning: always True as per requirement
    fairness_warning = True
    
    # Recommendation: next round if score >= 2, else no next round
    if score >= 2:
        recommendation = 'Next round: Proceed to technical interview.'
    else:
        recommendation = 'Next round: Consider additional screening.'
    
    return {
        'score': score,
        'fairness_warning': fairness_warning,
        'recommendation': recommendation
    }