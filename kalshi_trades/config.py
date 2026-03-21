"""Environment-aware configuration for Kalshi API connections."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------
PROD_REST_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_REST_BASE = "https://demo-api.kalshi.co/trade-api/v2"

PROD_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"


@dataclass(frozen=True)
class Config:
    """Immutable configuration container.

    Parameters
    ----------
    env : str
        ``"prod"`` or ``"demo"``.  Controls which URLs and ``.env`` file are
        used.
    env_file : Path | None
        Explicit path to a ``.env`` file.  When *None* the default is
        ``.env`` for prod and ``.env.demo`` for demo.
    api_key : str | None
        Kalshi API key ID.  Loaded from the environment variable
        ``KALSHI_API_KEY_ID`` when *None*.
    private_key_path : Path | None
        Path to the RSA private key file.  Loaded from the environment
        variable ``KALSHI_PRIVATE_KEY_PATH`` when *None*.
    """

    env: str = "demo"
    env_file: Path | None = None
    api_key: str | None = field(default=None, repr=False)
    private_key_path: Path | None = None

    # Resolved at post-init ------------------------------------------------
    rest_base: str = field(init=False, repr=True)
    ws_url: str = field(init=False, repr=True)
    _api_key: str = field(init=False, repr=False)
    _private_key_path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.env not in ("prod", "demo"):
            raise ValueError(f"env must be 'prod' or 'demo', got {self.env!r}")

        # Load .env ----------------------------------------------------------
        dotenv_path = self.env_file
        if dotenv_path is None:
            dotenv_path = Path(".env") if self.env == "prod" else Path(".env.demo")
        load_dotenv(dotenv_path=dotenv_path, override=True)

        # URLs ---------------------------------------------------------------
        object.__setattr__(
            self,
            "rest_base",
            PROD_REST_BASE if self.env == "prod" else DEMO_REST_BASE,
        )
        object.__setattr__(
            self,
            "ws_url",
            PROD_WS_URL if self.env == "prod" else DEMO_WS_URL,
        )

        # Credentials --------------------------------------------------------
        resolved_key = self.api_key or os.environ.get("KALSHI_API_KEY_ID", "")
        resolved_path = self.private_key_path or Path(
            os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        )
        object.__setattr__(self, "_api_key", resolved_key)
        object.__setattr__(self, "_private_key_path", resolved_path)

    def get_api_key(self) -> str:
        """Return the resolved API key ID."""
        if not self._api_key:
            raise RuntimeError(
                "API key not set. Provide api_key= or set KALSHI_API_KEY_ID."
            )
        return self._api_key

    def get_private_key_path(self) -> Path:
        """Return the resolved private-key file path."""
        if not str(self._private_key_path):
            raise RuntimeError(
                "Private key path not set. Provide private_key_path= "
                "or set KALSHI_PRIVATE_KEY_PATH."
            )
        return self._private_key_path
