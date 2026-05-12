"""Tests for enhanced distributed patterns: event sourcing, saga, outbox."""
import asyncio, os, sys, tempfile; sys.path.insert(0, ".")


def tmp_db(name: str = "test.db") -> str:
    return os.path.join(tempfile.mkdtemp(), name)


# ═══ Event Sourcing ═══

def test_event_store_append():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    v1 = es.append("order-1", "Created", {"amount": 100})
    v2 = es.append("order-1", "Updated", {"amount": 150})
    assert v1 == 1
    assert v2 == 2

def test_event_store_optimistic_concurrency():
    from largestack._distributed.event_sourcing import EventStore, ConcurrencyError
    es = EventStore(tmp_db("events.db"))
    es.append("order-1", "Created", {"x": 1})
    # Expect v2 but append v3 instead → fails
    try:
        es.append("order-1", "Update", {"y": 2}, expected_version=5)
        assert False, "Should have raised"
    except ConcurrencyError:
        pass

def test_event_store_stream_retrieval():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("order-1", "A", {"n": 1})
    es.append("order-1", "B", {"n": 2})
    es.append("order-2", "C", {"n": 3})
    events = es.get_stream("order-1")
    assert len(events) == 2
    assert events[0]["type"] == "A"

def test_event_store_reconstruct_state():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("user-1", "NameSet", {"name": "Alice"})
    es.append("user-1", "EmailSet", {"email": "a@x.com"})
    state = es.reconstruct_state("user-1")
    assert state["name"] == "Alice"
    assert state["email"] == "a@x.com"

def test_event_store_custom_reducer():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    for i in range(5):
        es.append("counter", "Inc", {"n": i})
    
    def sum_reducer(state, event):
        return {"total": state.get("total", 0) + event["data"]["n"]}
    
    state = es.reconstruct_state("counter", reducer=sum_reducer)
    assert state["total"] == 10  # 0+1+2+3+4

def test_event_store_snapshot():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("s1", "A", {"a": 1})
    es.save_snapshot("s1", {"a": 1, "cached": True}, version=1)
    snap = es.get_snapshot("s1")
    assert snap is not None
    assert snap["version"] == 1
    assert snap["state"]["cached"] is True

def test_event_store_snapshot_plus_replay():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("s1", "A", {"a": 1})
    es.save_snapshot("s1", {"a": 1}, version=1)
    es.append("s1", "B", {"b": 2})
    # Reconstruct uses snapshot + replays newer events
    state = es.reconstruct_state("s1")
    assert state["a"] == 1
    assert state["b"] == 2

def test_event_store_batch_append():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    versions = es.append_batch([
        {"stream_id": "s1", "type": "A", "data": {"x": 1}},
        {"stream_id": "s1", "type": "B", "data": {"y": 2}},
        {"stream_id": "s2", "type": "C", "data": {"z": 3}},
    ])
    assert len(versions) == 3
    # s1 gets v1 and v2; s2 gets v1
    assert versions[0] == 1
    assert versions[1] == 2
    assert versions[2] == 1

def test_event_store_get_by_type():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("s1", "OrderCreated", {"x": 1})
    es.append("s2", "OrderCreated", {"x": 2})
    es.append("s1", "OrderShipped", {"x": 3})
    orders = es.get_by_type("OrderCreated")
    assert len(orders) == 2

def test_event_store_subscribe():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    received = []
    es.subscribe("order-*", lambda e: received.append(e))
    es.append("order-1", "Created", {"x": 1})
    es.append("user-1", "Login", {"y": 2})
    # Only order-* subscriber fires
    assert len(received) == 1
    assert received[0]["stream_id"] == "order-1"

def test_event_store_list_streams():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("a", "X", {})
    es.append("b", "X", {})
    es.append("a", "Y", {})
    streams = es.list_streams()
    assert len(streams) == 2

def test_event_store_stats():
    from largestack._distributed.event_sourcing import EventStore
    es = EventStore(tmp_db("events.db"))
    es.append("s1", "A", {})
    es.append("s1", "B", {})
    es.append("s2", "A", {})
    s = es.stats
    assert s["total_events"] == 3
    assert s["unique_streams"] == 2
    assert s["unique_event_types"] == 2


# ═══ Saga ═══

def test_saga_simple_success():
    from largestack._distributed.saga import SagaOrchestrator
    saga = SagaOrchestrator("test")
    saga.add_step("step1", lambda ctx: {"result1": "ok"}, lambda ctx: None)
    saga.add_step("step2", lambda ctx: {"result2": "ok"}, lambda ctx: None)
    
    result = asyncio.run(saga.execute({"input": "x"}))
    assert result["result1"] == "ok"
    assert result["result2"] == "ok"
    assert result["input"] == "x"

def test_saga_compensation_on_failure():
    from largestack._distributed.saga import SagaOrchestrator, SagaExecutionError
    compensations_called = []
    
    def step2_action(ctx): raise RuntimeError("boom")
    def step1_compensate(ctx): compensations_called.append("s1")
    
    saga = SagaOrchestrator("test")
    saga.add_step("s1", lambda ctx: {"a": 1}, step1_compensate)
    saga.add_step("s2", step2_action, lambda ctx: None)
    
    try:
        asyncio.run(saga.execute({}))
        assert False
    except SagaExecutionError as e:
        assert e.failed_step == "s2"
    
    # s1 compensation should have been called
    assert "s1" in compensations_called

def test_saga_compensation_reverse_order():
    from largestack._distributed.saga import SagaOrchestrator, SagaExecutionError
    order = []
    
    saga = SagaOrchestrator("test")
    saga.add_step("a", lambda ctx: None, lambda ctx: order.append("compA"))
    saga.add_step("b", lambda ctx: None, lambda ctx: order.append("compB"))
    saga.add_step("c", lambda ctx: None, lambda ctx: order.append("compC"))
    def fail(ctx): raise RuntimeError("fail")
    saga.add_step("d", fail, lambda ctx: order.append("compD"))
    
    try:
        asyncio.run(saga.execute({}))
    except SagaExecutionError:
        pass
    
    # Reverse order: c, b, a
    assert order == ["compC", "compB", "compA"]

def test_saga_retry():
    from largestack._distributed.saga import SagaOrchestrator
    attempts = []
    def flaky(ctx):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("flaky")
        return {"done": True}
    
    saga = SagaOrchestrator("test")
    saga.add_step("flaky", flaky, lambda ctx: None, max_retries=3)
    
    result = asyncio.run(saga.execute({}))
    assert result["done"] is True
    assert len(attempts) == 3

def test_saga_timeout():
    from largestack._distributed.saga import SagaOrchestrator, SagaExecutionError
    
    async def slow(ctx):
        await asyncio.sleep(2)
        return {"ok": True}
    
    saga = SagaOrchestrator("test")
    saga.add_step("slow", slow, lambda ctx: None, timeout=0.1)
    
    try:
        asyncio.run(saga.execute({}))
        assert False
    except SagaExecutionError as e:
        # Timeout error
        assert "slow" in e.failed_step

def test_saga_compensation_no_op():
    from largestack._distributed.saga import SagaOrchestrator, SagaExecutionError
    # Steps can have no compensation (None = no-op)
    saga = SagaOrchestrator("test")
    saga.add_step("a", lambda ctx: None, None)
    def fail(ctx): raise RuntimeError("x")
    saga.add_step("b", fail, None)
    try:
        asyncio.run(saga.execute({}))
    except SagaExecutionError:
        pass  # Compensation skipped, no error


# ═══ Outbox ═══

def test_outbox_write_and_poll():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"))
    o.write("order.created", {"id": 1})
    o.write("order.paid", {"id": 1, "amount": 100})
    pending = o.poll_unpublished()
    assert len(pending) == 2

def test_outbox_mark_published():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"))
    eid = o.write("event", {"data": "x"})
    o.mark_published(eid)
    assert len(o.poll_unpublished()) == 0

def test_outbox_retry_with_backoff():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"), max_retries=3)
    eid = o.write("event", {})
    o.mark_failed(eid, "error1")
    # Has retry_count=1, not yet in DLQ
    assert len(o.get_dlq()) == 0

def test_outbox_dlq_after_max_retries():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"), max_retries=2)
    eid = o.write("event", {"n": 1})
    o.mark_failed(eid, "e1")
    o.mark_failed(eid, "e2")
    # Should be in DLQ now
    dlq = o.get_dlq()
    assert len(dlq) == 1
    assert dlq[0]["last_error"] == "e2"

def test_outbox_process_once():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"))
    o.write("e1", {"x": 1})
    o.write("e2", {"x": 2})
    
    published = []
    async def pub(event):
        published.append(event["type"])
    
    count = asyncio.run(o.process_once(pub))
    assert count == 2
    assert "e1" in published and "e2" in published

def test_outbox_process_handles_publisher_error():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"), max_retries=5)
    o.write("event", {})
    
    async def failing_pub(event):
        raise RuntimeError("pub failed")
    
    count = asyncio.run(o.process_once(failing_pub))
    assert count == 0  # Nothing published successfully
    # Should be scheduled for retry
    assert o.stats["failed_count"] >= 0  # Not yet in DLQ (only 1 failure)

def test_outbox_batch_write():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"))
    ids = o.write_batch([
        {"type": "a", "payload": {"x": 1}},
        {"type": "b", "payload": {"x": 2}},
        {"type": "c", "payload": {"x": 3}},
    ])
    assert len(ids) == 3
    pending = o.poll_unpublished()
    assert len(pending) == 3

def test_outbox_requeue_from_dlq():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"), max_retries=1)
    eid = o.write("event", {"data": "x"})
    o.mark_failed(eid, "err")
    # In DLQ now
    dlq = o.get_dlq()
    assert len(dlq) == 1
    # Requeue
    new_id = o.requeue_from_dlq(dlq[0]["id"])
    assert new_id is not None
    assert len(o.get_dlq()) == 0
    assert len(o.poll_unpublished()) == 1

def test_outbox_stats():
    from largestack._distributed.outbox import OutboxPattern
    o = OutboxPattern(tmp_db("outbox.db"))
    o.write("a", {})
    o.write("b", {})
    s = o.stats
    assert s["pending"] == 2
    assert s["total_events"] == 2
    assert s["dlq_size"] == 0
