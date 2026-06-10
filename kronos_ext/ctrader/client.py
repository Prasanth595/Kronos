"""Placeholder cTrader client boundary.

No live trading, credentials, API keys, or network calls belong in this
scaffold. Future client code should be dependency-injected and testable with
offline fixtures before any real broker connection is introduced.
"""

from __future__ import annotations


class CTraderClient:
    """Inert placeholder for a future cTrader data client."""

    def fetch_candles(self, *args: object, **kwargs: object) -> None:
        """Reject live data access until an offline-safe client is designed."""

        raise NotImplementedError("Real cTrader connectivity is not implemented.")
