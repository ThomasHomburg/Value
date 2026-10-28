"""Neues Ranking aller Ticker + Vergleich alt (Baseline) vs. neu, Positionswechsel.

Usage: python3 tools_ranking_compare.py [baseline.json] [outfile.json]
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
    baseline_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/baseline_scores.json"
    outfile = sys.argv[2] if len(sys.argv) > 2 else "new_scores.json"

    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)
    old_scores = {r["ticker"]: r["score"] for r in baseline["rows"]}
    old_excluded = {e["ticker"] for e in baseline["excluded"]}

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
            {"ticker": r["ticker"], "name": r["name"], "score": r["score"],
             "quality": r["quality"], "value": r["value"], "coverage": r["coverage"],
             "flags": r["flags"]}
            for r in rows
        ],
        "excluded": [{"ticker": e["ticker"], "reasons": e["reasons"]} for e in excluded],
    }
    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    old_rank = {r["ticker"]: i for i, r in enumerate(baseline["rows"], 1)}
    print(f"\n{'#neu':>4} {'#alt':>4} {'Ticker':<7} {'alt':>6} {'neu':>6} {'Δ':>7}  Wechsel  Q(neu)  V(neu)  Flags")
    print("-" * 88)
    movers = []
    for i, r in enumerate(rows, 1):
        t = r["ticker"]
        old = old_scores.get(t)
        delta = "" if old is None or old != old or r["score"] != r["score"] else f"{r['score'] - old:+.1f}"
        change = ""
        if t in old_rank and old_rank[t] != i:
            d = old_rank[t] - i
            change = f"↑{d}" if d > 0 else f"↓{-d}"
            movers.append((t, old_rank[t], i, d))
        elif t not in old_rank:
            change = "NEU"
            movers.append((t, None, i, None))
        old_s = "n/a" if old is None or old != old else f"{old:.1f}"
        print(f"{i:>4} {old_rank.get(t, '-'):>4} {t:<7} {old_s:>6} {r['score']:>6.1f} {delta:>7}  {change:<7} "
              f"{r['quality']:>6.1f}  {r['value'] if r['value'] == r['value'] else float('nan'):>6.1f}  {r['flags']}")
    newly_excluded = [e["ticker"] for e in excluded if e["ticker"] in old_scores]
    for t in newly_excluded:
        print(f"     {old_rank.get(t, '-'):>4} {t:<7} AUSGESCHLOSSEN neu")
    print()
    print("Ausgeschlossen (neu):")
    for e in excluded:
        mark = " (vorher bewertet)" if e["ticker"] in old_scores else ""
        print(f"  {e['ticker']}: {'; '.join(e['reasons'])}{mark}")
    print()
    if movers:
        print("Positionswechsel:")
        for t, o, n, d in movers:
            if d is None:
                print(f"  {t}: Platz {o} -> {n} (neu bewertet)")
            else:
                print(f"  {t}: Platz {o} -> {n} ({'↑' if d > 0 else '↓'}{abs(d)})")
    else:
        print("Keine Positionswechsel.")
    print(f"\n{len(rows)} bewertet, {len(excluded)} ausgeschlossen -> {outfile}")


if __name__ == "__main__":
    main()
