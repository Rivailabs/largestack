def detect_task(rows, target):
    """Detect whether the target column indicates regression or classification.
    Numeric targets with more than two unique values -> regression.
    Otherwise -> classification.
    """
    values = [row[target] for row in rows]
    # Try to convert all values to float; if any fails, treat as classification
    numeric_values = []
    for v in values:
        try:
            numeric_values.append(float(v))
        except (ValueError, TypeError):
            return 'classification'
    unique = set(numeric_values)
    if len(unique) > 2:
        return 'regression'
    else:
        return 'classification'


def baseline(rows, target):
    """Compute a baseline metric for the given task.
    For regression: mean absolute error (MAE) using the mean prediction.
    For classification: accuracy using the majority class.
    Returns a dict with keys 'task' and either 'mae' or 'accuracy'.
    """
    task = detect_task(rows, target)
    values = [row[target] for row in rows]
    if task == 'regression':
        numeric_values = [float(v) for v in values]
        mean_val = sum(numeric_values) / len(numeric_values)
        mae = sum(abs(v - mean_val) for v in numeric_values) / len(numeric_values)
        return {'task': 'regression', 'mae': mae}
    else:
        # classification: majority class accuracy
        from collections import Counter
        counter = Counter(values)
        majority_count = counter.most_common(1)[0][1]
        accuracy = majority_count / len(values)
        return {'task': 'classification', 'accuracy': accuracy}
