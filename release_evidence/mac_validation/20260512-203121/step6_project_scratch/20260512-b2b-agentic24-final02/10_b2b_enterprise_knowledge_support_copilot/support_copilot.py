import re

_articles = {}

def add_article(doc_id: str, content: str) -> None:
    _articles[doc_id] = content

def _tokenize(text: str) -> set:
    # Lowercase, split on non-alphanumeric, filter out weak words (short, common)
    weak = {'the', 'a', 'an', 'is', 'it', 'to', 'in', 'for', 'of', 'on', 'and', 'or', 'at', 'by', 'with', 'from', 'as', 'be', 'this', 'that', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could', 'may', 'might', 'shall', 'should', 'not', 'no', 'nor', 'but', 'if', 'so', 'up', 'out', 'about', 'into', 'over', 'after', 'before', 'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own', 'same', 'too', 'very', 'just', 'also', 'now', 'than', 'then', 'these', 'those', 'which', 'who', 'whom', 'what', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself', 'they', 'them', 'their', 'theirs', 'themselves', 'it', 'its', 'itself'}
    tokens = set()
    for word in re.findall(r'[a-zA-Z0-9]+', text.lower()):
        if len(word) >= 3 and word not in weak:
            tokens.add(word)
    return tokens

def _retrieve(query: str) -> list:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    results = []
    for doc_id, content in _articles.items():
        content_tokens = _tokenize(content)
        overlap = query_tokens & content_tokens
        if len(overlap) >= 2:
            results.append((doc_id, content, len(overlap)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results

def answer_question(query: str) -> dict:
    results = _retrieve(query)
    if not results:
        return {'answer': 'Insufficient evidence', 'citations': []}
    best_doc_id, best_content, _ = results[0]
    return {'answer': best_content, 'citations': [best_doc_id]}

def escalation_decision(request: str) -> dict:
    request_lower = request.lower()
    # Security/payment keywords
    security_keywords = ['delete', 'remove', 'purge', 'wipe', 'destroy', 'terminate', 'shutdown', 'kill', 'erase', 'drop']
    payment_keywords = ['payment', 'billing', 'invoice', 'charge', 'refund', 'credit', 'debit', 'pay', 'transaction', 'purchase']
    for kw in security_keywords:
        if kw in request_lower:
            return {'approval_required': True, 'reason': 'Security action requires approval', 'executed': False}
    for kw in payment_keywords:
        if kw in request_lower:
            return {'approval_required': True, 'reason': 'Payment action requires approval', 'executed': False}
    return {'approval_required': False, 'reason': '', 'executed': True}
