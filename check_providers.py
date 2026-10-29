"""Provider-Check: laedt Ticker ueber die Provider-Schnittstelle und gibt Rohwerte aus.

Aufruf:  python3 check_providers.py [TICKER ...]   (Default: AAPL SAP.DE ASML.AS NOVO-B.CO)

Pro Ticker: genutzte Quelle, Jahre, FCF + Marktkapitalisierung (neuestes FY,
absolut mit Waehrung) und ROIC (neuestes FY + 5-Jahres-Durchschnitt), plus
'Daten duenn'-Markierung (Kriterien mit < data.thin_years Jahren).
"""

from __future__ import annotations

import logging
import math
import os
import sys

from config import load_config
from data.metrics import fcf_yield, invested_capital, nopat, roic, tax_rate
from data.providers.base import ProviderError, build_providers, load_with_provider
from scoring.criteria import compute_criteria
from scoring.pipeline import evaluate_ticker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _fmt_abs(value: float, currency: str) -> str:
    if math.isnan(value):
        return "n/a"
    for div, suffix in (1e12, "Bio."), (1e9, "Mrd."), (1e6, "Mio."):
        if abs(value) >= div:
            return f"{value / div:,.2f} {suffix} {currency}"
    return f"{value:,.0f} {currency}"


def _fmt_pct(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.2%}"


def main() -> None:
    cfg = load_config()
    api_key = os.environ.get("FMP_API_KEY", "")
    providers = build_providers(api_key)
    tickers = sys.argv[1:] or ["AAPL", "SAP.DE", "ASML.AS", "NOVO-B.CO"]
    print(f"Provider verfuegbar: {', '.join(sorted(providers))} "
          f"(FMP nur mit FMP_API_KEY; yfinance ohne Key)")
    print()

    for ticker in tickers:
        try:
            m = load_with_provider(ticker, cfg, providers, years=cfg["data"]["years"])
        except ProviderError as exc:
            print(f"{ticker}: FEHLER: {exc}\n")
            continue

        latest_fy = max(m.years)
        ym = m.years[latest_fy]
        cur = ym.get("fcf")
        cur = cur.currency if cur is not None else "?"
        fcf = ym.get("fcf")
        mcap = m.market_cap.value if m.market_cap is not None and not m.market_cap.is_na() else float("nan")
        mcap_cur = m.market_cap.currency if m.market_cap is not None else "?"

        crits = compute_criteria(m, cfg)
        roic_latest = roic(m, latest_fy)
        roic5 = crits["roic_avg5"]
        res = evaluate_ticker(m, cfg)

        print(f"=== {m.ticker} – {m.name} ({m.sector}, {m.country}) ===")
        print(f"  Quelle          : {m.source}")
        print(f"  Jahre           : {', '.join(str(fy) for fy in sorted(m.years))}")
        print(f"  FCF FY{latest_fy}       : {_fmt_abs(fcf.value, cur)} (OCF + Capex, absolut)")
        print(f"  Marktkap.       : {_fmt_abs(mcap, mcap_cur)} (aktuell, Quote-Waehrung)")
        print(f"  FCF-Yield FY{latest_fy}  : {_fmt_pct(fcf_yield(m, latest_fy))}")
        print(f"  EBIT FY{latest_fy}      : {_fmt_abs(ym['ebit'].value, cur)}")
        print(f"  Steuersatz FY{latest_fy} : {_fmt_pct(tax_rate(m, latest_fy))}")
        print(f"  NOPAT FY{latest_fy}      : {_fmt_abs(nopat(m, latest_fy), cur)}")
        print(f"  Inv. Kapital FY{latest_fy}: {_fmt_abs(invested_capital(m, latest_fy), cur)} "
              f"(EK + Nettoverschuldung)")
        print(f"  ROIC FY{latest_fy}       : {_fmt_pct(roic_latest)}")
        print(f"  ROIC Ø 5J       : {_fmt_pct(roic5.value)}  "
              f"(Daten: {roic5.years_available} J.{' [!] duenn' if roic5.thin else ''})")
        if res["row"] is not None:
            print(f"  Score           : {res['row']['score']:.1f} / 100"
                  f"  Flags: {res['row']['flags'] or '–'}")
            thin = ", ".join(res["thin_criteria"]) or "keine"
            print(f"  'Daten duenn'   : {thin}")
        else:
            print(f"  Ausgeschlossen  : {'; '.join(res['excluded'])}")
        print()


if __name__ == "__main__":
    main()
