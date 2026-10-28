"""Gesamte Auswertungs-Pipeline fuer CLI (run_ranking.py) und Streamlit-UI.

Ablauf je Ticker: harte Filter -> Sanity-Check (Log) -> Kriterien -> Score.
Ausgeschlossene Ticker werden mit Grund geloggt (CLAUDE.md: Logging-Pflicht).
"""

from __future__ import annotations

import logging
import math

from data.loader import TickerMetrics
from data.metrics import fcf_yield, fcf_yield_sbc, roic
from data.sanity import check_ticker
from scoring.criteria import compute_criteria
from scoring.filters import check_filters
from scoring.score import score_ticker
from valuation.dcf import compute_dcf, is_buy_candidate

logger = logging.getLogger("value_screener.pipeline")


def _fmt_pct(v: float) -> str:
    return "n/a" if math.isnan(v) else f"{v:.2%}"


def evaluate_ticker(m: TickerMetrics, cfg: dict) -> dict:
    """Wertet einen Ticker aus.

    Rueckgabe: {"row": dict | None, "excluded": [gruende], "violations": [texte],
                "criteria": {...}, "score": {...}}
    row ist None, wenn der Ticker ausgeschlossen wurde.
    """
    out = {"row": None, "excluded": [], "violations": [], "criteria": {}, "score": {}}

    reasons = check_filters(m, cfg["filters"])
    for r in reasons:
        logger.info("%s ausgeschlossen: %s", m.ticker, r)
    out["excluded"] = reasons
    if reasons:
        return out

    out["violations"] = check_ticker(m, cfg["sanity"])
    for v in out["violations"]:
        logger.warning("%s Sanity-Verstoss: %s", m.ticker, v)

    criteria = compute_criteria(m, cfg)
    result = score_ticker(criteria, cfg["criteria"], cfg.get("score_groups"))
    out["criteria"] = criteria
    out["score"] = result

    # DCF (Build-Schritt 6): MoS Base in die Row; Kaufkandidat markieren
    dcf = compute_dcf(m, cfg)
    out["dcf"] = dcf
    price = float("nan")
    if (m.market_cap is not None and not m.market_cap.is_na()
            and dcf.shares == dcf.shares and dcf.shares > 0):
        price = m.market_cap.value / dcf.shares
    dcf.is_buy = is_buy_candidate(result["total"], dcf, price, cfg)

    # MoS je Szenario + Kandidaten-Begruendung (welche Bedingung fehlt)
    dc = cfg["dcf"]
    score_min = float(dc.get("buy_score_min", 70))
    mos_min = float(dc.get("buy_margin_of_safety_min", 0.30))
    bear_floor = float(dc.get("buy_bear_floor", 0.80))
    mos_bear = float("nan")
    mos_bull = float("nan")
    bear_vps = dcf.scenarios.get("bear")
    bull_vps = dcf.scenarios.get("bull")
    if price == price and price > 0:
        if bear_vps is not None and bear_vps.value_per_share == bear_vps.value_per_share \
                and bear_vps.value_per_share > 0:
            mos_bear = 1.0 - price / bear_vps.value_per_share
        if bull_vps is not None and bull_vps.value_per_share == bull_vps.value_per_share \
                and bull_vps.value_per_share > 0:
            mos_bull = 1.0 - price / bull_vps.value_per_share
    missing = []
    if result["total"] != result["total"] or result["total"] < score_min:
        missing.append(f"Score {result['total']:.1f} < {score_min:.0f}"
                       if result["total"] == result["total"] else "Score n/a")
    if dcf.margin_of_safety != dcf.margin_of_safety or dcf.margin_of_safety < mos_min:
        missing.append(f"MoS Base {dcf.margin_of_safety:.1%} < {mos_min:.0%}"
                       if dcf.margin_of_safety == dcf.margin_of_safety else "MoS Base n/a")
    if (bear_vps is None or bear_vps.value_per_share != bear_vps.value_per_share
            or bear_vps.value_per_share < bear_floor * (price if price == price else float("nan"))):
        if price == price and bear_vps is not None and bear_vps.value_per_share == bear_vps.value_per_share:
            missing.append(f"Bear {bear_vps.value_per_share / price:.0%} Kurs < {bear_floor:.0%} Kurs")
        else:
            missing.append("Bear n/a")

    # Quelle pro Ticker loggen (CLAUDE.md: Logging-Pflicht)
    logger.info("%s: Quelle=%s (%s)", m.ticker, m.source or "unbekannt", m.name)

    # Kriterien mit zu wenig Jahren als "Daten duenn" markieren
    thin = result.get("thin_criteria", [])
    out["thin_criteria"] = thin
    for name in thin:
        crit = criteria[name]
        logger.info("%s: Kriterium '%s' = Daten duenn (%d Jahre mit Daten)",
                    m.ticker, name, crit.years_available)

    latest_fy = max(m.years)
    # Flags kompakt und entdoppelt: Block-Flags als "blk:duenn", duenne Kriterien
    # als "duenn", kleine Kapitalbasis als "kl.Kapital", Kaufkandidat als "kauf"
    flag_parts = [f"{b[:4]}:duenn" for b, f in result["block_flags"].items() if f]
    if thin:
        flag_parts.append("duenn")
    # ROIC > 100 % entsteht typischerweise durch eine kleine/negative Kapitalbasis
    # (z. B. Net Cash wie bei AAPL) -- Anzeige begrenzen und flaggen.
    roic5 = criteria["roic_avg5"].value
    if roic5 == roic5 and roic5 > 1.0:
        flag_parts.append("kl.Kapital")
        logger.info("%s: ROIC 5 J = %.1f%% > 100%% -> Flag 'Kapitalbasis klein' (kleine/negative Kapitalbasis)",
                    m.ticker, roic5 * 100)
    if dcf.is_buy:
        flag_parts.append("kauf")
        logger.info("%s: Kaufkandidat (Score %.1f, MoS Base %.1f%%, Bear >= 80%% Kurs)",
                    m.ticker, result["total"], dcf.margin_of_safety * 100)
    flags = " ".join(dict.fromkeys(flag_parts))  # entdoppeln, Reihenfolge behalten
    row = {
        "ticker": m.ticker,
        "name": m.name,
        "sector": m.sector,
        "country": m.country,
        "source": m.source or "unbekannt",
        "score": result["total"],
        "quality": result["quality"],
        "value": result["value"],
        "coverage": result["coverage"],
        "fcf_yield": fcf_yield(m, latest_fy),
        "fcf_yield_sbc": fcf_yield_sbc(m, latest_fy),
        "fcf_yield_3y": criteria["fcf_yield_sbc_avg3"].value,  # nach SBC (Value-Score)
        "roic_5y": criteria["roic_avg5"].value,
        "roic_5y_years": criteria["roic_avg5"].years_available,  # Fensterlaenge (Tooltip "ROIC Ø")
        "roic_latest": roic(m, latest_fy),   # ROIC neuestes Geschaeftsjahr (Spalte + Metrik)
        "roic_latest_fy": latest_fy,
        "nd_ebitda": criteria["net_debt_ebitda"].value,
        "ev_ebit_med": criteria["ev_ebit_vs_median"].value,
        # Margin of Safety (Base) aus dem DCF-Modul (Build-Schritt 6)
        "margin_of_safety": dcf.margin_of_safety,
        # MoS je Szenario + Kandidaten-Spalte (ja/nein + fehlende Bedingung)
        "mos_bear": mos_bear,
        "mos_bull": mos_bull,
        "kandidat": "ja" if dcf.is_buy else ("nein: " + "; ".join(missing) if missing else "nein"),
        "dcf_value_per_share_base": dcf.scenarios.get("base").value_per_share
        if dcf.scenarios.get("base") else float("nan"),
        "dcf_value_per_share_bear": dcf.scenarios.get("bear").value_per_share
        if dcf.scenarios.get("bear") else float("nan"),
        "dcf_value_per_share_bull": dcf.scenarios.get("bull").value_per_share
        if dcf.scenarios.get("bull") else float("nan"),
        "is_buy": dcf.is_buy,
        "flags": flags,
    }
    out["row"] = row
    return out


def evaluate_all(companies: list[TickerMetrics], cfg: dict) -> tuple[list[dict], list[dict]]:
    """Wertet alle Ticker aus; gibt (rangliste, ausgeschlossene) zurueck.

    Rangliste: Rows sortiert nach Score absteigend (NaN-Scores zuletzt).
    Ausgeschlossene: [{"ticker", "name", "reasons": [...]}]
    """
    rows, excluded = [], []
    for m in companies:
        res = evaluate_ticker(m, cfg)
        if res["row"] is None:
            excluded.append({"ticker": m.ticker, "name": m.name, "reasons": res["excluded"]})
        else:
            rows.append(res["row"])
    rows.sort(key=lambda r: (r["score"] if r["score"] == r["score"] else -1), reverse=True)
    return rows, excluded


def rank_rows(rows: list[dict], key: str = "quality") -> dict[str, int | None]:
    """Rang je Ticker nach Kennzahl (1 = bester Wert); Gleichstand -> gleicher Rang.

    NaN-Werte erhalten None (Anzeige "n/a"). Wird fuer die Spalte
    "Quality-Rang" im Universum verwendet (Rangliste + CLI).
    """
    vals = sorted({r[key] for r in rows if r[key] == r[key]}, reverse=True)
    return {
        r["ticker"]: (vals.index(r[key]) + 1 if r[key] == r[key] else None)
        for r in rows
    }


def raw_metric_table(m: "TickerMetrics", names: tuple[str, ...]) -> list[dict]:
    """Rohwerte mit Einheit/Waehrung/Jahr/Quelle fuer eine Kennzahlenliste.

    Wird fuer die Scorecard-Anzeige der Formeln (ROIC 5J, FCF-Yield, ND/EBITDA)
    verwendet.
    """
    out = []
    for fy in sorted(m.years):
        ym = m.years[fy]
        for key in names:
            met = ym.get(key)
            if met is None:
                continue
            out.append({
                "Jahr": fy, "Kennzahl": key,
                "Wert": "n/a" if met.is_na() else f"{met.value:,.0f}",
                "Einheit": met.unit, "Waehrung": met.currency,
            })
    return out
