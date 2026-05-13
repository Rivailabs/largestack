from aml_monitoring import batch_screen, draft_sar, policy_answer, screen_transaction


def test_screen_transaction_sanctions_and_keyword():
    txn = {
        "txn_id": "T1",
        "amount": 1_200_000,
        "country": "IR",
        "description": "crypto mixer payout",
        "customer_id": "C1",
    }
    customer = {"kyc_risk": "high", "average_monthly_volume": 100_000}
    watchlist = {"blocked_countries": ["IR", "KP"], "high_risk_keywords": ["crypto mixer"]}
    result = screen_transaction(txn, customer, watchlist)
    assert result["risk_level"] == "high"
    assert result["risk"] == "high"
    assert result["requires_review"] is True
    assert any("sanctioned" in reason.lower() for reason in result["reasons"])
    assert any("keyword" in reason.lower() for reason in result["reasons"])


def test_screen_transaction_list_watchlist_and_counterparty_country():
    txn = {"txn_id": "T2", "amount": 25_000, "counterparty_country": "IR"}
    customer = {"kyc_risk": "low", "avg_monthly_volume": 20_000}
    watchlist = [{"entity": "Iran", "type": "sanctions_country"}]
    result = screen_transaction(txn, customer, watchlist)
    assert result["risk_level"] == "high"
    assert result["requires_review"] is True


def test_low_risk_transaction():
    txn = {"txn_id": "T3", "amount": 5_000, "country": "US", "description": "vendor invoice"}
    customer = {"kyc_risk": "low", "average_monthly_volume": 100_000}
    result = screen_transaction(txn, customer, {"blocked_countries": ["IR"], "high_risk_keywords": []})
    assert result["risk_level"] == "low"
    assert result["reasons"] == []


def test_draft_sar_never_files_externally():
    txn = {"txn_id": "T1", "amount": 1_200_000}
    high = {"risk_level": "high", "reasons": ["Country IR is sanctioned"]}
    sar = draft_sar(txn, high)
    assert "SAR Draft" in sar["draft"]
    assert sar["approval_required"] is True
    assert sar["requires_review"] is True
    assert sar["filed"] is False
    low = draft_sar(txn, {"risk_level": "low", "reasons": []})
    assert low["draft"] == "No SAR needed."
    assert low["approval_required"] is False
    assert low["filed"] is False


def test_policy_answer_cites_document_name():
    docs = {"aml_policy.md": "High risk sanctions or structuring cases require MLRO review before filing SAR."}
    answer = policy_answer("when file sar for sanctions?", docs)
    assert "MLRO" in answer["answer"]
    assert answer["citations"] == ["aml_policy.md"]


def test_policy_answer_insufficient_evidence():
    docs = {"aml_policy.md": "High risk sanctions cases require MLRO review before filing SAR."}
    answer = policy_answer("equity refresh policy?", docs)
    assert answer["answer"] == "Insufficient evidence to answer."
    assert answer["citations"] == []


def test_batch_screen_uses_customer_map():
    transactions = [
        {"txn_id": "T1", "customer_id": "C1", "amount": 1_200_000, "country": "IR", "description": "crypto mixer"},
        {"txn_id": "T2", "customer_id": "C2", "amount": 1_000, "country": "US", "description": "invoice"},
    ]
    customers = {
        "C1": {"kyc_risk": "high", "average_monthly_volume": 100_000},
        "C2": {"kyc_risk": "low", "average_monthly_volume": 100_000},
    }
    results = batch_screen(transactions, customers, {"blocked_countries": ["IR"], "high_risk_keywords": ["crypto mixer"]})
    assert [row["risk_level"] for row in results] == ["high", "low"]
