"""Temporary password generation for admin-provisioned users."""

from __future__ import annotations

import secrets
import string


_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_DIGITS = string.digits
_SPECIAL = "!@#$%^&*-_=+"
_ALL = _UPPER + _LOWER + _DIGITS + _SPECIAL


def generate_temporary_password(length: int = 16) -> str:
    """
    Generate a temporary password for a newly invited native user.

    Guarantees at least one uppercase, lowercase, digit, and special character.
    Mixes `secrets.token_urlsafe` entropy into the remaining character pool.
    """
    if length < 8:
        length = 16

    required = [
        secrets.choice(_UPPER),
        secrets.choice(_LOWER),
        secrets.choice(_DIGITS),
        secrets.choice(_SPECIAL),
    ]
    leftover = length - len(required)
    # token_urlsafe(12) yields ~16 url-safe chars; fold into the charset pool.
    entropy = secrets.token_urlsafe(12)
    mixed = [ch for ch in entropy if ch in _ALL]
    while len(mixed) < leftover:
        mixed.append(secrets.choice(_ALL))
    chars = required + mixed[:leftover]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
