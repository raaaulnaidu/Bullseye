"""
privacy_processor.py
--------------------
Anonymizes student PII locally before any text is sent to Claude.
Replaces: student name, ID numbers, email addresses, course codes, phone numbers.
"""

import re
from typing import Tuple, List

_EMAIL_RE     = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')
_STUDENT_ID_RE = re.compile(r'\b\d{7,10}\b')
_COURSE_CODE_RE = re.compile(r'\b(CAI|ISM|MAN|FIN|MKT|QMB|BUL|STA|CGS)\s*\d{4}\b', re.IGNORECASE)
_PHONE_RE     = re.compile(r'\b(\+1[\-.\s]?)?\(?\d{3}\)?[\-.\s]?\d{3}[\-.\s]?\d{4}\b')


def anonymize(text: str, known_name: str = "") -> Tuple[str, List[str]]:
    """
    Strip PII from a student submission.

    Args:
        text:        Raw extracted submission text.
        known_name:  Student name inferred from filename (e.g. "Alice Johnson").

    Returns:
        anonymized_text: Text with PII replaced by placeholders.
        log:             Human-readable list of what was replaced (for audit).
    """
    log: List[str] = []

    # Known student name from filename — split into parts and remove each
    if known_name:
        for part in known_name.split():
            if len(part) > 2:
                pat = re.compile(re.escape(part), re.IGNORECASE)
                count = len(pat.findall(text))
                if count:
                    text = pat.sub("[STUDENT]", text)
                    log.append(f"Name '{part}' → [STUDENT] ({count}x)")

    # Email addresses
    found = _EMAIL_RE.findall(text)
    if found:
        text = _EMAIL_RE.sub("[EMAIL]", text)
        log.append(f"Email(s) → [EMAIL] ({len(found)}x)")

    # 7-10 digit numeric student IDs
    found = _STUDENT_ID_RE.findall(text)
    if found:
        text = _STUDENT_ID_RE.sub("[ID]", text)
        log.append(f"Student ID(s) → [ID] ({len(found)}x)")

    # Course codes (e.g. CAI 3801, ISM 6145)
    found = _COURSE_CODE_RE.findall(text)
    if found:
        text = _COURSE_CODE_RE.sub("[COURSE]", text)
        log.append(f"Course code(s) → [COURSE] ({len(found)}x)")

    # Phone numbers
    found = _PHONE_RE.findall(text)
    if found:
        text = _PHONE_RE.sub("[PHONE]", text)
        log.append(f"Phone(s) → [PHONE] ({len(found)}x)")

    return text, log
