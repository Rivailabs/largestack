import pytest
from expense_tracker import add_expense, list_expenses, monthly_summary, flag_policy_violations, clear_expenses


@pytest.fixture(autouse=True)
def reset_expenses():
    clear_expenses()
    yield


def test_add_expense():
    e = add_expense('2026-05-01', 'travel', 250, 'card')
    assert e['date'] == '2026-05-01'
    assert e['category'] == 'travel'
    assert e['amount'] == 250
    assert e['payment_method'] == 'card'


def test_add_expense_positive_amount():
    with pytest.raises(ValueError):
        add_expense('2026-05-01', 'travel', -10, 'card')


def test_list_expenses():
    add_expense('2026-05-01', 'travel', 250, 'card')
    add_expense('2026-05-02', 'food', 100, 'cash')
    expenses = list_expenses()
    assert len(expenses) == 2


def test_monthly_summary():
    add_expense('2026-05-01', 'travel', 250, 'card')
    add_expense('2026-05-02', 'food', 100, 'cash')
    summary = monthly_summary('2026-05')
    assert summary['total'] == 350
    assert summary['count'] == 2


def test_monthly_summary_empty():
    summary = monthly_summary('2026-06')
    assert summary['total'] == 0
    assert summary['count'] == 0


def test_flag_policy_violations():
    expenses = [
        {'date': '2026-05-01', 'category': 'travel', 'amount': 250, 'payment_method': 'card'},
        {'date': '2026-05-02', 'category': 'gift', 'amount': 600, 'payment_method': 'cash'},
        {'date': '2026-05-03', 'category': 'cash', 'amount': 700, 'payment_method': 'cash'},
        {'date': '2026-05-04', 'category': 'gift', 'amount': 400, 'payment_method': 'cash'},
    ]
    violations = flag_policy_violations(expenses)
    assert len(violations) == 2
    assert violations[0]['category'] == 'gift'
    assert violations[1]['category'] == 'cash'


def test_public_contract():
    from expense_tracker import add_expense, monthly_summary, flag_policy_violations
    e = add_expense('2026-05-01', 'travel', 250, 'card')
    assert monthly_summary('2026-05')['total'] == 250
    assert flag_policy_violations([add_expense('2026-05-02', 'gift', 600, 'cash')])
