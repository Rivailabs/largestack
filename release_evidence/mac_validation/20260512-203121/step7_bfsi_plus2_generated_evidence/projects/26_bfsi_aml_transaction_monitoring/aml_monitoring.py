import os
import re

# In-memory storage for policies (loaded from file)
_policy_documents = []

def _load_policy_documents():
    global _policy_documents
    if not _policy_documents:
        policy_path = os.path.join(os.path.dirname(__file__), 'policies', 'aml_policy.md')
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Split into paragraphs as documents
            _policy_documents = [p.strip() for p in content.split('\n\n') if p.strip()]
        except FileNotFoundError:
            _policy_documents = []
    return _policy_documents

_STOPWORDS = {
    "a", "an", "and", "are", "for", "in", "is", "of", "or", "the", "to", "what", "when"
}


def _tokens(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"\w+", text.lower()) if token not in _STOPWORDS}
    normalized = set(tokens)
    for token in tokens:
        if token.endswith("ing") and len(token) > 5:
            normalized.add(token[:-3])
        if token.endswith("ed") and len(token) > 4:
            normalized.add(token[:-2])
        if token.endswith("s") and len(token) > 3:
            normalized.add(token[:-1])
    if "threshold" in tokens:
        normalized.update({"report", "reported", "amount", "limit"})
    if "sar" in tokens:
        normalized.update({"suspicious", "activity", "report", "filing", "file"})
    return normalized


def _token_overlap(query: str, document: str) -> int:
    """Count meaningful overlapping tokens between query and document."""
    query_tokens = _tokens(query)
    doc_tokens = _tokens(document)
    return len(query_tokens & doc_tokens)

def _watchlist_entries(watchlist) -> tuple[set[str], list[str]]:
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
            entity = str(entry.get("entity", "")).upper()
            kind = entry.get("type", "")
            if kind == "sanctions_country" and entity:
                countries.add(entity)
                if entity == "IRAN":
                    countries.add("IR")
                elif entity == "NORTH KOREA":
                    countries.add("KP")
            if "keyword" in entry:
                keywords.append(str(entry["keyword"]).lower())
    return countries, keywords


def screen_transaction(txn: dict, customer: dict, watchlist) -> dict:
    """
    Screen a transaction for AML risk.
    Returns a dict with 'risk' (high/low), 'risk_level' (high/low), and 'reasons' list.
    """
    reasons = []
    risk = 'low'

    blocked_countries, configured_keywords = _watchlist_entries(watchlist)

    country = str(txn.get('counterparty_country') or txn.get('country') or '').upper()
    if country in blocked_countries:
        reasons.append(f"Country {country} is sanctioned")
        risk = 'high'

    # Check amount spike (above 5x average monthly volume)
    avg_volume = customer.get('avg_monthly_volume', customer.get('average_monthly_volume', 0))
    amount = txn.get('amount', 0)
    if avg_volume > 0 and amount > 5 * avg_volume:
        reasons.append(f"Amount {amount} exceeds 5x average monthly volume {avg_volume}")
        risk = 'high'

    # Check high-risk keywords in transaction description (if any)
    description = txn.get('description', '')
    high_risk_keywords = configured_keywords or [
        'terrorism', 'money laundering', 'fraud', 'bribery', 'corruption', 'sanctions evasion'
    ]
    for keyword in high_risk_keywords:
        if keyword.lower() in description.lower():
            reasons.append(f"Description contains high-risk keyword: {keyword}")
            risk = 'high'
            break

    # Check high-risk KYC profile
    kyc_risk = customer.get('kyc_risk', 'low')
    if kyc_risk == 'high':
        reasons.append("Customer KYC profile is high risk")
        risk = 'high'

    return {
        'risk': risk,
        'risk_level': risk,
        'requires_review': risk == 'high',
        'reasons': reasons
    }

def draft_sar(txn: dict, screening: dict) -> dict:
    """
    Draft a Suspicious Activity Report based on screening results.
    Never files externally; returns filed=False and approval_required=True for high-risk screening.
    Returns dict with 'draft', 'filed', 'approval_required', 'requires_review' keys.
    """
    if screening.get('risk') == 'high' or screening.get('risk_level') == 'high':
        return {
            'draft': 'SAR: Suspicious activity detected - requires manual review.',
            'filed': False,
            'approval_required': True,
            'requires_review': True
        }
    else:
        return {
            'draft': 'No SAR needed.',
            'filed': False,
            'approval_required': False,
            'requires_review': False
        }

def policy_answer(query: str, documents) -> dict:
    """
    Answer a policy question using token-overlap retrieval.
    Returns dict with 'answer' and 'citations' list.
    If no document has sufficient overlap, returns 'Insufficient evidence to answer.' with empty citations.
    """
    if not documents:
        documents = _load_policy_documents()
    if isinstance(documents, dict):
        iterable = list(documents.items())
    else:
        iterable = [(f"document_{i + 1}", doc) for i, doc in enumerate(documents)]
    
    best_score = 0
    best_doc = None
    best_name = None
    for name, doc in iterable:
        score = _token_overlap(query, doc)
        if score > best_score:
            best_score = score
            best_doc = doc
            best_name = name
    
    if best_score >= 2:
        return {
            'answer': best_doc,
            'citations': [best_name or 'policy']
        }
    else:
        return {
            'answer': 'Insufficient evidence to answer.',
            'citations': []
        }
