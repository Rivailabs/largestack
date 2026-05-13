import sqlite3
import json

class JarvisCore:
    def __init__(self, db_path=':memory:'):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute('CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)')
        self.conn.commit()

    def remember(self, key, value):
        serialized = json.dumps(value)
        self.conn.execute('REPLACE INTO memory (key, value) VALUES (?, ?)', (key, serialized))
        self.conn.commit()

    def recall(self, key):
        cursor = self.conn.execute('SELECT value FROM memory WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def plan_day(self, tasks):
        result = []
        for task in tasks:
            result.append({'task': task})
        return result

    def decide_action(self, action, payload):
        risky_actions = ['send_email', 'move_file', 'delete_file', 'publish_social', 'refund_payment', 'write_production']
        if action in risky_actions:
            return {'decision': 'require_approval', 'executed': False}
        return {'decision': 'approved', 'executed': True}
