import csv
import os

_opportunities = []

def add_opportunity(name, amount, stage, probability, close_quarter, owner):
    _opportunities.append({
        'name': name,
        'amount': amount,
        'stage': stage,
        'probability': probability,
        'close_quarter': close_quarter,
        'owner': owner
    })

def forecast_quarter(quarter, target):
    weighted_pipeline = 0.0
    commit_pipeline = 0.0
    for opp in _opportunities:
        if opp['close_quarter'] == quarter:
            weighted_pipeline += opp['amount'] * opp['probability']
            if opp['stage'] == 'commit':
                commit_pipeline += opp['amount']
    coverage_ratio = weighted_pipeline / target if target > 0 else 0.0
    return {
        'weighted_pipeline': weighted_pipeline,
        'commit_pipeline': commit_pipeline,
        'coverage_ratio': coverage_ratio,
        'target': target
    }

def explain_pipeline_risk(forecast):
    risks = []
    if forecast['coverage_ratio'] < 3.0:
        risks.append(f"Coverage ratio {forecast['coverage_ratio']:.2f}x is below 3x target. Increase pipeline.")
    return {
        'risks': risks,
        'coverage_ratio': forecast['coverage_ratio']
    }

def load_opportunities_from_csv(filepath):
    if not os.path.exists(filepath):
        return
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_opportunity(
                name=row['name'],
                amount=float(row['amount']),
                stage=row['stage'],
                probability=float(row['probability']),
                close_quarter=row['close_quarter'],
                owner=row['owner']
            )

def clear_opportunities():
    _opportunities.clear()
