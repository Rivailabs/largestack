import sys
sys.path.insert(0, '.')
from sales_forecast import add_opportunity, forecast_quarter, explain_pipeline_risk, clear_opportunities

def setup_function():
    clear_opportunities()

def test_forecast_and_risk():
    add_opportunity('O1', amount=100000, stage='proposal', probability=0.5, close_quarter='2026Q2', owner='A')
    add_opportunity('O2', amount=50000, stage='commit', probability=0.9, close_quarter='2026Q2', owner='A')
    forecast = forecast_quarter('2026Q2', target=100000)
    assert abs(forecast['weighted_pipeline'] - 95000) < 0.01, f"weighted_pipeline {forecast['weighted_pipeline']}"
    assert forecast['commit_pipeline'] == 50000, f"commit_pipeline {forecast['commit_pipeline']}"
    risk = explain_pipeline_risk(forecast)
    assert isinstance(risk['risks'], list), "risks should be a list"
    assert 'coverage_ratio' in risk, "coverage_ratio missing"
    assert risk['coverage_ratio'] == 0.95, f"coverage_ratio {risk['coverage_ratio']}"
    assert len(risk['risks']) > 0, "should have risk because coverage < 3x"

def test_no_risk_when_coverage_high():
    add_opportunity('O3', amount=500000, stage='commit', probability=1.0, close_quarter='2026Q3', owner='B')
    forecast = forecast_quarter('2026Q3', target=100000)
    risk = explain_pipeline_risk(forecast)
    assert risk['coverage_ratio'] == 5.0
    assert len(risk['risks']) == 0
