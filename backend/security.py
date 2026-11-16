"""
Module: security.py
Provides core cryptographic and security services for ResumeScope:
1. Authenticated symmetric encryption (AES-256-GCM) for sensitive data at rest.
2. Secure key management (keys loaded from environment or protected file, never hardcoded).
3. Memory-hard password hashing using Argon2id.
4. Cryptographically signed authentication tokens.
5. Log sanitization to prevent sensitive data leakage.
"""

import os
import re
import hmac
import time
import base64
import hashlib
import secrets
from typing import Tuple, Optional, Dict, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

# Key configuration
# Deterministic email HMAC lookup utility
def _load_email_hmac_key() -> bytes:
    """Load the deterministic HMAC key for email lookup.
    The key is taken from the ``EMAIL_HMAC_KEY`` environment variable.
    It must be either a 64‑character hex string (32‑byte) or a base64‑encoded
    32‑byte value. If the variable is missing, a stable key is derived from the
    primary encryption key ``_ENCRYPTION_KEY`` so that the HMAC stays constant
    across application restarts.
    """
    env_key = os.getenv('EMAIL_HMAC_KEY')
    if env_key:
        try:
            # Hex representation (64 hex chars == 32 bytes)
            if len(env_key) == 64:
                return bytes.fromhex(env_key)
            # Base64 representation
            raw = base64.b64decode(env_key)
            if len(raw) == 32:
                return raw
        except Exception:
            raise ValueError('Invalid EMAIL_HMAC_KEY: must be 64‑hex chars or base64‑encoded 32‑byte key')
    # Derive a stable 32‑byte key from the primary encryption key (always available)
    return hmac.new(_ENCRYPTION_KEY, b'email_hmac_key', hashlib.sha256).digest()



def email_hmac(email: str) -> str:
    """Return a deterministic HMAC (hex) for a normalized email address.
    Normalization: stripped, lower‑cased UTF‑8 bytes.
    """
    norm = email.strip().lower().encode('utf-8')
    return hmac.new(_EMAIL_HMAC_KEY, norm, hashlib.sha256).hexdigest()
KEY_ENV_VAR = "RESUMESCOPE_ENCRYPTION_KEY"
SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret.key")
NONCE_LENGTH = 12  # Standard 96-bit nonce for AES-GCM
KEY_LENGTH = 32    # 256-bit key

# Initialize Argon2 Password Hasher (Argon2id default, memory-hard)
_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16
)


def _load_or_generate_encryption_key() -> bytes:
    """
    Retrieves the 256-bit AES encryption key from the environment variable,
    or loads it from a protected local key file outside source control.
    If neither exists, a new cryptographically secure key is generated and saved.
    """
    env_key = os.environ.get(KEY_ENV_VAR)
    if env_key:
        try:
            # Support base64 or hex formatted key
            if len(env_key) == 64:
                return bytes.fromhex(env_key)
            raw = base64.b64decode(env_key)
            if len(raw) == KEY_LENGTH:
                return raw
        except Exception:
            raise ValueError("Invalid EMAIL_HMAC_KEY format: must be 64‑hex characters or base64‑encoded 32‑byte key")

    # Check local key file
    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, "rb") as f:
                key_bytes = f.read().strip()
                if len(key_bytes) == KEY_LENGTH:
                    return key_bytes
                # If stored as base64
                decoded = base64.b64decode(key_bytes)
                if len(decoded) == KEY_LENGTH:
                    return decoded
        except Exception:
            raise ValueError("Invalid EMAIL_HMAC_KEY format: must be 64‑hex characters or base64‑encoded 32‑byte key")

    # Generate a fresh 256-bit key
    new_key = AESGCM.generate_key(bit_length=256)
    try:
        with open(SECRET_KEY_FILE, "wb") as f:
            f.write(base64.b64encode(new_key))
        # Set file permissions if supported (e.g. read/write for owner only)
        try:
            os.chmod(SECRET_KEY_FILE, 0o600)
        except Exception:
            raise ValueError("Invalid EMAIL_HMAC_KEY format: must be 64‑hex characters or base64‑encoded 32‑byte key")
    except Exception:
        pass

    return new_key



_ENCRYPTION_KEY = _load_or_generate_encryption_key()

_EMAIL_HMAC_KEY = _load_email_hmac_key()



def encrypt_data(plaintext: str) -> str:
    """
    Encrypts a plaintext string using AES-256-GCM authenticated encryption.
    Returns a URL-safe Base64 encoded string containing the 12-byte random nonce
    concatenated with the ciphertext and authentication tag.
    
    Args:
        plaintext: The sensitive string to encrypt.
        
    Returns:
        Base64-encoded ciphertext string.
    """
    if plaintext is None:
        return ""
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)

    nonce = secrets.token_bytes(NONCE_LENGTH)
    aesgcm = AESGCM(_ENCRYPTION_KEY)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    
    combined = nonce + ciphertext_and_tag
    return base64.urlsafe_b64encode(combined).decode("ascii")


def decrypt_data(encrypted_b64: str) -> str:
    """
    Decrypts an AES-256-GCM encrypted Base64 string.
    Verifies authentication tag to ensure data integrity and authenticity.
    
    Args:
        encrypted_b64: Base64-encoded string produced by encrypt_data.
        
    Returns:
        Decrypted plaintext string.
        
    Raises:
        ValueError: If decryption fails or data has been tampered with.
    """
    if not encrypted_b64:
        return ""

    try:
        raw = base64.urlsafe_b64decode(encrypted_b64.encode("ascii"))
        if len(raw) <= NONCE_LENGTH:
            raise ValueError("Invalid encrypted payload size")

        nonce = raw[:NONCE_LENGTH]
        ciphertext_and_tag = raw[NONCE_LENGTH:]

        aesgcm = AESGCM(_ENCRYPTION_KEY)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        raise ValueError("Decryption failed or ciphertext was tampered with") from e


def hash_password(password: str) -> str:
    """
    Hashes a password using Argon2id (memory-hard, resistant to GPU/ASIC attacks).
    
    Args:
        password: Raw user password.
        
    Returns:
        Argon2 formatted hash string.
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a plain password against an Argon2 hash.
    Constant-time comparison to prevent timing side-channel attacks.
    """
    if not password or not hashed:
        return False
    try:
        return _password_hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def create_auth_token(user_id: int, username: str, expires_in_seconds: int = 86400) -> str:
    """
    Creates a cryptographically signed authentication token.
    Token format: base64(payload).base64(hmac_signature)
    """
    payload = f"{user_id}:{username}:{int(time.time()) + expires_in_seconds}:{secrets.token_hex(8)}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(_ENCRYPTION_KEY, payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii")
    return f"{payload_b64}.{sig_b64}"


def verify_auth_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the cryptographic signature and expiration of an authentication token.
    Returns user details dict if valid, or None if expired/tampered.
    """
    if not token or "." not in token:
        return None

    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(_ENCRYPTION_KEY, payload_b64.encode("ascii"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_b64.encode("ascii"))

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        parts = payload.split(":")
        if len(parts) < 4:
            return None

        user_id = int(parts[0])
        username = parts[1]
        expires_at = int(parts[2])

        if time.time() > expires_at:
            return None  # Expired

        return {"user_id": user_id, "username": username}
    except Exception:
        return None


def sanitize_log_message(msg: str) -> str:
    """
    Removes emails, phone numbers, passwords, and tokens before logging.
    Ensures application logs remain free of sensitive personal data.
    """
    if not isinstance(msg, str):
        msg = str(msg)
    # Mask emails
    msg = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '[REDACTED_EMAIL]', msg)
    # Mask phone numbers
    msg = re.sub(r'(?:\+?91|0)?[6-9]\d{9}', '[REDACTED_PHONE]', msg)
    # Mask password parameters
    msg = re.sub(r'(password[\'\"]?\s*[:=]\s*[\'\"]?)[^\'\"]+', r'\1[REDACTED_PASS]', msg, flags=re.IGNORECASE)
    # Mask Bearer tokens
    msg = re.sub(r'(Bearer\s+)[A-Za-z0-9._-]+', r'\1[REDACTED_TOKEN]', msg, flags=re.IGNORECASE)
    return msg

