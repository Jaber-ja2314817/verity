"""API keys for the public Verity API (/v1).

A key is "vrt_" plus 43 random URL-safe characters. Only its SHA-256 hash is stored, so a
leaked database does not leak keys; the plaintext is shown once, when the key is created.
Keys are high-entropy random strings, so a plain hash (no salt or slow hash) is enough.
"""

import hashlib
import hmac
import secrets

from pydantic import BaseModel

KEY_PREFIX = "vrt_"
LISTED_PREFIX_CHARS = len(KEY_PREFIX) + 6  # enough to tell keys apart in a list


class ApiKey(BaseModel):
    id: str
    name: str
    prefix: str  # first characters of the key, for listings (never enough to use it)
    created_at: str
    revoked_at: str | None = None
    rate_per_minute: int
    daily_quota: int


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> tuple[str, str]:
    """(plaintext, hash). Show the plaintext once; store only the hash."""
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, hash_key(plaintext)


def bearer_token(header: str | None) -> str | None:
    """The token of an "Authorization: Bearer <token>" header, else None."""
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


def is_admin(header: str | None, secret: str) -> bool:
    """True when the header carries the admin secret. Always False if no secret is set."""
    token = bearer_token(header)
    if not secret or not token:
        return False
    return hmac.compare_digest(token.encode(), secret.encode())
