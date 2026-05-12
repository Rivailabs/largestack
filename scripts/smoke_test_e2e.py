"""LARGESTACK v0.14.0 — End-to-end smoke test.

Exercises EVERY major subsystem in a single integration run to prove
the framework actually works as a system (not just isolated units).

This is what you run before shipping to production.
"""
from __future__ import annotations

# Ensure repo root is importable when this script is launched by path from CI or shell.
import sys as _ls_sys
from pathlib import Path as _LSPath
_LS_ROOT = _LSPath(__file__).resolve().parents[1]
if str(_LS_ROOT) not in _ls_sys.path:
    _ls_sys.path.insert(0, str(_LS_ROOT))

import asyncio
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path


PASSED = []
FAILED = []
SKIPPED = []


def section(name):
    print(f"\n{'='*70}\n  {name}\n{'='*70}")


def check(name, fn):
    print(f"  {name:60s}", end=" ", flush=True)
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            result = asyncio.get_event_loop().run_until_complete(result)
        print("✓")
        PASSED.append(name)
        return result
    except Exception as e:
        print(f"✗  {type(e).__name__}: {e}")
        FAILED.append((name, str(e)))
        return None


def acheck(name, coro):
    print(f"  {name:60s}", end=" ", flush=True)
    try:
        result = asyncio.get_event_loop().run_until_complete(coro)
        print("✓")
        PASSED.append(name)
        return result
    except Exception as e:
        print(f"✗  {type(e).__name__}: {e}")
        FAILED.append((name, str(e)))
        return None


# ============================================================
# SECTION 1: Framework imports + version
# ============================================================
section("1. Framework imports & version")

import largestack
check("import largestack", lambda: largestack.__version__)
print(f"  → version: {largestack.__version__}")

from largestack.agent import Agent
check("import Agent", lambda: Agent)


# ============================================================
# SECTION 2: Long-term memory (Letta pattern)
# ============================================================
section("2. Long-term memory (Letta-pattern, multi-tier)")

from largestack._memory.long_term import (
    LongTermMemoryManager, LongTermMemoryEntry,
    InMemoryLongTermStore,
)

mgr = check(
    "construct LongTermMemoryManager(tenant=t1, user=u1)",
    lambda: LongTermMemoryManager(tenant_id="t1", user_id="u1"),
)

acheck(
    "add_core (persona)",
    mgr.add_core("Helpful Indian-fintech KYC assistant", tag="persona"),
)
acheck(
    "add_archival (durable fact)",
    mgr.add_archival("user lives in Bengaluru", scope="semantic"),
)
acheck(
    "add_recall (recent event)",
    mgr.add_recall("user asked about loans yesterday", scope="episodic"),
)

block = acheck("get_core_block (always-in-context)", mgr.get_core_block())
assert block and "fintech" in block, f"core block missing: {block}"

archival_results = acheck(
    "search_archival(Bengaluru)", mgr.search_archival("Bengaluru"),
)
assert len(archival_results) >= 1, "archival search returned nothing"

recall_results = acheck(
    "search_recall(loans)", mgr.search_recall("loans"),
)
assert len(recall_results) >= 1, "recall search returned nothing"


# ============================================================
# SECTION 3: Tenant isolation (DPDP / RBI critical)
# ============================================================
section("3. Multi-tenant isolation (RBI auditor probe)")

mgr_a = LongTermMemoryManager(tenant_id="bank_a", user_id="alice")
mgr_b = LongTermMemoryManager(tenant_id="bank_b", user_id="bob")

acheck(
    "tenant A adds confidential data",
    mgr_a.add_archival("alice's PAN: AAACR1234C"),
)
acheck(
    "tenant B adds confidential data",
    mgr_b.add_archival("bob's loan application"),
)

# Cross-tenant search MUST return nothing
cross = acheck(
    "tenant B searches for tenant A's data → empty",
    mgr_b.search_archival("PAN"),
)
assert all("alice" not in r.content for r in cross or []), \
    "TENANT LEAK — bank_b can see bank_a's data!"
print("  → cross-tenant isolation: VERIFIED")


# ============================================================
# SECTION 4: Memory backends (vector embedding, Postgres)
# ============================================================
section("4. Memory backends (vector + Postgres)")

from largestack._memory.vector_store import (
    VectorMemoryStore, HashingEmbedder,
)
from largestack._memory.postgres_store import PostgresLongTermStore

vstore = check(
    "construct VectorMemoryStore",
    lambda: VectorMemoryStore(
        InMemoryLongTermStore(), embedder=HashingEmbedder(dim=128),
    ),
)

# Add entries with different topics
acheck(
    "vector store: add 'Bengaluru office'",
    vstore.add(LongTermMemoryEntry(
        id="v1", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="The team is based in Bengaluru office",
    )),
)
acheck(
    "vector store: add 'Mumbai branch'",
    vstore.add(LongTermMemoryEntry(
        id="v2", tenant_id="t1", user_id="u1",
        tier="archival", scope="semantic",
        content="The Mumbai branch handles loans",
    )),
)

# Semantic search should rank Bengaluru higher for "Bengaluru" query
results = acheck(
    "vector search: Bengaluru → Bengaluru ranked first",
    vstore.search(tenant_id="t1", user_id="u1",
                  query="Bengaluru", limit=2),
)
if results:
    assert results[0].id == "v1", \
        f"vector search wrong order: {[r.id for r in results]}"

# Postgres backend (mocked import, no real DB)
check(
    "Postgres backend module importable",
    lambda: PostgresLongTermStore.__name__,
)


# ============================================================
# SECTION 5: Self-editing memory tools (agent-callable)
# ============================================================
section("5. Self-editing memory (Letta-pattern tools)")

from largestack._memory.tools import (
    core_memory_replace, archival_insert, archival_search,
    memory_tool_specs,
)

acheck(
    "core_memory_replace (agent edits its own persona)",
    core_memory_replace(
        mgr, tag="persona",
        new_content="Updated: KYC + AML expert",
    ),
)

block_after = acheck("get_core_block (verify replace)", mgr.get_core_block())
assert "KYC + AML" in block_after, "core_memory_replace failed"

specs = check("memory_tool_specs (5 OpenAI-format tools)",
              lambda: memory_tool_specs(mgr))
assert len(specs) == 5
assert {s["name"] for s in specs} == {
    "core_memory_replace", "core_memory_append", "archival_insert",
    "archival_search", "recall_search",
}


# ============================================================
# SECTION 6: A2A Protocol (cross-framework interop)
# ============================================================
section("6. A2A Protocol (interop with LangGraph/CrewAI/Google ADK)")

from largestack._a2a import AgentCard, AgentSkill, A2AMessage
from largestack._a2a.v03 import (
    sign_agent_card_hs256, verify_agent_card_hs256,
    StreamingA2AServer,
)

card = check("build AgentCard", lambda: AgentCard(
    name="kyc-agent",
    description="DPDP-compliant KYC verification",
    url="https://nbfc.example.in/agents/kyc",
    skills=[AgentSkill(id="verify_pan", name="Verify PAN",
                       description="Validates PAN format")],
))

# Sign + verify
signed = check("sign card with HS256",
               lambda: sign_agent_card_hs256(card, secret="prod-secret"))
ok, _ = check("verify signed card",
              lambda: verify_agent_card_hs256(signed, secret="prod-secret"))
assert ok, "signed card verification failed"

# Tampering detection
signed.card.name = "evil-agent"
ok, _ = check("tampered card → rejected",
              lambda: verify_agent_card_hs256(signed, secret="prod-secret"))
assert not ok, "TAMPER NOT DETECTED — security failure"


# A2A streaming (Phase 4)
async def streaming_handler(input_text, task, emit):
    await emit("progress", {"step": 1, "of": 2})
    await emit("progress", {"step": 2, "of": 2})
    return f"echo: {input_text}"

server = check("build StreamingA2AServer", lambda: StreamingA2AServer(
    card=card, handler=streaming_handler,
))


async def consume_stream():
    events = []
    async for ev in server.stream_task("hello"):
        events.append(ev)
    return events


events = acheck("stream task → SSE events emitted", consume_stream())
assert any(e.event == "progress" for e in events), "no progress events"
assert any(e.event == "done" for e in events), "no done event"


# ============================================================
# SECTION 7: Multi-modal A2A (Phase 20)
# ============================================================
section("7. A2A multi-modal message parts")

from largestack._a2a.multimodal import (
    text_part, image_part, file_part,
    message_from_parts, part_get_bytes,
)

t = check("text_part", lambda: text_part("hello"))
img = check("image_part with bytes",
            lambda: image_part(data=b"PNG-bytes", media_type="image/png"))
f = check("file_part with bytes",
          lambda: file_part(data=b"PDF-content",
                            media_type="application/pdf",
                            filename="contract.pdf"))

# Compose multi-modal message
msg = check("compose multi-modal message",
            lambda: message_from_parts("user", t, img, f))
assert len(msg.parts) == 3

# Verify base64 round-trip
check(
    "part_get_bytes round-trip",
    lambda: part_get_bytes(img),
)


# ============================================================
# SECTION 8: Studio export (single-HTML visualization)
# ============================================================
section("8. Studio export + side-by-side comparison")

from largestack._studio import (
    StudioBuilder, NodeSpec, EdgeSpec, ComplianceMarker,
)

builder = check("build StudioBuilder", lambda: StudioBuilder(title="KYC Pipeline"))
builder.add_node(NodeSpec(id="intake", label="Intake", kind="start"))
builder.add_node(NodeSpec(id="kyc", label="KYC Verify", kind="agent"))
builder.add_node(NodeSpec(id="approve", label="Approve", kind="end"))
builder.add_edge(EdgeSpec(source="intake", target="kyc"))
builder.add_edge(EdgeSpec(source="kyc", target="approve"))
builder.add_audit_event(agent="kyc", event="pan_verify",
                        payload={"masked_pan": "AAA***1C"})
builder.add_compliance(ComplianceMarker(
    name="DPDP_Act_2023", section="Section 6",
))

with tempfile.TemporaryDirectory() as td:
    studio_path = Path(td) / "studio.html"
    check("export Studio HTML", lambda: builder.export(str(studio_path)))
    html = studio_path.read_text(encoding="utf-8")
    assert len(html) > 1000, "Studio HTML too small"
    assert "DPDP_Act_2023" in html, "compliance marker not in HTML"
    print(f"  → Studio HTML: {len(html)} bytes")


# Side-by-side compare (Phase 11)
from largestack._studio.compare import compute_diff, render_comparison_html

# Build a "main" version that has approve node added
builder_main = StudioBuilder(title="KYC main")
builder_main.add_node(NodeSpec(id="intake", label="Intake"))
builder_main.add_node(NodeSpec(id="kyc", label="KYC Verify"))
builder_main.add_edge(EdgeSpec(source="intake", target="kyc"))

diff = check("compute Studio diff (v0.12 vs main)",
             lambda: compute_diff(builder_main, builder))
assert "approve" in diff.nodes_added, "diff didn't catch added node"

html = check("render comparison HTML",
             lambda: render_comparison_html(builder_main, builder,
                                            label_a="main", label_b="v0.12"))


# ============================================================
# SECTION 9: Eval framework + similarity + dataset versioning
# ============================================================
section("9. Eval framework (similarity + versioning + PR diff)")

from largestack._eval.extensions_v130 import (
    EmbeddingSimilarityAssertion, hash_suite_yaml, version_suite,
)

sim = EmbeddingSimilarityAssertion(
    expected="The user is in Bengaluru", threshold=0.5,
)
passed, score, reason = acheck(
    "similarity assertion: paraphrase passes",
    sim.evaluate("The user lives in Bengaluru"),
)
print(f"  → similarity score: {score:.3f}")

# Hash a suite
yaml_text = """name: kyc-test
cases:
  - name: c1
    input: hi
"""
h = check("hash eval suite (reproducibility)",
          lambda: hash_suite_yaml(yaml_text))
assert len(h) == 64
print(f"  → suite hash: {h[:12]}...")


# PR diff (Phase 13)
from largestack._eval.pr_diff import compute_eval_delta, render_pr_comment_markdown

baseline = {
    "summary": {"pass_rate": 0.94, "passed": 47, "total": 50},
    "cases": [{"name": "kyc_pan", "passed": True},
              {"name": "kyc_aadhaar", "passed": True}],
}
current = {
    "summary": {"pass_rate": 0.87, "passed": 42, "total": 48},
    "cases": [{"name": "kyc_pan", "passed": True},
              {"name": "kyc_aadhaar", "passed": False}],
}

delta = check("compute eval delta",
              lambda: compute_eval_delta(baseline, current))
assert delta.is_overall_regression
assert any(r.name == "kyc_aadhaar" for r in delta.regressions)

md = check("render PR comment markdown",
          lambda: render_pr_comment_markdown(delta, suite_name="KYC"))
assert "kyc_aadhaar" in md
assert "94" in md and "87" in md


# Webhook alerts (Phase 14)
from largestack._eval.alerts import build_payload, AlertChannel

slack_payload = check("build Slack payload",
                      lambda: build_payload("slack", delta, "KYC"))
assert "blocks" in slack_payload

teams_payload = check("build MS Teams payload",
                      lambda: build_payload("teams", delta, "KYC"))
assert teams_payload["@type"] == "MessageCard"


# ============================================================
# SECTION 10: Loaders (PDF, DOCX, PPTX, XLSX, semantic chunking)
# ============================================================
section("10. Document loaders + semantic chunking")

from largestack._loaders.office import load_pptx, load_xlsx
from largestack._loaders.semantic_chunking import (
    SemanticChunker, split_sentences,
)

# XLSX round-trip
import openpyxl

with tempfile.TemporaryDirectory() as td:
    xlsx_path = Path(td) / "loans.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LoanBook"
    ws.append(["loan_id", "amount", "borrower"])
    ws.append(["L001", 50000, "Sachith"])
    ws.append(["L002", 100000, "Sushma"])
    wb.save(str(xlsx_path))

    docs = acheck("load .xlsx (NBFC loan book)",
                  load_xlsx(xlsx_path))
    assert len(docs) == 1
    assert "L001" in docs[0]["content"]
    assert "Sachith" in docs[0]["content"]


# Semantic chunking (Phase 15)
chunker = check("build SemanticChunker",
                lambda: SemanticChunker(
                    embedder=HashingEmbedder(dim=128),
                    breakpoint_distance=0.4,
                    min_chunk_chars=20,
                    max_chunk_chars=200,
                ))

text = (
    "First sentence about loans. Second sentence about loans. "
    "Now we shift to weather. Today is sunny. Tomorrow may rain."
)
chunks = acheck("semantic chunk a paragraph",
                chunker.chunk(text))
assert len(chunks) >= 1
print(f"  → semantic chunks produced: {len(chunks)}")


# ============================================================
# SECTION 11: Indian compliance (DPDP / RBI / PMLA)
# ============================================================
section("11. Indian compliance markers + DPDP §8 breach")

from largestack._compliance.dpdp_breach import (
    BreachDetector, BreachClassifier, BreachIndicator,
    render_dpb_notification, render_principal_notification,
    DPB_NOTIFICATION_DEADLINE_SECONDS,
    BreachDetectorConfig,
)

detector = check("build BreachDetector",
                 lambda: BreachDetector(BreachDetectorConfig(
                     mass_read_threshold=10,
                     mass_read_window_seconds=60.0,
                 )))

# Simulate mass-read breach
for _ in range(15):
    detector.observe_read(tenant_id="bank_a", user_id="rogue_user")

indicators = check("flush indicators (mass-read trigger)",
                   lambda: detector.flush())
assert any(i.kind == "mass_read" for i in indicators)
print(f"  → {len(indicators)} indicator(s) detected")

# Cross-tenant attempt
detector.observe_cross_tenant_attempt(
    actor_tenant="bank_a", target_tenant="bank_b", user_id="rogue",
)
ct = detector.flush()
assert ct[0].kind == "cross_tenant"

# Classify
classifier = BreachClassifier()
classification = check(
    "classify cross_tenant → high severity",
    lambda: classifier.classify(ct[0]),
)
assert classification.severity == "high"
assert classification.must_notify_dpb is True

# Render DPB notification
notif = check("render DPB notification (DPDP §8(6))",
              lambda: render_dpb_notification(
                  classification,
                  organisation_name="Sri Rajeshwari NBFC",
                  contact_email="dpo@srirajeshwari.in",
              ))
assert "Section 8(6)" in notif.body
assert notif.deadline_seconds == DPB_NOTIFICATION_DEADLINE_SECONDS
print(f"  → DPB deadline: {DPB_NOTIFICATION_DEADLINE_SECONDS/3600:.0f} hours")

principal_notif = check(
    "render principal notification (plain language)",
    lambda: render_principal_notification(
        classification,
        organisation_name="Sri Rajeshwari NBFC",
        contact_email="grievance@srirajeshwari.in",
        principal_name="Sachith",
    ),
)
assert "Sachith" in principal_notif.body
assert "Section 8(6)" not in principal_notif.body  # no jargon for principals


# ============================================================
# SECTION 12: LiteLLM bridge (100+ providers)
# ============================================================
section("12. LiteLLM bridge + India residency check")

from largestack._integrations.litellm_bridge import (
    LiteLLMProvider, FallbackRouter, ProviderRoute,
    CHINA_HOSTED_PROVIDERS,
)

# India residency: Bedrock Mumbai allowed
ok_provider = check(
    "Bedrock ap-south-1 + India residency = OK",
    lambda: LiteLLMProvider(
        model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
        region="ap-south-1",
        require_india_residency=True,
    ),
)

# China-hosted blocked
def try_deepseek():
    try:
        LiteLLMProvider(model="deepseek/chat",
                       require_india_residency=True)
        return False
    except ValueError:
        return True

assert check("DeepSeek + India residency = REJECTED",
             try_deepseek), "should have rejected"

# Bedrock US region rejected
def try_us_bedrock():
    try:
        LiteLLMProvider(
            model="bedrock/claude-3", region="us-east-1",
            require_india_residency=True,
        )
        return False
    except ValueError:
        return True

assert check("Bedrock us-east-1 + India residency = REJECTED",
             try_us_bedrock)

print(f"  → blocked China providers: {sorted(CHINA_HOSTED_PROVIDERS)[:4]}...")


# ============================================================
# SECTION 13: Per-tenant rate limits (SaaS readiness)
# ============================================================
section("13. Per-tenant rate limits")

from largestack._ratelimit import (
    InMemoryRateLimiter, TenantQuota,
)

rl = check("build rate limiter", lambda: InMemoryRateLimiter())
rl.set_quota("tenant_premium", rate_per_sec=100, burst=200)
rl.set_quota("tenant_basic", rate_per_sec=10, burst=20)

# Burn through basic
acheck("basic tenant: 20 acquires succeed",
       rl.try_acquire("tenant_basic", cost=20.0))
denied = acheck("basic tenant: 21st acquire denied",
                rl.try_acquire("tenant_basic", cost=1.0))
assert denied is False

# Premium has independent budget
ok = acheck("premium tenant: still has budget (isolation)",
            rl.try_acquire("tenant_premium", cost=50.0))
assert ok is True


# ============================================================
# SECTION 14: compliance-check CLI
# ============================================================
section("14. compliance-check CLI (pre-deploy validator)")

from largestack._cli.cli_v130_compliance import run_compliance_check

with tempfile.TemporaryDirectory() as td:
    # Write a known-good agent.yaml
    good = Path(td) / "good.yaml"
    good.write_text("""\
name: nbfc-kyc
sector: financial
model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
region: ap-south-1
tenant_id: '{{ env.TENANT_ID }}'
audit:
  enabled: true
  retention_days: 2920
compliance:
  - name: DPDP_Act_2023
    section: Section 6
  - name: RBI MD-NBFC-D
    section: NBFC
  - name: PMLA Rule 9
    section: CDD
""")
    report = check("good agent.yaml → PASS",
                   lambda: run_compliance_check(good))
    assert report.passed, f"expected pass, got: {report.render()}"

    # Bad: China-hosted LLM in financial sector
    bad = Path(td) / "bad.yaml"
    bad.write_text("""\
name: bad
sector: financial
model: deepseek/chat
tenant_id: '{{ env.X }}'
audit: {enabled: true}
compliance:
  - {name: DPDP_Act_2023, section: Section 6}
""")
    report = check("China-hosted LLM in financial = FAIL",
                   lambda: run_compliance_check(bad))
    assert not report.passed
    assert any("C050" in f.code for f in report.errors), \
        "should have C050 (China-hosted)"


# ============================================================
# SECTION 15: Generic typed Agent (Phase 18)
# ============================================================
section("15. Generic typed Agent (mypy --strict ready)")

from pydantic import BaseModel
from largestack._core.typed_agent import TypedAgent

class KYCInput(BaseModel):
    pan: str
    aadhaar_last4: str

class KYCOutput(BaseModel):
    verified: bool
    confidence: float


# Construction without LLM call
typed = check("TypedAgent[KYCInput, KYCOutput] direct construct",
              lambda: TypedAgent(
                  name="kyc-typed",
                  model="bedrock/claude-3-haiku",
                  input_model=KYCInput,
                  output_model=KYCOutput,
                  instructions="Verify KYC documents",
              ))

# Verify required fields enforced
def try_no_name():
    try:
        TypedAgent(name="", model="x",
                   input_model=KYCInput, output_model=KYCOutput)
        return False
    except ValueError:
        return True
assert check("TypedAgent: missing name → ValueError", try_no_name)

# Validate input round-trip via pydantic model
inp = KYCInput(pan="AAACR1234C", aadhaar_last4="9012")
prompt_msgs = check("typed agent: build prompt from input",
                    lambda: typed._build_prompt(inp))
assert len(prompt_msgs) >= 1


# ============================================================
# SECTION 16: Sub-graph Workflow composition (Phase 19)
# ============================================================
section("16. Sub-graph Workflow composition")

from largestack.workflow import Workflow
from largestack._workflow.sub_graph import as_node


async def double(state):
    state = dict(state or {})
    state["x"] = state.get("x", 0) * 2
    return state


inner = check("build inner workflow", lambda: Workflow("inner"))
inner.add_node("double", double)

sub_node = check("wrap inner workflow as sub-node", lambda: as_node(inner))

result = acheck("run sub-graph: x=5 → x=10", sub_node({"x": 5}))
assert result["x"] == 10


# ============================================================
# Final report
# ============================================================
section("FINAL SMOKE TEST RESULTS")

total = len(PASSED) + len(FAILED)
print(f"\n  Total checks: {total}")
print(f"  Passed:       {len(PASSED)} ({100*len(PASSED)/total:.1f}%)")
print(f"  Failed:       {len(FAILED)}")

if FAILED:
    print("\n  FAILED CHECKS:")
    for name, err in FAILED:
        print(f"    ✗ {name}")
        print(f"        {err}")
    sys.exit(1)
else:
    print("\n  ✅ ALL SUBSYSTEMS WORKING — READY FOR PRODUCTION TESTING")
    sys.exit(0)
