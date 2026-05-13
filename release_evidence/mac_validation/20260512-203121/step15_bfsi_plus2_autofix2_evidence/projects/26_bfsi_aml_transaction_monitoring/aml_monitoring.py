import re
from collections import Counter

# Stopwords for token overlap
STOPWORDS = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but', 'not', 'with', 'as', 'by', 'from', 'it', 'its', 'this', 'that', 'these', 'those', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could', 'shall', 'should', 'may', 'might', 'must', 'about', 'into', 'over', 'after', 'before', 'between', 'under', 'above', 'below', 'out', 'off', 'up', 'down', 'no', 'nor', 'so', 'if', 'then', 'than', 'too', 'very', 'just', 'because', 'when', 'where', 'how', 'what', 'which', 'who', 'whom', 'why'}

def _tokenize(text):
    return [w.lower() for w in re.findall(r'\w+', text) if w.lower() not in STOPWORDS]

def screen_transaction(txn, customer, watchlist):
    reasons = []
    risk_level = 'low'
    requires_review = False

    # Determine country
    country = txn.get('country') or txn.get('counterparty_country')
    # Determine average monthly volume
    avg_volume = customer.get('average_monthly_volume') or customer.get('avg_monthly_volume')

    # Normalize watchlist
    if isinstance(watchlist, dict):
        blocked_countries = watchlist.get('blocked_countries', [])
        high_risk_keywords = watchlist.get('high_risk_keywords', [])
    elif isinstance(watchlist, list):
        blocked_countries = []
        high_risk_keywords = []
        for item in watchlist:
            if isinstance(item, str):
                high_risk_keywords.append(item)
            elif isinstance(item, dict):
                blocked_countries.extend(item.get('blocked_countries', []))
                high_risk_keywords.extend(item.get('high_risk_keywords', []))
    else:
        blocked_countries = []
        high_risk_keywords = []

    # Sanctions country check
    if country and country in blocked_countries:
        reasons.append(f"Country {country} is sanctioned")
        risk_level = 'high'
        requires_review = True

    # Amount spike check
    if avg_volume and avg_volume > 0:
        if txn['amount'] > 5 * avg_volume:
            reasons.append(f"Amount {txn['amount']} exceeds 5x average monthly volume {avg_volume}")
            risk_level = 'high'
            requires_review = True

    # High-risk keywords in transaction description
    description = txn.get('description', '')
    for kw in high_risk_keywords:
        if kw.lower() in description.lower():
            reasons.append(f"High-risk keyword '{kw}' found in description")
            risk_level = 'high'
            requires_review = True

    # High-risk KYC profile
    kyc_score = customer.get('kyc_score', 0)
    if kyc_score >= 80:
        reasons.append(f"High-risk KYC profile with score {kyc_score}")
        risk_level = 'high'
        requires_review = True

    if not reasons:
        reasons.append("No risk indicators")
        risk_level = 'low'

    return {
        'risk_level': risk_level,
        'risk': risk_level == 'high',
        'requires_review': requires_review,
        'reasons': reasons
    }

def draft_sar(txn, screening):
    filed = False
    approval_required = False
    requires_review = False
    if screening.get('risk_level') == 'high':
        approval_required = True
        requires_review = True
    return {
        'filed': filed,
        'approval_required': approval_required,
        'requires_review': requires_review
    }

def policy_answer(query, documents):
    # Normalize documents to dict
    if isinstance(documents, list):
        doc_dict = {f"doc_{i}": doc for i, doc in enumerate(documents)}
    elif isinstance(documents, dict):
        doc_dict = documents
    else:
        doc_dict = {}

    query_tokens = _tokenize(query)
    if not query_tokens:
        return {'answer': 'Insufficient evidence to answer.', 'citations': []}

    # Token overlap scoring
    scores = {}
    for filename, text in doc_dict.items():
        doc_tokens = _tokenize(text)
        if not doc_tokens:
            continue
        overlap = sum((Counter(query_tokens) & Counter(doc_tokens)).values())
        if overlap > 0:
            scores[filename] = overlap

    if not scores:
        return {'answer': 'Insufficient evidence to answer.', 'citations': []}

    # Sort by overlap descending
    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Return top 2 citations
    citations = [filename for filename, _ in sorted_docs[:2]]
    # Build answer from top document
    top_doc = sorted_docs[0][0]
    top_text = doc_dict[top_doc]
    # Extract first sentence as answer
    first_sentence = top_text.split('.')[0] + '.'
    return {'answer': first_sentence, 'citations': citations}
