import pytest
from document_portal import upload_document, extract_fields, classify_document

def test_upload_document_valid():
    doc = upload_document('invoice.txt', 'Invoice total: 1200\nVendor: ACME')
    assert doc['filename'] == 'invoice.txt'
    assert doc['size'] == len('Invoice total: 1200\nVendor: ACME'.encode('utf-8'))
    assert doc['extension'] == '.txt'

def test_upload_document_unsupported_extension():
    with pytest.raises(ValueError, match='Unsupported extension'):
        upload_document('invoice.pdf', 'content')

def test_upload_document_too_large():
    large_content = 'a' * (1024 * 1024 + 1)
    with pytest.raises(ValueError, match='File too large'):
        upload_document('large.txt', large_content)

def test_classify_document_invoice():
    doc = upload_document('invoice.txt', 'Invoice total: 1200\nVendor: ACME')
    assert classify_document(doc) == 'invoice'

def test_classify_document_receipt():
    doc = upload_document('receipt.txt', 'Receipt total: 50')
    assert classify_document(doc) == 'receipt'

def test_classify_document_unknown():
    doc = upload_document('notes.txt', 'Some random notes')
    assert classify_document(doc) == 'unknown'

def test_extract_fields_total():
    doc = upload_document('invoice.txt', 'Invoice total: 1200\nVendor: ACME')
    fields = extract_fields(doc)
    assert fields['total'] == '1200'

def test_extract_fields_vendor():
    doc = upload_document('invoice.txt', 'Invoice total: 1200\nVendor: ACME')
    fields = extract_fields(doc)
    assert fields['vendor'] == 'ACME'

def test_extract_fields_no_total():
    doc = upload_document('note.txt', 'Some text without total')
    fields = extract_fields(doc)
    assert 'total' not in fields

def test_public_contract():
    doc = upload_document('invoice.txt', 'Invoice total: 1200\nVendor: ACME')
    assert classify_document(doc) == 'invoice'
    assert extract_fields(doc)['total'] == '1200'
