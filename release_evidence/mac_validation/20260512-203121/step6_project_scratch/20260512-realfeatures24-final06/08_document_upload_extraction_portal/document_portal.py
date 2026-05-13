import os
import re

# Configuration
MAX_FILE_SIZE = 1024 * 1024  # 1 MB
ALLOWED_EXTENSIONS = {'.txt', '.csv', '.json', '.xml'}

def upload_document(filename: str, content: str) -> dict:
    """
    Upload a document after validating size and extension.
    Returns a document dict with keys: filename, content, size, extension.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported extension: {ext}. Allowed: {ALLOWED_EXTENSIONS}")
    size = len(content.encode('utf-8'))
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {size} bytes. Max: {MAX_FILE_SIZE} bytes")
    return {
        'filename': filename,
        'content': content,
        'size': size,
        'extension': ext
    }

def extract_fields(doc: dict) -> dict:
    """
    Extract fields from a document based on simple patterns.
    Returns a dict of extracted field names to values.
    """
    fields = {}
    content = doc.get('content', '')
    for line in content.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            # Normalize key: remove common prefixes like 'invoice' to get 'total'
            if 'total' in key:
                match = re.search(r'[\d.]+', value)
                if match:
                    fields['total'] = match.group()
            elif 'vendor' in key:
                fields['vendor'] = value
            elif 'date' in key:
                fields['date'] = value
            else:
                fields[key] = value
    return fields

def classify_document(doc: dict) -> str:
    """
    Classify a document based on its content.
    Returns a string label: 'invoice', 'receipt', 'report', or 'unknown'.
    """
    content = doc.get('content', '').lower()
    if 'invoice' in content:
        return 'invoice'
    elif 'receipt' in content:
        return 'receipt'
    elif 'report' in content:
        return 'report'
    else:
        return 'unknown'
