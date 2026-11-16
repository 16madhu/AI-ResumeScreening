"""
Module: text_extractor.py
Extracts raw text from PDF and DOCX files using PyMuPDF and python-docx,
and cleans text by standardizing whitespace and formatting.
"""

import os
import re
import io
from typing import Union, BinaryIO

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import docx


def clean_text(text: str) -> str:
    """
    Cleans extracted text by standardizing whitespaces, stripping control characters,
    and removing redundant blank lines while preserving word boundaries.
    """
    if not text:
        return ""
    
    # Replace non-breaking spaces, tabs, and form feeds with standard space
    text = text.replace('\xa0', ' ').replace('\t', ' ').replace('\r', '\n')
    
    # Remove control characters except standard newlines
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Normalize multiple consecutive spaces to a single space
    text = re.sub(r'[ ]+', ' ', text)
    
    # Normalize multiple consecutive newlines (more than 2) to standard paragraph breaks
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()


def extract_text_from_pdf(source: Union[str, bytes, BinaryIO]) -> str:
    """
    Extracts text from a PDF document using PyMuPDF (fitz).
    Supports file path (str), raw bytes, or file-like streams.
    """
    text_parts = []
    
    if isinstance(source, bytes):
        doc = fitz.open(stream=source, filetype="pdf")
    elif isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"PDF file not found at: {source}")
        doc = fitz.open(source)
    elif hasattr(source, "read"):
        content = source.read()
        doc = fitz.open(stream=content, filetype="pdf")
    else:
        raise ValueError("Unsupported source type for PDF extraction")

    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_text = page.get_text("text")
            if page_text:
                text_parts.append(page_text)
    finally:
        doc.close()

    raw_text = "\n".join(text_parts)
    return clean_text(raw_text)


def extract_text_from_docx(source: Union[str, bytes, BinaryIO]) -> str:
    """
    Extracts text from a DOCX document using python-docx.
    Extracts text from both paragraphs and table structures.
    """
    if isinstance(source, bytes):
        doc_stream = io.BytesIO(source)
        doc = docx.Document(doc_stream)
    elif isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"DOCX file not found at: {source}")
        doc = docx.Document(source)
    elif hasattr(source, "read"):
        doc = docx.Document(source)
    else:
        raise ValueError("Unsupported source type for DOCX extraction")

    text_parts = []
    
    # Extract from paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    # Extract from tables
    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_text:
                text_parts.append(" | ".join(row_text))

    raw_text = "\n".join(text_parts)
    return clean_text(raw_text)


def extract_text(source: Union[str, bytes, BinaryIO], filename: str = "") -> str:
    """
    Router function to extract text based on file extension.
    """
    ext = ""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
    elif isinstance(source, str):
        ext = os.path.splitext(source)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(source)
    elif ext in [".docx", ".doc"]:
        return extract_text_from_docx(source)
    elif ext == ".txt":
        if isinstance(source, bytes):
            return clean_text(source.decode("utf-8", errors="ignore"))
        elif isinstance(source, str) and os.path.exists(source):
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                return clean_text(f.read())
        elif hasattr(source, "read"):
            content = source.read()
            if isinstance(content, bytes):
                return clean_text(content.decode("utf-8", errors="ignore"))
            return clean_text(str(content))
        return clean_text(str(source))
    else:
        # If no extension or unknown, attempt PDF then DOCX then text decode
        if isinstance(source, str) and not os.path.exists(source):
            return clean_text(source)
        try:
            return extract_text_from_pdf(source)
        except Exception:
            try:
                return extract_text_from_docx(source)
            except Exception:
                if isinstance(source, (bytes, str)):
                    return clean_text(str(source))
                raise ValueError("Unable to determine file format or parse document text.")

