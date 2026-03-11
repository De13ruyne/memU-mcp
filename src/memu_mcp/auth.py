"""Authentication error type for memU Cloud API."""

from __future__ import annotations


class AuthError(Exception):
    """Raised when API authentication fails (HTTP 401)."""
