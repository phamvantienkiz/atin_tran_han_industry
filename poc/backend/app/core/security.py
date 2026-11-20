"""Security helpers (JWT / hashing placeholders for ATIN IAM & standalone auth)."""

from __future__ import annotations

import hmac


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two secret strings in constant time."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))
