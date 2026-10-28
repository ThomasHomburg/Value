"""ADBE-Analyse: Kriterien des ersten Blocks (profitability) mit Rohwert/Schwellen/Punkten.

Usage: python3 tools_adbe_analysis.py [TICKER]
"""

from __future__ import annotations

import math
import os
import sys

from config import load_config
from data.providers.base import build_providers, load_with_provider
from scoring.criteria import compute_criteria
from scoring.score import score_ticker


def fmt(v: float) -> str:
    return "n/a" if (v != v) else f"{v:.4f}"


def main() -> None:
    cfg = load_config()
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "ADBE").upper()
    providers = build_providers(os.environ.get("FMP_API_KEY", ""))
    m = load_with_provider(ticker, cfg, providers, years=cfg["data"]["years"])
    print(f"\n=== {m.ticker} – {m.name} ({m.sector}, {m.country}) Quelle={m.source} ===")
    print(f"Jahre geladen: {sorted(m.years)}  ({len(m.years)} Jahre)")
    print(f"Marktkap.: {m.market_cap.value / 1e9:,.2f} Mrd. {m.market_cap.currency} "
          f"(Stichtag {m.market_cap_date})")

    crits = compute_criteria(m, cfg)
    res = score_ticker(crits, cfg["criteria"], cfg.get("score_groups"))

    print("\n--- Block-Scores ---")
    for b, s in res["blocks"].items():
        flag = res["block_flags"].get(b, "")
        print(f"  {b:<15} {fmt(s):>7} / 100   {flag}")

    print("\n--- Alle Kriterien: Rohwert, Schwellen, Punkte ---")
    for name, crit in crits.items():
        c = cfg["criteria"][name]
        pts = res["details"][name]["points"]
        pct = {"roic_avg5", "roe_avg5", "fcf_margin_avg5", "revenue_cagr_5y", "fcf_yield_sbc_avg3"}
        if crit.is_na:
            val = "n/a"
        elif name in pct:
            val = f"{crit.value:.2%}"
        elif name == "fcf_positive_years":
            n = int(crit.value)
            val = f"{n} positive Jahre (Rohwert {crit.value:.0f})"
        elif name == "gross_margin_trend":
            val = f"{crit.value:.2f} PP/Jahr"
        else:
            val = f"{crit.value:.2f}"
        full = c["full"]
        zero = c["zero"]
        full_s = f"{full:.2%}" if name in pct else (f"{full:.0f}" if name == "fcf_positive_years" else f"{full:.2f}")
        zero_s = f"{zero:.2%}" if name in pct else (f"{zero:.0f}" if name == "fcf_positive_years" else f"{zero:.2f}")
        pts_s = "n/a" if (pts != pts) else f"{pts:.1f}"
        thin = "  [DUENN]" if crit.thin else ""
        print(f"  [{c['block']:<13}] {name:<22} wert={val:<28} voll={full_s:<8} null={zero_s:<8} "
              f"punkte={pts_s:>6}  ({crit.years_available} J.){thin}")

    print(f"\nGesamt: Score={res['total']}  Quality={res['quality']}  Value={res['value']}  "
          f"Abdeckung={res['coverage']}")


if __name__ == "__main__":
    main()
