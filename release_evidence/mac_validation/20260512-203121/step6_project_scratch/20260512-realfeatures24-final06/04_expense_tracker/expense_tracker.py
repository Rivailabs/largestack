import csv
import os
from datetime import datetime
from typing import List, Dict, Optional

_expenses: List[Dict] = []


def add_expense(date: str, category: str, amount: float, payment_method: str) -> Dict:
    if amount <= 0:
        raise ValueError("Amount must be positive")
    expense = {
        "date": date,
        "category": category,
        "amount": amount,
        "payment_method": payment_method
    }
    _expenses.append(expense)
    return expense


def list_expenses() -> List[Dict]:
    return list(_expenses)


def monthly_summary(year_month: str) -> Dict:
    total = 0.0
    count = 0
    for exp in _expenses:
        if exp["date"].startswith(year_month):
            total += exp["amount"]
            count += 1
    return {"total": total, "count": count}


def flag_policy_violations(expenses: List[Dict]) -> List[Dict]:
    violations = []
    for exp in expenses:
        if exp["category"] in ("cash", "gift") and exp["amount"] > 500:
            violations.append(exp)
    return violations


def clear_expenses():
    _expenses.clear()
