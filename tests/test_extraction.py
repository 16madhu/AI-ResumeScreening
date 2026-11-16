"""
Unit tests for text extraction (PDF, DOCX, text) and PII masking.
"""

import os
import pytest
from backend.text_extractor import clean_text, extract_text_from_pdf, extract_text_from_docx, extract_text
from backend.pii_masker import mask_pii, EMAIL_REGEX, PHONE_REGEX


def test_clean_text():
    raw = "   John   Doe  \t\n\n\n\nSoftware Engineer \xa0with Python.   "
    cleaned = clean_text(raw)
    assert "   " not in cleaned
    assert "John Doe" in cleaned
    assert "Software Engineer" in cleaned
    assert "\xa0" not in cleaned


def test_pii_masking_emails_and_phones():
    text = (
        "Candidate contact: test.user@example.com, alt: dev.lead@techcorp.org. "
        "Call +1-555-234-5678 or 9876543210. "
        "Portfolio: https://github.com/testdev"
    )
    masked, meta = mask_pii(text)

    assert "[EMAIL]" in masked
    assert "test.user@example.com" not in masked
    assert "[PHONE]" in masked
    assert "555-234-5678" not in masked
    assert "[URL]" in masked
    assert meta["emails_count"] == 2
    assert meta["phones_count"] >= 1
    assert meta["urls_count"] >= 1
    assert "disclaimer" in meta


def test_docx_extraction_existing_proposal():
    # The proposal document is present in the workspace root
    proposal_file = "AIML_Project_Proposal_Updated (1).docx"
    if os.path.exists(proposal_file):
        text = extract_text(proposal_file)
        assert len(text) > 100
        assert "Resume Screening" in text

