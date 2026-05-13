import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from customer_health import compute_health_score, generate_playbook


def test_public_contract():
    """Test the exact public usage contract from requirements."""
    account = {
        'usage_percent': 35,
        'open_p1_tickets': 2,
        'nps': 4,
        'renewal_days': 45,
        'executive_sponsor': False
    }
    health = compute_health_score(account)
    assert 0 <= health['score'] <= 100, f"Score out of range: {health['score']}"
    assert health['risk_level'] == 'high', f"Expected high, got {health['risk_level']}"
    plan = generate_playbook(account, health)
    assert plan['owner_actions'], f"Expected non-empty actions, got {plan['owner_actions']}"
    assert plan['approval_required'] is False, f"Expected False, got {plan['approval_required']}"


def test_healthy_account():
    """Test a healthy account with perfect signals."""
    account = {
        'usage_percent': 95,
        'open_p1_tickets': 0,
        'nps': 10,
        'renewal_days': 200,
        'executive_sponsor': True
    }
    health = compute_health_score(account)
    assert health['score'] >= 85, f"Expected low risk, got {health['risk_level']}"
    assert health['risk_level'] == 'low', f"Expected low, got {health['risk_level']}"
    plan = generate_playbook(account, health)
    assert plan['owner_actions'] == [], f"Expected empty actions, got {plan['owner_actions']}"
    assert plan['approval_required'] is False, f"Expected False, got {plan['approval_required']}"


def test_missing_sponsor():
    """Test account missing executive sponsor."""
    account = {
        'usage_percent': 85,
        'open_p1_tickets': 0,
        'nps': 8,
        'renewal_days': 100,
        'executive_sponsor': False
    }
    health = compute_health_score(account)
    assert health['score'] < 100, "Score should not be perfect due to missing sponsor"
    plan = generate_playbook(account, health)
    assert any('executive sponsor' in action.lower() for action in plan['owner_actions']), \
        f"Expected executive sponsor action, got {plan['owner_actions']}"


def test_low_usage():
    """Test account with low usage."""
    account = {
        'usage_percent': 40,
        'open_p1_tickets': 0,
        'nps': 9,
        'renewal_days': 200,
        'executive_sponsor': True
    }
    health = compute_health_score(account)
    assert health['score'] < 100, "Score should not be perfect due to low usage"
    plan = generate_playbook(account, health)
    assert any('usage' in action.lower() for action in plan['owner_actions']), \
        f"Expected usage action, got {plan['owner_actions']}"


def test_near_renewal():
    """Test account with near renewal."""
    account = {
        'usage_percent': 90,
        'open_p1_tickets': 0,
        'nps': 9,
        'renewal_days': 30,
        'executive_sponsor': True
    }
    health = compute_health_score(account)
    assert health['score'] < 100, "Score should not be perfect due to near renewal"
    plan = generate_playbook(account, health)
    assert any('renewal' in action.lower() for action in plan['owner_actions']), \
        f"Expected renewal action, got {plan['owner_actions']}"
