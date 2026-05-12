import uuid
from collections import defaultdict

_runs = []

def record_run(agent_name: str, status: str, *, cost: float = 0.0, tokens: int = 0, trace_id: str = None):
    if trace_id is None:
        trace_id = str(uuid.uuid4())
    _runs.append({
        'agent_name': agent_name,
        'status': status,
        'cost': cost,
        'tokens': tokens,
        'trace_id': trace_id
    })

def list_runs():
    return list(_runs)

def metrics():
    total = len(_runs)
    total_cost = sum(r['cost'] for r in _runs)
    total_tokens = sum(r['tokens'] for r in _runs)
    status_counts = defaultdict(int)
    for r in _runs:
        status_counts[r['status']] += 1
    return {
        'runs_total': total,
        'total_cost': total_cost,
        'total_tokens': total_tokens,
        'status_counts': dict(status_counts)
    }

def mermaid_graph(agents: list):
    lines = ['graph TD']
    for i, agent in enumerate(agents):
        lines.append(f'    {agent}[{agent}]')
    if len(agents) > 1:
        for i in range(len(agents) - 1):
            lines.append(f'    {agents[i]} --> {agents[i+1]}')
    return '\n'.join(lines)
