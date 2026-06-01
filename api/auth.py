"""
auth.py - Authentication helpers for Snowflake REST API.

Supports three methods:
  1. Key-Pair JWT authentication (recommended for production).
  2. OAuth token (for integrations with an IdP).
  3. Personal Access Token / password (development only).
"""

from __future__ import annotations

import base64
import hashlib
import time
from enum import Enum
from pathlib import Path
from typing import Optional

import jwt  # PyJWT
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from .config import Settings


class AuthMethod(str, Enum):
    KEY_PAIR = "key_pair"
    OAUTH = "oauth"
    PAT = "pat"


# -- Helper: compute the public-key fingerprint --------------------------------
def _public_key_fingerprint(
    private_key_path: str,
    private_key_passphrase: Optional[str] = None,
) -> str:
    """Return the SHA-256 fingerprint of the RSA public key (Base64-encoded)."""
    pw_bytes: Optional[bytes] = (
        private_key_passphrase.encode() if private_key_passphrase else None
    )
    pem_bytes = Path(private_key_path).read_bytes()
    private_key = load_pem_private_key(pem_bytes, pw_bytes, backend=default_backend())
    public_key = private_key.public_key()
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(pub_bytes).digest()
    return "SHA256:" + base64.b64encode(digest).decode()


# -- Key-Pair JWT token --------------------------------------------------------
def generate_keypair_jwt(settings: Settings) -> str:
    """
    Generate a short-lived JWT for Snowflake key-pair authentication.
    The token is valid for 59 minutes (Snowflake maximum).
    """
    if not settings.snowflake_private_key_path:
        raise ValueError("SNOWFLAKE_PRIVATE_KEY_PATH must be set for key_pair auth.")

    passphrase = settings.snowflake_private_key_passphrase
    pw_bytes: Optional[bytes] = passphrase.encode() if passphrase else None
    pem_bytes = Path(settings.snowflake_private_key_path).read_bytes()
    private_key = load_pem_private_key(pem_bytes, pw_bytes, backend=default_backend())

    account = settings.snowflake_account.upper()
    user = settings.snowflake_user.upper()
    fingerprint = _public_key_fingerprint(
        settings.snowflake_private_key_path,
        passphrase,
    )

    qualified_username = f"{account}.{user}"
    now = int(time.time())
    payload = {
        "iss": f"{qualified_username}.{fingerprint}",
        "sub": qualified_username,
        "iat": now,
        "exp": now + 59 * 60,  # 59 minutes
    }

    token: str = jwt.encode(payload, private_key, algorithm="RS256")
    return token


# -- Build Authorization header ------------------------------------------------
def get_auth_header(settings: Settings) -> dict[str, str]:
    """Return the Authorization header dict for the configured auth method."""
    method = settings.snowflake_auth_method

    if method == AuthMethod.KEY_PAIR:
        token = generate_keypair_jwt(settings)
        return {
            "Authorization": "Bearer " + token,
            "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        }

    if method == AuthMethod.OAUTH:
        if not settings.snowflake_oauth_token:
            raise ValueError("SNOWFLAKE_OAUTH_TOKEN must be set for oauth auth.")
        return {
            "Authorization": "Bearer " + settings.snowflake_oauth_token,
            "X-Snowflake-Authorization-Token-Type": "OAUTH",
        }

    if method == AuthMethod.PAT:
        if not settings.snowflake_password:
            raise ValueError("SNOWFLAKE_PASSWORD must be set for pat auth.")
        return {
            "Authorization": "Bearer " + settings.snowflake_password,
            "X-Snowflake-Authorization-Token-Type": "SNOWFLAKE_JWT",
        }

    raise ValueError(f"Unsupported auth method: {method}")
