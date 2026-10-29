"""Provider-Schnittstelle fuer Fundamentaldaten.

Alle Provider liefern dasselbe normalisierte Schema: TickerMetrics
(data/loader.py) mit Einheit, Waehrung, Berichtsjahr und Quelle (source).

Auswahl: data/providers/base.py -> select_provider()
  - Ticker-Suffix (.DE, .AS, .PA, .CO ...) -> suffix_map in config.yaml
  - US-Ticker ohne Suffix -> FMP (falls API-Key gesetzt), sonst yfinance
  - Config-Override: providers.force erzwingt einen Provider fuer alle Ticker
"""

from data.providers.base import Provider, ProviderError, select_provider
from data.providers.fmp import FmpProvider
from data.providers.yfinance_provider import YfinanceProvider

__all__ = [
    "Provider",
    "ProviderError",
    "FmpProvider",
    "YfinanceProvider",
    "select_provider",
]
