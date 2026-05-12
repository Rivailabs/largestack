import pytest
from workflow_dashboard import record_run, metrics, mermaid_graph, list_runs

@pytest.fixture(autouse=True)
def clear_runs():
    import workflow_dashboard
    workflow_dashboard._runs.clear()
    yield

def test_record_run_and_metrics():
    record_run('agent-a', 'completed', cost=0.1, tokens=20, trace_id='t1')
    m = metrics()
    assert m['runs_total'] == 1
    assert m['total_cost'] == 0.1
    assert m['total_tokens'] == 20
    assert m['status_counts'] == {'completed': 1}

def test_mermaid_graph():
    graph = mermaid_graph(['agent-a', 'agent-b'])
    assert 'graph TD' in graph
    assert 'agent-a[agent-a]' in graph
    assert 'agent-b[agent-b]' in graph
    assert 'agent-a --> agent-b' in graph

def test_list_runs():
    record_run('agent-a', 'completed', cost=0.1, tokens=20, trace_id='t1')
    runs = list_runs()
    assert len(runs) == 1
    assert runs[0]['agent_name'] == 'agent-a'
    assert runs[0]['status'] == 'completed'
    assert runs[0]['cost'] == 0.1
    assert runs[0]['tokens'] == 20
    assert runs[0]['trace_id'] == 't1'
