"""Local AML transaction monitoring demo for LARGESTACK BFSI validation."""
from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "for", "in", "is", "of", "or", "the", "to", "what", "when",
}


def load_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Load synthetic CSV rows from the local project data directory."""
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _tokens(text: str) -> set[str]:
    words = {word for word in re.findall(r"\w+", text.lower()) if word not in STOPWORDS}
    expanded = set(words)
    for word in words:
        if word.endswith("ing") and len(word) > 5:
            expanded.add(word[:-3])
        if word.endswith("ed") and len(word) > 4:
            expanded.add(word[:-2])
        if word.endswith("s") and len(word) > 3:
            expanded.add(word[:-1])
    if "sar" in words:
        expanded.update({"suspicious", "activity", "report", "file", "filing"})
    if "threshold" in words:
        expanded.update({"report", "amount", "limit"})
    return expanded


def _watchlist_parts(watchlist: Any) -> tuple[set[str], list[str]]:
    countries: set[str] = set()
    keywords: list[str] = []
    if isinstance(watchlist, dict):
        countries.update(str(c).upper() for c in watchlist.get("blocked_countries", []))
        keywords.extend(str(k).lower() for k in watchlist.get("high_risk_keywords", []))
        return countries, keywords
    for entry in watchlist or []:
        if isinstance(entry, str):
            countries.add(entry.upper())
        elif isinstance(entry, dict):
            if entry.get("type") == "sanctions_country":
                entity = str(entry.get("entity", "")).upper()
                countries.add(entity)
                if entity == "IRAN":
                    countries.add("IR")
                if entity == "NORTH KOREA":
                    countries.add("KP")
            if entry.get("keyword"):
                keywords.append(str(entry["keyword"]).lower())
    return countries, keywords


def screen_transaction(txn: dict, customer: dict, watchlist: Any) -> dict:
    """Screen a transaction and return deterministic AML risk evidence."""
    blocked_countries, configured_keywords = _watchlist_parts(watchlist)
    reasons: list[str] = []
    country = str(txn.get("country") or txn.get("counterparty_country") or "").upper()
    amount = float(txn.get("amount", 0) or 0)
    avg_volume = float(
        customer.get("average_monthly_volume", customer.get("avg_monthly_volume", 0)) or 0
    )
    description = str(txn.get("description", ""))

    if country in blocked_countries:
        reasons.append(f"Country {country} is sanctioned")
    if avg_volume > 0 and amount > 5 * avg_volume:
        reasons.append(f"Amount {amount:.0f} exceeds 5x average monthly volume {avg_volume:.0f}")

    high_risk_keywords = configured_keywords or [
        "crypto mixer", "cash structuring", "terrorism", "money laundering", "sanctions evasion",
    ]
    for keyword in high_risk_keywords:
        if keyword in description.lower():
            reasons.append(f"Description contains high-risk keyword: {keyword}")

    if str(customer.get("kyc_risk", "")).lower() == "high":
        reasons.append("Customer KYC profile is high risk")

    risk_level = "high" if reasons else "low"
    return {
        "txn_id": txn.get("txn_id"),
        "risk": risk_level,
        "risk_level": risk_level,
        "requires_review": risk_level == "high",
        "reasons": reasons,
    }


def draft_sar(txn: dict, screening: dict) -> dict:
    """Prepare a SAR draft locally; never file or call an external system."""
    high_risk = screening.get("risk_level") == "high" or screening.get("risk") == "high"
    if high_risk:
        return {
            "txn_id": txn.get("txn_id"),
            "draft": "SAR Draft: suspicious activity requires MLRO review before filing.",
            "filed": False,
            "approval_required": True,
            "requires_review": True,
            "narrative": "; ".join(screening.get("reasons", [])),
        }
    return {
        "txn_id": txn.get("txn_id"),
        "draft": "No SAR needed.",
        "filed": False,
        "approval_required": False,
        "requires_review": False,
        "narrative": "No suspicious activity detected.",
    }


def policy_answer(query: str, documents: dict[str, str] | list[str]) -> dict:
    """Answer AML policy questions with citation-backed token retrieval."""
    if isinstance(documents, dict):
        items = list(documents.items())
    else:
        items = [(f"document_{i + 1}", text) for i, text in enumerate(documents)]
    query_tokens = _tokens(query)
    best_name = ""
    best_text = ""
    best_score = 0
    for name, text in items:
        score = len(query_tokens & _tokens(text))
        if score > best_score:
            best_name = name
            best_text = text
            best_score = score
    if best_score < 2:
        return {"answer": "Insufficient evidence to answer.", "citations": []}
    return {"answer": best_text, "citations": [best_name]}


def batch_screen(transactions: list[dict], customers: dict[str, dict], watchlist: Any) -> list[dict]:
    """Screen a batch of synthetic transactions for local validation."""
    results = []
    for txn in transactions:
        customer = customers.get(str(txn.get("customer_id")), {})
        results.append(screen_transaction(txn, customer, watchlist))
    return results
