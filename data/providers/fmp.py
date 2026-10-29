"""FMP-Provider: US-Ticker ueber die Financial Modeling Prep API.

Liefert das normalisierte Schema (TickerMetrics) mit Quelle 'fmp'.
"""

from __future__ import annotations

import logging

from data.fmp_client import FMPClient, FMPError
from data.loader import DataLoader, TickerMetrics
from data.providers.base import ProviderError

logger = logging.getLogger("value_screener.providers.fmp")


class FmpProvider:
    """Provider fuer FMP (US-Ticker; Statements in reportedCurrency, absolut)."""

    name = "fmp"

    def __init__(self, client: FMPClient) -> None:
        self.client = client
        self._loader = DataLoader(client)

    def supports(self, ticker: str) -> bool:
        return self.client.configured

    def load(self, ticker: str, years: int = 5) -> TickerMetrics:
        if not self.client.configured:
            raise ProviderError("FMP: kein FMP_API_KEY gesetzt.")
        try:
            metrics = self._loader.load_ticker(ticker)
        except FMPError as exc:
            raise ProviderError(f"FMP: {exc}") from exc
        metrics.source = self.name
        logger.info("%s: %d Jahre von FMP geladen", ticker, len(metrics.years))
        return metrics
