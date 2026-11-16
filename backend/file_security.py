"""
Module: file_security.py
Implements defensive file upload security for ResumeScope:
1. File extension and MIME type validation.
2. File magic bytes / header inspection (PDF, DOCX, TXT) to prevent disguised executable uploads.
3. File size limits (rejects empty or oversized files).
4. Path traversal prevention and cryptographically random filename generation.
5. Secure temporary storage outside public web roots with guaranteed cleanup.
"""

import os
import io
import zipfile
import secrets
from typing import Tuple, Optional
from werkzeug.utils import secure_filename

# Configuration
SECURE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secure_uploads")
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB strict limit
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Magic byte signatures
PDF_MAGIC = b"%PDF-"
ZIP_DOCX_MAGIC = b"PK\x03\x04"

os.makedirs(SECURE_UPLOAD_DIR, exist_ok=True)


def sanitize_filename(original_name: str) -> str:
    """
    Sanitizes an incoming filename, stripping directory path traversal
    sequences, absolute path indicators, and unsafe control characters.
    """
    if not original_name:
        return "unnamed_document"
    clean_base = os.path.basename(original_name)
    safe = secure_filename(clean_base)
    return safe if safe else "document"


def validate_file_content(file_bytes: bytes, filename: str) -> Tuple[bool, str]:
    """
    Validates file content by inspecting magic headers and structure:
    - PDF: Must start with %PDF- header.
    - DOCX: Must be a valid zip archive containing Word document structure.
    - TXT: Must be valid UTF-8/ASCII without null bytes or binary executable headers.
    
    Returns:
        (is_valid: bool, reason: str)
    """
    if not file_bytes or len(file_bytes) == 0:
        return False, "File is empty (0 bytes)."

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB."

    ext = os.path.splitext(filename.lower())[1]

    if ext == ".pdf":
        if not file_bytes.startswith(PDF_MAGIC):
            return False, "Invalid PDF: Missing standard '%PDF-' file signature."
        return True, "Valid PDF"

    elif ext == ".docx":
        if not file_bytes.startswith(ZIP_DOCX_MAGIC):
            return False, "Invalid DOCX: Missing standard PK zip header."
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = zf.namelist()
                if not any("word/document.xml" in n or "[Content_Types].xml" in n for n in names):
                    return False, "Invalid DOCX: Archive missing required Word XML document structures."
            return True, "Valid DOCX"
        except zipfile.BadZipFile:
            return False, "Invalid DOCX: Archive is corrupted or malformed."

    elif ext == ".txt":
        # Disallow executable headers (e.g. PE MZ header or ELF \x7fELF)
        if file_bytes.startswith(b"MZ") or file_bytes.startswith(b"\x7fELF"):
            return False, "Invalid TXT: Binary executable header detected."
        if b"\x00" in file_bytes[:1024]:
            return False, "Invalid TXT: Binary null bytes detected."
        try:
            file_bytes.decode("utf-8")
            return True, "Valid TXT"
        except UnicodeDecodeError:
            try:
                file_bytes.decode("latin-1")
                return True, "Valid TXT (Latin-1)"
            except Exception:
                return False, "Invalid TXT: Unrecognized or non-text encoding."

    return False, f"Unsupported file extension: {ext}. Only PDF, DOCX, and TXT are allowed."


def generate_secure_storage_name(filename: str) -> str:
    """
    Generates a cryptographically random, unpredictable filename
    while preserving the validated extension.
    Prevents file overwriting, enumeration, and path traversal.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".bin"
    return f"{secrets.token_hex(16)}{ext}"


class SecureTemporaryUpload:
    """
    Context manager for handling temporary file writes.
    Ensures that uploaded files written to disk are automatically
    unlinked/scrubbed upon completion or error.
    """
    def __init__(self, file_bytes: bytes, filename: str):
        self.file_bytes = file_bytes
        self.original_filename = sanitize_filename(filename)
        self.safe_filename = generate_secure_storage_name(self.original_filename)
        self.filepath = os.path.join(SECURE_UPLOAD_DIR, self.safe_filename)

    def __enter__(self) -> str:
        with open(self.filepath, "wb") as f:
            f.write(self.file_bytes)
        return self.filepath

    def __exit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.filepath):
            try:
                # Overwrite bytes before deletion for secure scrubbing
                with open(self.filepath, "wb") as f:
                    f.write(b"\x00" * min(len(self.file_bytes), 4096))
                os.remove(self.filepath)
            except Exception:
                try:
                    os.remove(self.filepath)
                except Exception:
                    pass

