"""v35 Testlauf: dieselben 25 Ticker wie im letzten Lauf (Seed 42), live.

Erzeugt testlauf_25.csv (mit neuen Spalten Industry-Gruppe + SEC-Detail) und
testlauf_fehler.txt (Fehler + Datenqualitaet je Ticker). Kein Volllauf.
"""
import csv
import logging
import math
import sys

sys.path.insert(0, ".")

from config import load_config
from data.providers.base import build_providers, load_with_provider
from scoring.pipeline import evaluate_all

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s",
                    stream=sys.stderr)

TICKERS = ["JPM", "BAC", "GS", "MS", "WFC", "TRV", "AIG", "MET", "AMT", "PLD",
           "EQIX", "XOM", "NEM", "FCX", "DOW", "CAT", "NVDA", "BIIB", "AEE",
           "ROK", "DUK", "DE", "CSX", "CARR", "RL"]


def fmt_mos(v, special=False, le0=False):
    if special:
        return "n/a (Sonderregel)"
    if le0:
        return "Start-FCF ≤ 0"
    if v != v:
        return "n/a"
    if v < -1.0:
        return "< −100%"
    return f"{v:.1%}"


def fmt_v(v):
    return "n/a" if v != v else f"{v:.1f}"


def fmt_cov(c):
    return "n/a" if c != c else f"{c:.0%}"


def main():
    cfg = load_config()
    providers = build_providers("")
    companies, errors = [], []
    for i, t in enumerate(TICKERS, 1):
        try:
            m = load_with_provider(t, cfg, providers, years=cfg["data"]["years"])
            companies.append(m)
            print(f"[{i}/25] {t} geladen ({m.source})", file=sys.stderr)
        except Exception as exc:
            errors.append({"ticker": t, "error": str(exc)[:200]})
            print(f"[{i}/25] {t} FEHLER: {exc}", file=sys.stderr)

    results = []
    for m in companies:
        results.append((m, __import__("scoring.pipeline", fromlist=["evaluate_ticker"]).evaluate_ticker(m, cfg)))

    rows = [res["row"] for _, res in results if res["row"] is not None]
    excluded = [(m, res) for m, res in results if res["row"] is None]
    rows.sort(key=lambda r: -(r["score"] if r["score"] == r["score"] else -1))

    cols = ["Ticker", "Industry", "Industry-Gruppe", "Status (alle Modi)", "Status (jüngste 2)",
            "Quality", "Value", "Datenabdeckung", "MoS Ø3J", "MoS jüngstes GJ", "MoS TTM Ø", "MoS TTM",
            "SEC", "SEC-Detail", "Flags"]
    with open("testlauf_25.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            special = bool(r.get("sector_special", False))
            sec = ("⚠ Quellen weichen ab" if r["sec_check_flag"] else
                   "ok" if r["sec_check_ok"] else "n/a")
            w.writerow([
                r["ticker"], r.get("industry", ""), r.get("sector_group", ""),
                r["status_all"], r["status_recent2"],
                fmt_v(r["quality"]), fmt_v(r["value"]), fmt_cov(r["coverage"]),
                fmt_mos(r["mos_avg3"], special), fmt_mos(r["mos_latest"], special),
                fmt_mos(r["mos_ttm"], special), fmt_mos(r["mos_ttm_only"], special),
                sec, r.get("sec_detail", ""), r["flags"],
            ])

    with open("testlauf_fehler.txt", "w", encoding="utf-8") as f:
        if errors:
            f.write("=== Fehler (Provider) ===\n")
            for e in errors:
                f.write(f"{e['ticker']}: {e['error']}\n")
        else:
            f.write("keine Fehler\n")
        f.write("\n=== Datenqualität je Ticker ===\n")
        any_dq = False
        for m, res in results:
            dq = res.get("data_quality", [])
            if res["row"] is None:
                dq = list(dq) + [f"ausgeschlossen: {'; '.join(res['excluded'])}"]
            if dq:
                any_dq = True
                f.write(f"{m.ticker}:\n")
                for d in dq:
                    f.write(f"  - {d}\n")
        if not any_dq:
            f.write("keine Auffälligkeiten\n")

    print(f"\n{len(rows)} bewertet, {len(excluded)} ausgeschlossen, {len(errors)} Fehler")


if __name__ == "__main__":
    main()
