import re
from collections import defaultdict

def cluster_feedback(items):
    clusters = {}
    for item in items:
        text = item['text'].lower()
        arr = item['arr']
        # Determine theme based on keywords
        if 'sso' in text or 'single sign-on' in text:
            theme = 'sso'
        elif 'dark mode' in text or 'dark_mode' in text:
            theme = 'dark_mode'
        else:
            theme = 'other'
        if theme not in clusters:
            clusters[theme] = {'count': 0, 'arr': 0, 'sentiment': 0.0, 'items': []}
        clusters[theme]['count'] += 1
        clusters[theme]['arr'] += arr
        # Simple sentiment: positive if contains 'please' or 'need', else neutral
        if 'please' in text or 'need' in text:
            sentiment = 0.5
        elif 'confusing' in text or 'hard' in text:
            sentiment = -0.5
        else:
            sentiment = 0.0
        clusters[theme]['sentiment'] = (clusters[theme]['sentiment'] * (clusters[theme]['count'] - 1) + sentiment) / clusters[theme]['count']
        clusters[theme]['items'].append(item)
    return clusters

def roadmap_signals(clusters):
    signals = []
    for theme, data in clusters.items():
        if data['count'] >= 2 and data['arr'] >= 50000:
            priority = 'critical' if data['arr'] >= 100000 else 'high'
        else:
            priority = 'medium'
        signals.append({
            'theme': theme,
            'count': data['count'],
            'arr': data['arr'],
            'sentiment': data['sentiment'],
            'priority': priority,
            'evidence': f"{data['count']} feedback items, ${data['arr']} ARR, sentiment {data['sentiment']:.2f}"
        })
    signals.sort(key=lambda x: x['arr'], reverse=True)
    return signals
