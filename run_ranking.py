"""Rangliste neu berechnen und als Tabelle ausgeben.

Live-Modus ueber Provider-Schnittstelle (data/providers/): US-Ticker -> FMP
(mit FMP_API_KEY), alle anderen (Suffix .DE/.AS/.PA/.CO ...) -> yfinance
(kein Key noetig). Demo-Daten nur als Fallback, wenn kein Live-Ticker geladen
werden kann. Ticker per Kommandozeile oder tickers.csv.
"""

from __future__ import annotations

import logging
import math
import os
import sys

from config import load_config
from data.demo import demo_companies
from data.metrics import fcf_yield, fcf_yield_sbc
from data.providers.base import ProviderError, build_providers, load_with_provider
from data.loader import country_code
from data.tickerlist import load_ticker_file
from scoring.pipeline import evaluate_all

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("value_screener.ranking")


def _fmt(value: float, spec: str) -> str:
    return "n/a" if math.isnan(value) else format(value, spec)


def main() -> None:
    cfg = load_config()
    api_key = os.environ.get("FMP_API_KEY", "")

    # Provider-Modus: Auswahl per Ticker-Suffix (FMP fuer US, yfinance sonst)
    providers = build_providers(api_key)
    tickers = sys.argv[1:] or load_ticker_file("tickers.csv") or ["AAPL"]
    logger.info("Live-Modus: %d Ticker ueber Provider (%s)", len(tickers), ", ".join(sorted(providers)))
    companies = []
    for ticker in tickers:
        try:
            companies.append(load_with_provider(ticker, cfg, providers, years=cfg["data"]["years"]))
        except ProviderError as exc:
            logger.error("Provider-Fehler bei %s: %s", ticker, exc)
    if not companies:
        logger.info("Kein Live-Ticker geladen -- verwende Demo-Daten.")
        companies = demo_companies()

    rows, excluded = evaluate_all(companies, cfg)

    print(f"\n=== Rangliste (Quality/Value getrennt, renormalisiert) – "
          f"{len(rows)} bewertet, {len(excluded)} ausgeschlossen "
          f"({len(rows) + len(excluded)} Ticker gesamt) ===")
    header = (f"{'Ticker':<10} {'Name':<30} {'Sektor':<16} {'Land':<4} {'Quelle':<8} "
              f"{'Score':>6} {'Quality':>7} {'Value':>6} {'Datenabdeckung':>14} "
              f"{'FCF-Yield':>9} {'FCF-Yld n.SBC':>12} {'FCF-Yld n.SBC 3J':>16} {'ROIC 5J':>8} {'ND/EBITDA':>9} {'MoS Base':>8}  Flags")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['ticker']:<10} {r['name'][:30]:<30} {r['sector'][:16]:<16} {country_code(r['country']):<4} {r['source']:<8} "
            f"{_fmt(r['score'], '>6.1f')} "
            f"{_fmt(r['quality'], '>7.1f')} "
            f"{_fmt(r['value'], '>6.1f')} "
            f"{_fmt(r['coverage'], '>14.1%')} "
            f"{_fmt(r['fcf_yield'], '>9.1%')} "
            f"{_fmt(r['fcf_yield_sbc'], '>12.1%')} "
            f"{_fmt(r['fcf_yield_3y'], '>16.1%')} "
            f"{_fmt(r['roic_5y'], '>8.1%')} "
            f"{_fmt(r['nd_ebitda'], '>9.2f')} "
            f"{_fmt(r['margin_of_safety'], '>8.1%')}  {r['flags']}"
        )
    buys = [r["ticker"] for r in rows if r.get("is_buy")]
    if buys:
        print(f"\nKaufkandidaten: {', '.join(buys)}")

    # Vorher/Nachher fuer AAPL zeigen
    aapl = next((m for m in companies if m.ticker == "AAPL"), None)
    if aapl is not None:
        latest_fy = max(aapl.years)
        fixed = fcf_yield(aapl, latest_fy)
        buggy = aapl.years[latest_fy]["fcf"].value / (aapl.market_cap.value / 1e6)
        print(f"\nAAPL FY{latest_fy}: FCF-Yield vorher (Bug, Mio.-Skalierung) = {buggy:.1%}")
        print(f"AAPL FY{latest_fy}: FCF-Yield nachher (Fix, absolute USD)     = {fixed:.1%}")


if __name__ == "__main__":
    main()
