"""Quality-Scores vorher/nachher: alte Config-Schwellen vs. neue (verschaerft).

Usage: python3 tools_quality_compare.py [outfile.json]
Laedt tickers.csv live, wertet mit der aktuellen Config (neu) UND mit den
alten Schwellen (ROIC full 30 %, CAGR full 6 %, FCF-Marge full 20 %) aus.
"""

from __future__ import annotations

import copy
import json
import os
import sys

from config import load_config
from data.providers.base import ProviderError, build_providers, load_with_provider
from data.tickerlist import load_ticker_file
from scoring.pipeline import evaluate_all

OLD_FULL = {"roic_avg5": 0.30, "revenue_cagr_5y": 0.06, "fcf_margin_avg5": 0.20}


def main() -> None:
    cfg = load_config()
    cfg_old = copy.deepcopy(cfg)
    for name, full in OLD_FULL.items():
        cfg_old["criteria"][name]["full"] = full

    providers = build_providers(os.environ.get("FMP_API_KEY", ""))
    tickers = load_ticker_file("tickers.csv") or ["AAPL"]
    companies = []
    for ticker in tickers:
        try:
            companies.append(load_with_provider(ticker, cfg, providers, years=cfg["data"]["years"]))
        except ProviderError as exc:
            print(f"FEHLER {ticker}: {exc}", file=sys.stderr)

    rows_old, excl_old = evaluate_all(companies, cfg_old)
    rows_new, excl_new = evaluate_all(companies, cfg)
    old = {r["ticker"]: r for r in rows_old}
    new = {r["ticker"]: r for r in rows_new}

    print(f"\n{'Ticker':<7} {'Q alt':>7} {'Q neu':>7} {'Δ':>7}   {'Score alt':>9} {'Score neu':>9} {'Δ':>7}   Kandidat")
    print("-" * 80)
    out = []
    for t in sorted(new, key=lambda t: -(new[t]["quality"] if new[t]["quality"] == new[t]["quality"] else -1)):
        ro, rn = old.get(t), new[t]
        qo = ro["quality"] if ro else float("nan")
        vn = rn["value"]
        so = ro["score"] if ro else float("nan")
        dq = "" if qo != qo or rn["quality"] != rn["quality"] else f"{rn['quality'] - qo:+.1f}"
        ds = "" if so != so or rn["score"] != rn["score"] else f"{rn['score'] - so:+.1f}"
        print(f"{t:<7} {qo if qo == qo else float('nan'):>7.1f} {rn['quality']:>7.1f} {dq:>7}   "
              f"{so if so == so else float('nan'):>9.1f} {rn['score']:>9.1f} {ds:>7}   {rn['kandidat'][:60]}")
        out.append({"ticker": t, "quality_old": qo, "quality_new": rn["quality"],
                    "score_old": so, "score_new": rn["score"], "value_new": vn,
                    "kandidat": rn["kandidat"]})
    if excl_new:
        print("\nAusgeschlossen:", ", ".join(e["ticker"] for e in excl_new))
    outfile = sys.argv[1] if len(sys.argv) > 1 else "/tmp/quality_compare.json"
    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"\ngeschrieben: {outfile}")


if __name__ == "__main__":
    main()
