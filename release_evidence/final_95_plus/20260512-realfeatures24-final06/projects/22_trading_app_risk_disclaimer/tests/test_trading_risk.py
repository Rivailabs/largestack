import pytest
from trading_risk import evaluate_signal, risk_disclaimer, place_order_decision

def test_risk_disclaimer():
    disclaimer = risk_disclaimer()
    assert 'not financial advice' in disclaimer.lower()

def test_evaluate_signal():
    result = evaluate_signal({'rsi': 20})
    assert result['signal'] in {'buy_watch', 'hold', 'sell_watch'}

def test_place_order_decision(monkeypatch):
    monkeypatch.setattr('builtins.input', lambda _: 'no')
    result = place_order_decision({'symbol': 'ABC'})
    assert result['executed'] is False
