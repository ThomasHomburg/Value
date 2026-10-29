"""Provider-Basisklasse und Auswahl-Logik (Suffix oder Config)."""

from __future__ import annotations

import logging
import re
from typing import Protocol

from data.fmp_client import FMPClient
from data.loader import TickerMetrics

logger = logging.getLogger("value_screener.providers")

_SUFFIX_RE = re.compile(r"^(?P<base>[A-Z0-9][A-Z0-9.\-_]*)\.(?P<suffix>[A-Z]{1,2})$")


class ProviderError(RuntimeError):
    """Provider konnte die Daten nicht liefern."""


class Provider(Protocol):
    """Einheitliche Schnittstelle: liefert TickerMetrics (normalisiertes Schema)."""

    name: str

    def supports(self, ticker: str) -> bool: ...

    def load(self, ticker: str, years: int = 5) -> TickerMetrics: ...


def split_suffix(ticker: str) -> tuple[str, str | None]:
    """Zerlegt 'NOVO-B.CO' -> ('NOVO-B', '.CO'); 'AAPL' -> ('AAPL', None)."""
    m = _SUFFIX_RE.match(ticker.upper())
    if m:
        return m.group("base"), "." + m.group("suffix")
    return ticker.upper(), None


def select_provider(
    ticker: str,
    cfg: dict,
    providers: dict[str, Provider],
) -> Provider:
    """Waehlt den Provider fuer einen Ticker.

    Reihenfolge: providers.force (Config) > Suffix-Match > US->FMP (falls konfiguriert)
    > providers.default. Loggt die Wahl pro Ticker.
    """
    pcfg = cfg.get("providers", {})
    force = (pcfg.get("force") or "").strip().lower()
    if force:
        if force not in providers:
            raise ProviderError(f"Provider '{force}' (force) nicht verfuegbar: {sorted(providers)}")
        logger.info("%s: Quelle=%s (erzwungen per Config)", ticker, force)
        return providers[force]

    _base, suffix = split_suffix(ticker)
    suffix_map = {k.upper(): v.lower() for k, v in (pcfg.get("suffix_map") or {}).items()}

    if suffix and suffix.upper() in suffix_map:
        name = suffix_map[suffix.upper()]
    elif suffix:
        name = (pcfg.get("default") or "yfinance").lower()
    else:
        fmp = providers.get("fmp")
        if pcfg.get("fmp_when_no_suffix", True) and fmp is not None:
            name = "fmp"
        else:
            name = (pcfg.get("default") or "yfinance").lower()

    if name not in providers:
        raise ProviderError(f"Provider '{name}' nicht verfuegbar: {sorted(providers)}")
    logger.info("%s: Quelle=%s (Suffix=%s)", ticker, name, suffix or "kein/US")
    return providers[name]


def build_providers(fmp_api_key: str = "") -> dict[str, Provider]:
    """Erzeugt das Provider-Registry. FMP nur wenn API-Key gesetzt."""
    from data.providers.fmp import FmpProvider
    from data.providers.yfinance_provider import YfinanceProvider

    registry: dict[str, Provider] = {"yfinance": YfinanceProvider()}
    if fmp_api_key:
        registry["fmp"] = FmpProvider(FMPClient(fmp_api_key))
    return registry


def load_with_provider(ticker: str, cfg: dict, providers: dict[str, Provider],
                       years: int = 5) -> TickerMetrics:
    """Laedt einen Ticker ueber den passenden Provider; Quelle wird geloggt."""
    provider = select_provider(ticker, cfg, providers)
    metrics = provider.load(ticker, years=years)
    metrics.source = provider.name
    return metrics
