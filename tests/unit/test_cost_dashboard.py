import sys; sys.path.insert(0, ".")

def test_cost_monitor_records():
    from largestack._observe.cost_dashboard import CostMonitor
    m = CostMonitor()
    m.record(0.01, agent="bot1", model="gpt-4o")
    m.record(0.02, agent="bot1", model="gpt-4o")
    m.record(0.03, agent="bot2", model="claude")
    assert m.total == 0.06
    assert m.by_agent["bot1"] == 0.03
    
def test_cost_monitor_alert():
    from largestack._observe.cost_dashboard import CostMonitor
    m = CostMonitor()
    m.record(0.50)
    assert not m.alert_if_over(1.0)
    m.record(0.60)
    assert m.alert_if_over(1.0)

def test_cost_monitor_report():
    from largestack._observe.cost_dashboard import CostMonitor
    m = CostMonitor()
    m.record(0.10, agent="a")
    r = m.report()
    assert "total" in r
    assert "top_agents" in r
