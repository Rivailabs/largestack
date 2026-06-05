"""Offline tests for Enterprise Jarvis (no API key needed).

Run: cd enterprise_jarvis && python -m pytest test_ejarvis.py -q
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EJARVIS_DATA_DIR", "/tmp/ejarvis_test_data")

import shutil  # noqa: E402

shutil.rmtree("/tmp/ejarvis_test_data", ignore_errors=True)

from largestack.testing import FunctionModel  # noqa: E402

from ejarvis import knowledge, rbac, store  # noqa: E402
from ejarvis.agent import EnterpriseJarvis, EnterpriseReply, safe_calc  # noqa: E402
from ejarvis.context import Principal  # noqa: E402
from ejarvis.schemas import TicketTriage  # noqa: E402


# ---- RBAC ------------------------------------------------------------------

def test_rbac_viewer_cannot_raise_ticket():
    assert not rbac.can("viewer", "raise_ticket")
    assert rbac.can("agent", "raise_ticket")


def test_rbac_only_admin_reads_audit():
    assert rbac.can("admin", "read_audit")
    assert not rbac.can("agent", "read_audit")
    assert not rbac.can("viewer", "read_audit")


# ---- Bounded calculator ----------------------------------------------------

def test_calc_basic():
    assert safe_calc("23 * 19 + 7") == "444"


def test_calc_refuses_pow_dos():
    assert "Error" in safe_calc("9**9**9")


# ---- Store: tenant isolation + persistence + audit -------------------------

def test_tenant_isolation():
    store.set_fact("acme", "deadline", "June 20")
    store.set_fact("globex", "deadline", "July 5")
    assert store.get_fact("acme", "deadline") == "June 20"
    assert store.get_fact("globex", "deadline") == "July 5"


def test_approval_persists():
    rid = store.add_approval("acme", "carol", "delete logs", "risky")
    items = store.get_approvals("acme")
    assert any(a["id"] == rid and a["status"] == "pending" for a in items)


def test_audit_appends_and_reads():
    store.audit("acme", "alice", "admin", "kb_search", "leave policy")
    rows = store.read_audit("acme", limit=5)
    assert rows and rows[-1]["event"] == "kb_search"


# ---- Knowledge / RAG -------------------------------------------------------

def test_knowledge_finds_leave_policy_with_citation():
    hits = knowledge.search("how many annual leave days")
    assert hits
    assert any("hr_leave_policy.md" == src for src, _ in hits)


def test_knowledge_insufficient_evidence():
    assert knowledge.search("zzzzqqq nonsense token") == []


# ---- Agent wiring (offline via FunctionModel) ------------------------------

def test_ask_returns_typed_reply_offline():
    jarvis = EnterpriseJarvis(Principal("alice", "admin", "acme"))
    with jarvis.agent.override(model=FunctionModel(lambda m, i: {"content": "Hello from Jarvis"})):
        out = asyncio.run(jarvis.ask("hi"))
    assert isinstance(out, EnterpriseReply)
    assert out.reply == "Hello from Jarvis"


def test_triage_returns_validated_model_offline():
    jarvis = EnterpriseJarvis(Principal("alice", "admin", "acme"))
    payload = '{"category": "it", "priority": "high", "summary": "laptop dead", "needs_approval": false}'
    with jarvis._triage.override(model=FunctionModel(lambda m, i: {"content": payload})):
        t = asyncio.run(jarvis.triage("laptop won't boot"))
    assert isinstance(t, TicketTriage)
    assert t.category == "it" and t.priority == "high"
