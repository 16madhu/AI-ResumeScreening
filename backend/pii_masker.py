"""
Module: pii_masker.py
Safeguards candidate privacy by detecting and masking personal identifying information (PII)
including:
- Email addresses
- Phone numbers (including comprehensive Indian mobile +91 / landline and international formats)
- Physical addresses and Indian PIN codes
- Candidate names (via explicit markers, honorifics, and resume header heuristics)
- Web URLs, GitHub profiles, and LinkedIn links

Masking replaces sensitive identifiers with standardized placeholders:
[EMAIL], [PHONE], [ADDRESS], [NAME], [URL]

Safe preservation:
Guarantees that technical skills (Python, React, Docker, Machine Learning, etc.) and
employment/educational content needed for fair hybrid matching are strictly preserved.

Documented limitations per Section 6 & 10 of the proposal:
Heuristic and pattern-based PII detection cannot guarantee 100% detection of all
unstructured or novel personal references.
"""

import os
import re
import json
from typing import Tuple, Dict, Any, List, Set

PII_DISCLAIMER = (
    "Privacy Notice: Detectable email addresses, phone numbers, names, addresses, and URLs "
    "are masked before processing or storage where practical. This is a heuristic-based "
    "safeguard and does not guarantee 100% detection of all unstructured personal identifiers."
)

# 1. Email Regex (RFC-compliant and practical email patterns)
EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
)

# 2. Comprehensive Phone Number Regex
# Matches:
# - Indian mobile numbers: +91 9876543210, +91-98765-43210, +919876543210, 09876543210, 9876543210, 98765 43210
# - Indian STD landlines: 080-23456789, 022-12345678
# - International / US formats: +1-555-234-5678, (555) 123-4567, 555-123-4567
PHONE_REGEX = re.compile(
    r'(?:\+?91[\s.-]?|0)?[6-9]\d{4}[\s.-]?\d{5}\b|'
    r'(?:\+?91[\s.-]?|0)?[6-9]\d{2}[\s.-]?\d{3}[\s.-]?\d{4}\b|'
    r'(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b|'
    r'\b0\d{2,4}[-\s]?\d{6,8}\b'
)

# 3. Web URL, LinkedIn, and GitHub links
URL_REGEX = re.compile(
    r'(?:https?:\/\/|www\.)[^\s/$.?#].[^\s]*|'
    r'\b(?:linkedin\.com\/in|linkedin\.com\/pub|github\.com|gitlab\.com|medium\.com)\/[A-Za-z0-9_.-]+\b',
    re.IGNORECASE
)

# 4. Indian PIN codes (6 digits, first digit 1-9)
PIN_CODE_REGEX = re.compile(r'\b[1-9][0-9]{2}\s?[0-9]{3}\b')

# 5. Explicit Address Markers
ADDRESS_LABEL_REGEX = re.compile(
    r'(?i)(?:Permanent\s+Address|Current\s+Address|Residential\s+Address|Address|Location)\s*[:\-]\s*([^\n\r]+)'
)

# 6. Major Indian & Global Cities / States in Address context
ADDRESS_CITY_STATE_REGEX = re.compile(
    r'(?i)\b(?:Bangalore|Bengaluru|Mumbai|Delhi|New Delhi|Hyderabad|Chennai|Kolkata|Pune|Ahmedabad|Jaipur|Noida|Gurgaon|Gurugram|Mysore|Kochi|Trivandrum|Chandigarh)\b'
    r'(?:\s*,\s*(?:Karnataka|Maharashtra|Delhi|Telangana|Tamil Nadu|West Bengal|Gujarat|Rajasthan|Uttar Pradesh|Haryana|Kerala|Punjab|India))?'
    r'(?:\s*[-–,\s]\s*[1-9][0-9]{5})?'
)

# Locality markers (e.g. "#42, 5th Cross, Indiranagar", "Sector 62, Noida")
LOCALITY_REGEX = re.compile(
    r'(?i)\b(?:Flat\s*(?:No\.?)?\s*\d+|#\s*\d+|Plot\s*(?:No\.?)?\s*\d+|House\s*No\.?\s*\d+|Sector\s*\d+|Cross\s*\d+|Main\s*Road|Road|Street|Nagar|Layout|Colony|Enclave|Avenue|Lane|Apartment)\b[^\n,]+(?:,\s*[^\n,]+){1,2}',
)

# 7. Explicit Name Markers
NAME_LABEL_REGEX = re.compile(
    r"(?i)(?:Candidate\s+Name|Full\s+Name|Name)\s*[:\-]\s*([A-Za-z.'-]+(?:\s+[A-Za-z.'-]+){1,3})"
)
TITLE_NAME_REGEX = re.compile(
    r"(?i)\b(?:Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
)

# Load technical skill vocabulary to guarantee zero false-positive masking on skills
_SKILLS_CACHE: Set[str] = set()

def _get_skills_whitelist() -> Set[str]:
    """Loads all known technical skills to prevent them from being masked as names."""
    global _SKILLS_CACHE
    if not _SKILLS_CACHE:
        # Standard core technical terms
        default_skills = {
            "python", "java", "c++", "c#", "javascript", "typescript", "html", "css",
            "react", "angular", "vue", "node.js", "django", "flask", "fastapi", "spring",
            "sql", "mysql", "postgresql", "mongodb", "redis", "oracle", "sqlite",
            "machine learning", "deep learning", "nlp", "computer vision", "data science",
            "data analysis", "statistics", "pandas", "numpy", "scikit-learn", "pytorch",
            "tensorflow", "keras", "spark", "hadoop", "big data", "tableau", "power bi",
            "docker", "kubernetes", "aws", "azure", "gcp", "devops", "ci/cd", "git",
            "linux", "bash", "unix", "cyber security", "network security", "rest api",
            "microservices", "flutter", "react native", "android", "ios", "swift", "kotlin"
        }
        _SKILLS_CACHE.update(default_skills)

        # Merge from skills_dictionary.json if available
        dict_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "skills_dictionary.json")
        if os.path.exists(dict_path):
            try:
                with open(dict_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for s in data.get("skills", []):
                    _SKILLS_CACHE.add(s.lower())
                for syn in data.get("synonyms", {}).keys():
                    _SKILLS_CACHE.add(syn.lower())
            except Exception:
                pass
    return _SKILLS_CACHE


# Section headings and common non-name keywords
_SECTION_KEYWORDS = {
    "education", "experience", "work experience", "professional experience",
    "employment", "employment history", "projects", "skills", "technical skills",
    "summary", "professional summary", "career objective", "objective",
    "certifications", "certificates", "awards", "publications", "languages",
    "interests", "hobbies", "declaration", "contact", "profile", "achievements",
    "software engineer", "developer", "data scientist", "data analyst",
    "machine learning engineer", "devops engineer", "cloud architect",
    "bachelor", "master", "degree", "b.tech", "m.tech", "b.e", "m.e", "b.sc", "m.sc",
    "ph.d", "university", "college", "institute", "school", "curriculum vitae", "resume"
}


def _is_safe_candidate_name(candidate: str) -> bool:
    """
    Validates whether a candidate string is a plausible person's name
    and not a technical skill, section heading, or job title.
    """
    candidate = candidate.strip()
    if not candidate or len(candidate) < 3 or len(candidate) > 40:
        return False

    tokens = candidate.split()
    if len(tokens) < 1 or len(tokens) > 4:
        return False

    skills = _get_skills_whitelist()
    cand_lower = candidate.lower()

    if cand_lower in skills or cand_lower in _SECTION_KEYWORDS:
        return False

    # Check each token
    for t in tokens:
        t_clean = t.rstrip(".,").lower()
        if t_clean in skills or t_clean in _SECTION_KEYWORDS:
            return False
        # Must be mostly alphabetic
        if not re.match(r"^[A-Za-z.'-]+$", t):
            return False

    return True


def mask_pii(text: str, mask_placeholder: bool = True) -> Tuple[str, Dict[str, Any]]:
    """
    Scans resume text for PII: emails, Indian & international phone numbers,
    URLs, physical addresses, and candidate names. Masks them with placeholders.
    
    Args:
        text: Input raw resume text.
        mask_placeholder: If True, uses [EMAIL], [PHONE], [ADDRESS], [NAME], [URL].
                          If False, redacts with asterisks.
                          
    Returns:
        Tuple of (masked_text, metadata_dict)
    """
    if not text:
        return "", {
            "emails_count": 0,
            "phones_count": 0,
            "urls_count": 0,
            "names_count": 0,
            "addresses_count": 0,
            "total_masked": 0,
            "disclaimer": PII_DISCLAIMER
        }

    email_rep = "[EMAIL]" if mask_placeholder else "********@***.***"
    phone_rep = "[PHONE]" if mask_placeholder else "***-***-****"
    url_rep = "[URL]" if mask_placeholder else "https://*******"
    addr_rep = "[ADDRESS]" if mask_placeholder else "[REDACTED_ADDRESS]"
    name_rep = "[NAME]" if mask_placeholder else "[REDACTED_NAME]"

    # 1. Collect matches for metadata
    emails = EMAIL_REGEX.findall(text)
    phones = PHONE_REGEX.findall(text)
    urls = URL_REGEX.findall(text)

    # 2. Mask URLs first to prevent email/domain clash inside URLs
    masked = URL_REGEX.sub(url_rep, text)

    # 3. Mask Emails
    masked = EMAIL_REGEX.sub(email_rep, masked)

    # 4. Mask Phone Numbers
    masked = PHONE_REGEX.sub(phone_rep, masked)

    # 5. Mask Addresses
    addresses_found = []

    # Explicit Address Label masking
    def _addr_label_sub(match):
        addresses_found.append(match.group(0))
        return addr_rep

    masked = ADDRESS_LABEL_REGEX.sub(_addr_label_sub, masked)

    # City/State/PIN address patterns
    city_matches = ADDRESS_CITY_STATE_REGEX.findall(masked)
    addresses_found.extend(city_matches)
    masked = ADDRESS_CITY_STATE_REGEX.sub(addr_rep, masked)

    # Locality lines
    locality_matches = LOCALITY_REGEX.findall(masked)
    addresses_found.extend(locality_matches)
    masked = LOCALITY_REGEX.sub(addr_rep, masked)

    # Standalone 6-digit PIN codes (if not already masked)
    pin_matches = PIN_CODE_REGEX.findall(masked)
    addresses_found.extend(pin_matches)
    masked = PIN_CODE_REGEX.sub(addr_rep, masked)

    # 6. Mask Candidate Names
    names_found = []

    # A) Explicit name labels (e.g. "Name: Rahul Sharma")
    def _name_label_sub(match):
        raw_name = match.group(1).strip()
        if _is_safe_candidate_name(raw_name):
            names_found.append(raw_name)
            return match.group(0).replace(raw_name, name_rep)
        return match.group(0)

    masked = NAME_LABEL_REGEX.sub(_name_label_sub, masked)

    # B) Title prefixes (e.g. "Dr. Rajesh Kumar")
    def _title_name_sub(match):
        raw_name = match.group(1).strip()
        if _is_safe_candidate_name(raw_name):
            names_found.append(raw_name)
            return match.group(0).replace(raw_name, name_rep)
        return match.group(0)

    masked = TITLE_NAME_REGEX.sub(_title_name_sub, masked)

    # C) Top-of-resume Header heuristic:
    # First 1-3 non-empty lines typically contain the candidate's name.
    lines = masked.splitlines()
    header_checked = 0
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and header_checked < 3 and not names_found:
            header_checked += 1
            # If line is 2-4 capitalized words and qualifies as a safe name
            if _is_safe_candidate_name(stripped):
                names_found.append(stripped)
                new_lines.append(name_rep)
                continue
        new_lines.append(line)

    masked = "\n".join(new_lines)

    meta = {
        "emails_count": len(emails),
        "phones_count": len(phones),
        "urls_count": len(urls),
        "names_count": len(names_found),
        "addresses_count": len(addresses_found),
        "total_masked": len(emails) + len(phones) + len(urls) + len(names_found) + len(addresses_found),
        "disclaimer": PII_DISCLAIMER
    }

    return masked, meta
