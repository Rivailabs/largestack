import random

def evaluate_signal(data: dict) -> dict:
    rsi = data.get('rsi', 50)
    if rsi < 30:
        signal = 'buy_watch'
    elif rsi > 70:
        signal = 'sell_watch'
    else:
        signal = 'hold'
    return {'signal': signal}

def risk_disclaimer() -> str:
    return "This is not financial advice. Trading involves risk."

def place_order_decision(order: dict) -> dict:
    symbol = order.get('symbol', '')
    print(f"Risk warning: Trading {symbol} involves substantial risk of loss.")
    try:
        approval = input("Do you approve this order? (yes/no): ").strip().lower()
    except EOFError:
        approval = 'no'
    if approval == 'yes':
        return {'executed': True, 'symbol': symbol}
    else:
        return {'executed': False, 'symbol': symbol}
