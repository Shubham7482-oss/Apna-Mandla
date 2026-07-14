"""
app/core/otp_security.py

OTP hashing helpers — thin wrappers around app.core.security.

Background on algorithm choice:
  bcrypt is designed for long-lived secrets (passwords).
  OTPs are short-lived (5-10 min) and single-use, so bcrypt's cost factor
  adds unnecessary latency without improving security.

  This module delegates to the SHA-256 + HMAC approach in core.security,
  keeping one canonical implementation across the codebase.

  Both function names exported here match the signatures that routes expect:
    hash_otp(otp)              → hex string
    verify_otp_hash(otp, hash) → bool
"""

from app.core.security import hash_otp, verify_otp


def verify_otp_hash(plain_otp: str, hashed_otp: str) -> bool:
    """
    Verify a plain OTP against a stored SHA-256 hash.

    Alias for app.core.security.verify_otp with the name that auth routes use.
    Uses constant-time comparison internally to prevent timing attacks.
    """
    return verify_otp(plain_otp, hashed_otp)


# Re-export hash_otp so callers that import from this module still work.
__all__ = ["hash_otp", "verify_otp_hash"]
