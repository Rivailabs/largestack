import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml_automation import detect_task, baseline

def test_detect_task_classification_labels():
    rows = [{'target': 'cat'}, {'target': 'dog'}, {'target': 'cat'}]
    assert detect_task(rows, 'target') == 'classification'

def test_detect_task_classification_numeric_binary():
    rows = [{'target': 0}, {'target': 1}, {'target': 0}]
    assert detect_task(rows, 'target') == 'classification'

def test_detect_task_regression_numeric_many():
    rows = [{'target': 1.0}, {'target': 2.5}, {'target': 3.2}]
    assert detect_task(rows, 'target') == 'regression'

def test_detect_task_numeric_strings():
    rows = [{'target': '1.5'}, {'target': '2.0'}, {'target': '3.7'}]
    assert detect_task(rows, 'target') == 'regression'

def test_detect_task_mixed_non_numeric():
    rows = [{'target': 'a'}, {'target': 'b'}, {'target': 'c'}]
    assert detect_task(rows, 'target') == 'classification'

def test_baseline_classification():
    rows = [{'target': 'a'}, {'target': 'b'}, {'target': 'a'}]
    result = baseline(rows, 'target')
    assert result['task'] == 'classification'
    assert result['accuracy'] == 2/3
    assert result['majority_class_rate'] == 2/3

def test_baseline_regression():
    rows = [{'target': 1.0}, {'target': 2.0}, {'target': 3.0}]
    result = baseline(rows, 'target')
    assert result['task'] == 'regression'
    assert result['mae'] == 2/3
    assert result['baseline_prediction'] == 2.0

def test_baseline_single_row_regression():
    rows = [{'target': 5.0}]
    result = baseline(rows, 'target')
    # Single numeric value: only 1 unique value, so task is classification
    assert result['task'] == 'classification'
    assert result['accuracy'] == 1.0
    assert result['majority_class_rate'] == 1.0

def test_baseline_single_row_classification():
    rows = [{'target': 'x'}]
    result = baseline(rows, 'target')
    assert result['task'] == 'classification'
    assert result['accuracy'] == 1.0
    assert result['majority_class_rate'] == 1.0

def test_baseline_empty_rows():
    result = baseline([], 'target')
    assert result['task'] == 'classification'
    assert result['accuracy'] == 0.0
    assert result['majority_class_rate'] == 0.0

def test_baseline_numeric_strings_regression():
    rows = [{'target': '1.5'}, {'target': '2.0'}, {'target': '3.5'}]
    result = baseline(rows, 'target')
    assert result['task'] == 'regression'
    assert result['mae'] == (abs(1.5-2.0)+abs(2.0-2.0)+abs(3.5-2.0))/3
    assert result['baseline_prediction'] == 2.0

def test_baseline_single_numeric_string():
    rows = [{'target': '5.0'}]
    result = baseline(rows, 'target')
    # Single numeric string: only 1 unique value, so task is classification
    assert result['task'] == 'classification'
    assert result['accuracy'] == 1.0
    assert result['majority_class_rate'] == 1.0

def test_baseline_two_numeric_regression():
    rows = [{'target': 1.0}, {'target': 2.0}]
    result = baseline(rows, 'target')
    # Two unique values: not >2, so classification
    assert result['task'] == 'classification'
    assert result['accuracy'] == 0.5
    assert result['majority_class_rate'] == 0.5

def test_baseline_two_numeric_strings_classification():
    rows = [{'target': '1.0'}, {'target': '2.0'}]
    result = baseline(rows, 'target')
    assert result['task'] == 'classification'
    assert result['accuracy'] == 0.5
    assert result['majority_class_rate'] == 0.5
