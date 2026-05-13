from ml_automation import detect_task, baseline


def test_detect_task_regression():
    rows = [{'x': str(i), 'y': str(i*2)} for i in range(10)]
    assert detect_task(rows, 'y') == 'regression'


def test_detect_task_classification():
    rows = [{'x': i, 'label': 'yes' if i > 5 else 'no'} for i in range(10)]
    assert detect_task(rows, 'label') == 'classification'


def test_baseline_regression():
    rows = [{'x': str(i), 'y': str(i*2)} for i in range(10)]
    result = baseline(rows, 'y')
    assert result['task'] == 'regression'
    assert 'mae' in result


def test_baseline_classification():
    rows = [{'x': i, 'label': 'yes' if i > 5 else 'no'} for i in range(10)]
    result = baseline(rows, 'label')
    assert result['task'] == 'classification'
    assert 'accuracy' in result


def test_public_contract():
    reg = [{'x': str(i), 'y': str(i*2)} for i in range(10)]
    cls = [{'x': i, 'label': 'yes' if i > 5 else 'no'} for i in range(10)]
    assert detect_task(reg, 'y') == 'regression' and 'mae' in baseline(reg, 'y')
    assert baseline(cls, 'label')['task'] == 'classification'
