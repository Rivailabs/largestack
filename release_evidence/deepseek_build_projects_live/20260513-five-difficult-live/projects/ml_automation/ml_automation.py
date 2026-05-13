import statistics

def detect_task(rows, target):
    if not rows:
        return 'classification'
    values = []
    for row in rows:
        val = row[target]
        if isinstance(val, str):
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except ValueError:
                pass
        values.append(val)
    all_numeric = all(isinstance(v, (int, float)) for v in values)
    if all_numeric:
        unique = set(values)
        if len(unique) > 2:
            return 'regression'
        else:
            return 'classification'
    else:
        return 'classification'

def baseline(rows, target):
    if not rows:
        return {'task': 'classification', 'accuracy': 0.0, 'majority_class_rate': 0.0}
    values = []
    for row in rows:
        val = row[target]
        if isinstance(val, str):
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except ValueError:
                pass
        values.append(val)
    all_numeric = all(isinstance(v, (int, float)) for v in values)
    if all_numeric:
        unique = set(values)
        if len(unique) > 2:
            task = 'regression'
        else:
            task = 'classification'
    else:
        task = 'classification'
    
    if task == 'classification':
        from collections import Counter
        counter = Counter(values)
        majority_class, majority_count = counter.most_common(1)[0]
        accuracy = majority_count / len(values)
        majority_class_rate = majority_count / len(values)
        return {'task': 'classification', 'accuracy': accuracy, 'majority_class_rate': majority_class_rate}
    else:
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n % 2 == 1:
            baseline_prediction = sorted_vals[n // 2]
        else:
            baseline_prediction = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        mae = sum(abs(v - baseline_prediction) for v in values) / n
        return {'task': 'regression', 'mae': mae, 'baseline_prediction': baseline_prediction}
