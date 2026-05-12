# Document Upload Extraction Portal

A Python project that provides document upload, field extraction, and classification using only the standard library. Includes a LARGESTACK integration with async smoke test demonstrating rag_citations and memory_isolation features.

## Run Instructions

1. Install dependencies:
   ```bash
   pip install largestack pytest
   ```

2. Run the document portal tests:
   ```bash
   pytest tests/test_document_portal.py -v
   ```

3. Run the LARGESTACK smoke test:
   ```bash
   pytest tests/test_largestack_features.py -v
   ```

## Test Instructions

- All tests are located under `tests/`.
- The document portal tests use only the standard library.
- The LARGESTACK smoke test uses `TestModel` overrides to avoid network calls.

## Project Structure

- `document_portal.py` - Core document upload, extraction, and classification.
- `largestack_app.py` - LARGESTACK integration with async smoke test.
- `data/sample_invoice.txt` - Sample invoice file for testing.
- `policies/upload_policy.json` - Upload policy configuration.
- `tests/test_document_portal.py` - Tests for document portal.
- `tests/test_largestack_features.py` - Tests for LARGESTACK features.
