import sqlite3
import json
from datetime import datetime

class JarvisCore:
    def __init__(self, db_path=':memory:'):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute('CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, timestamp TEXT)')
        self.conn.commit()

    def remember(self, key, value):
        self.conn.execute('REPLACE INTO memory (key, value) VALUES (?, ?)', (key, json.dumps(value)))
        self.conn.commit()

    def recall(self, key):
        cursor = self.conn.execute('SELECT value FROM memory WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def plan_day(self, tasks):
        timestamp = datetime.now().isoformat()
        plans = []
        for task in tasks:
            self.conn.execute('INSERT INTO plans (task, timestamp) VALUES (?, ?)', (task, timestamp))
            plans.append({'task': task, 'timestamp': timestamp})
        self.conn.commit()
        return plans

    def decide_action(self, action, params):
        risky_actions = ['delete_file', 'send_email', 'shutdown']
        if action in risky_actions:
            return {'action': action, 'params': params, 'executed': False, 'reason': 'requires approval'}
        return {'action': action, 'params': params, 'executed': True}
