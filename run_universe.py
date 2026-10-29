"""Universumslader CLI (v28, Schritt 8): S&P 500 oder STOXX 600 laden.

Aufruf:
    python run_universe.py sp500 [--refresh]     # Wikipedia -> tickers_sp500.csv
    python run_universe.py stoxx600 [--csv PFAD] # CSV-Import

Abruf in Batches (config universe.batch_size) mit Pause, Fortschrittsanzeige
(pro Ticker), Wiederaufnahme nach Abbruch (Cache .universe_cache.json) und
Fehlerlog je Ticker (ein Fehler stoppt den Lauf nicht). Ergebnis: Rangliste
wie run_ranking.py.
"""

from __future__ import annotations

import logging
import sys

from config import load_config
from data.tickerlist import load_ticker_file
from data.universe import load_sp500_tickers, load_stoxx600_tickers, load_universe
from scoring.pipeline import evaluate_all, rank_rows

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
                    stream=sys.stderr)
logger = logging.getLogger("value_screener.universe_cli")


def main() -> None:
    cfg = load_config()
    ucfg = cfg.get("universe", {})
    args = sys.argv[1:]
    if not args or args[0] not in ("sp500", "stoxx600"):
        print(__doc__)
        sys.exit(1)
    kind = args[0]
    if kind == "sp500":
        refresh = "--refresh" in args
        tickers = load_sp500_tickers(ucfg.get("sp500_csv", "tickers_sp500.csv"),
                                     ucfg.get("sp500_wikipedia_url", ""),
                                     refresh=refresh)
    else:
        csv_path = ucfg.get("stoxx600_csv", "tickers_stoxx600.csv")
        if "--csv" in args:
            csv_path = args[args.index("--csv") + 1]
        tickers = load_stoxx600_tickers(csv_path)

    companies, errors = load_universe(tickers, cfg)
    print(f"\nUniversum {kind.upper()}: {len(companies)} geladen, {len(errors)} Fehler "
          f"(von {len(tickers)})")
    if errors:
        print("Fehlerlog:")
        for e in errors:
            print(f"  {e['ticker']}: {e['error'][:100]}")

    rows, excluded = evaluate_all(companies, cfg)
    rows.sort(key=lambda r: (1 if r.get("is_buy") else 0,
                             r["margin_of_safety"] if r["margin_of_safety"] == r["margin_of_safety"] else -1),
              reverse=True)
    print(f"\n=== Rangliste {kind.upper()} -- {len(rows)} bewertet, "
          f"{len(excluded)} ausgeschlossen ===")
    print(f"{'Ticker':<8} {'Name':<28} {'Score':>6} {'Quality':>7} {'Value':>6} "
          f"{'MoS Base':>8}  Status / Flags")
    for r in rows[:50]:
        print(f"{r['ticker']:<8} {r['name'][:28]:<28} {r['score']:>6.1f} "
              f"{r['quality']:>7.1f} {r['value']:>6.1f} "
              f"{r['margin_of_safety']:>8.1%}  {r['status']} | {r['flags']}")


if __name__ == "__main__":
    main()
