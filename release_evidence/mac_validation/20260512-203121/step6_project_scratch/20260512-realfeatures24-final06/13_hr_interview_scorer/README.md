# HR Interview Scorer

A Python project for HR interview scoring with question generation and answer scoring.

## Features

- `generate_questions(role)`: Returns a list of interview questions for a given role.
- `score_answer(answer)`: Scores an interview answer and returns a dict with `score`, `fairness_warning`, and `recommendation`.

## Usage

```python
from hr_interview import generate_questions, score_answer

questions = generate_questions('QA engineer')
print(questions)

result = score_answer('I tested APIs and improved automation quality')
print(result)
```

## Running Tests

Install pytest and run:

```bash
pytest tests/
```

## LARGESTACK Integration

`largestack_app.py` contains an async smoke test that uses LARGESTACK features with overridden models to avoid network calls.

Run the smoke test:

```bash
python largestack_app.py
```

## Project Structure

```
hr_interview_scorer/
├── hr_interview.py
├── largestack_app.py
├── README.md
├── data/
│   └── policy.txt
├── policies/
│   └── refund_policy.txt
└── tests/
    ├── test_hr_interview.py
    └── test_largestack_features.py
```