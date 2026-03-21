"""RSA-PSS authentication for the Kalshi REST API and WebSocket handshake.

Implements the exact signing algorithm from the Kalshi docs:
    message = timestamp_ms + HTTP_METHOD + path_without_query_params
    signature = RSA-PSS(SHA-256, salt_length=DIGEST_LENGTH)
    encoded = base64(signature)
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes


class KalshiAuth:
    """Produces signed headers for Kalshi API requests.

    Parameters
    ----------
    api_key : str
        The API Key ID shown in your Kalshi account.
    key_path : str | Path
        Filesystem path to the RSA private key (``.key`` / ``.pem``).
    """

    def __init__(self, api_key: str, key_path: str | Path) -> None:
        self.api_key = api_key
        self._private_key: PrivateKeyTypes = self._load_key(key_path)

    # ------------------------------------------------------------------
    # Key loading
    # ------------------------------------------------------------------
    @staticmethod
    def _load_key(key_path: str | Path) -> PrivateKeyTypes:
        with open(key_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _sign(self, message: str) -> str:
        """Sign *message* with RSA-PSS / SHA-256 and return base-64 string."""
        sig = self._private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode("utf-8")

    # ------------------------------------------------------------------
    # Header builders
    # ------------------------------------------------------------------
    def headers(self, method: str, path: str) -> dict[str, str]:
        """Return authentication headers for a REST request.

        Parameters
        ----------
        method : str
            HTTP method in uppercase (``"GET"``, ``"POST"``, etc.).
        path : str
            The request path **including** ``/trade-api/v2`` prefix.
            Query parameters are stripped automatically before signing.
        """
        timestamp = str(int(time.time() * 1000))
        # Per Kalshi docs: strip query parameters before signing
        clean_path = path.split("?")[0]
        sig = self._sign(timestamp + method + clean_path)
        return {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def ws_headers(self) -> dict[str, str]:
        """Return authentication headers for the WebSocket handshake."""
        return self.headers("GET", "/trade-api/ws/v2")
