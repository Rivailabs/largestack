import os
import sys
import tempfile
import shutil

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rag_assistant.rag import answer


def setup_module(module):
    """Create temporary docs directory with required files."""
    global tmpdir
    tmpdir = tempfile.mkdtemp()
    # Create docs subdirectory
    docs_dir = os.path.join(tmpdir, 'docs')
    os.makedirs(docs_dir, exist_ok=True)
    # Write refund_policy.md
    with open(os.path.join(docs_dir, 'refund_policy.md'), 'w', encoding='utf-8') as f:
        f.write("# Refund Policy\n\nDuplicate payments require approval before refund.\n\nAll refund requests must be submitted within 30 days.\n\nApproval from the finance department is necessary for processing duplicate payment refunds.\n")
    # Write security_policy.md
    with open(os.path.join(docs_dir, 'security_policy.md'), 'w', encoding='utf-8') as f:
        f.write("# Security Policy\n\nAccount protection is ensured through multi-factor authentication.\n\nAccess controls restrict sensitive data to authorized personnel only.\n\nRegular security audits are conducted to maintain integrity.\n")
    # Store docs_dir for tests
    module.docs_dir = docs_dir


def teardown_module(module):
    """Clean up temporary directory."""
    shutil.rmtree(tmpdir)


def test_answer_duplicate_payments():
    """Query about duplicate payments must cite refund_policy.md and answer must contain 'approval'."""
    result = answer("What is the policy on duplicate payments?", docs_dir=docs_dir)
    assert 'refund_policy.md' in result['citations'], f"Expected refund_policy.md in citations, got {result['citations']}"
    assert 'approval' in result['answer'].lower(), f"Answer must contain 'approval', got: {result['answer']}"


def test_answer_unknown_equity_refresh():
    """Query about unknown equity refresh policy must return 'Insufficient evidence' and no citations."""
    result = answer("What is the equity refresh policy?", docs_dir=docs_dir)
    assert result['answer'] == 'Insufficient evidence', f"Expected 'Insufficient evidence', got: {result['answer']}"
    assert result['citations'] == [], f"Expected empty citations, got {result['citations']}"


def test_answer_security_policy():
    """Query about account protection should return security_policy.md."""
    result = answer("How is account protection handled?", docs_dir=docs_dir)
    assert 'security_policy.md' in result['citations'], f"Expected security_policy.md in citations, got {result['citations']}"
    assert 'account protection' in result['answer'].lower()


def test_answer_no_match():
    """Query with no relevant document should return 'Insufficient evidence' and no citations."""
    result = answer("What is the weather today?", docs_dir=docs_dir)
    assert result['answer'] == 'Insufficient evidence', f"Expected 'Insufficient evidence', got: {result['answer']}"
    assert result['citations'] == [], f"Expected empty citations, got {result['citations']}"
