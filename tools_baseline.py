"""Baseline: alte Scores aller geladenen Ticker sichern (vor den Edits).

Usage: python3 tools_baseline.py [outfile]
Laedt tickers.csv live (yfinance/FMP), wertet aus und schreibt JSON.
"""

from __future__ import annotations

import json
import os
import sys

from config import load_config
from data.providers.base import ProviderError, build_providers, load_with_provider
from data.tickerlist import load_ticker_file
from scoring.pipeline import evaluate_all


def main() -> None:
    cfg = load_config()
    providers = build_providers(os.environ.get("FMP_API_KEY", ""))
    tickers = load_ticker_file("tickers.csv") or ["AAPL"]
    companies = []
    for ticker in tickers:
        try:
            companies.append(load_with_provider(ticker, cfg, providers, years=cfg["data"]["years"]))
        except ProviderError as exc:
            print(f"FEHLER {ticker}: {exc}", file=sys.stderr)
    rows, excluded = evaluate_all(companies, cfg)
    out = {
        "rows": [
            {
                "ticker": r["ticker"], "name": r["name"], "score": r["score"],
                "quality": r["quality"], "value": r["value"], "coverage": r["coverage"],
                "flags": r["flags"],
            }
            for r in rows
        ],
        "excluded": [{"ticker": e["ticker"], "reasons": e["reasons"]} for e in excluded],
    }
    outfile = sys.argv[1] if len(sys.argv) > 1 else "baseline_scores.json"
    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"{len(rows)} bewertet, {len(excluded)} ausgeschlossen -> {outfile}")
    for r in rows:
        print(f"{r['ticker']:<6} score={r['score']:.1f}  Q={r['quality']:.1f}  V={r['value']:.1f}  flags={r['flags']}")


if __name__ == "__main__":
    main()
