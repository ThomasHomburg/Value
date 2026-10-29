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
from scoring.criteria import compute_criteria, active_criteria
from scoring.sectors import sector_rule, normalized_net_income, price_to_book, dividend_yield
from scoring.filters import check_filters, count_value_years
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
    # v29: gezahlte Jahre (mit Werten) fuer die Ausschlusstabelle
    out["history_years"] = count_value_years(m)
    if reasons:
        return out

    out["violations"] = check_ticker(m, cfg["sanity"])
    for v in out["violations"]:
        logger.warning("%s Sanity-Verstoss: %s", m.ticker, v)

    criteria = compute_criteria(m, cfg)
    result = score_ticker(criteria, cfg["criteria"], cfg.get("score_groups"))
    out["criteria"] = criteria
    out["score"] = result

    # v28: Sektorgruppe (Industry-basiert) + Sektor-Kennzahlen in die Row
    rule = sector_rule(m, cfg)
    norm_ni, norm_years = normalized_net_income(m, rule)
    row_sector_group = rule.group
    row_sector_note = rule.note
    row_normalized_earnings = norm_ni
    row_normalized_earnings_years = norm_years
    row_price_to_book = price_to_book(m)
    row_dividend_yield = dividend_yield(m)

    # DCF (Build-Schritt 6): MoS Base in die Row; Kaufkandidat markieren
    dcf = compute_dcf(m, cfg)
    out["dcf"] = dcf
    price = float("nan")
    if (m.market_cap is not None and not m.market_cap.is_na()
            and dcf.shares == dcf.shares and dcf.shares > 0):
        price = m.market_cap.value / dcf.shares

    # v27: MoS (Base) je Startwert-Modus (Ø3J / jüngstes GJ / TTM Ø / TTM rein)
    mos_by_mode = {}
    for mode in ("avg3", "latest", "ttm", "ttm_only"):
        dcf_m = compute_dcf(m, cfg, fcf_mode=mode)
        mos_by_mode[mode] = dcf_m.margin_of_safety
    mos_avg3 = mos_by_mode.get("avg3", float("nan"))
    mos_latest = mos_by_mode.get("latest", float("nan"))
    mos_ttm = mos_by_mode.get("ttm", float("nan"))
    mos_ttm_only = mos_by_mode.get("ttm_only", float("nan"))

    # v27: Kandidatenregel nutzt das konfigurierte MoS (min/avg3/latest/ttm/ttm_only/auto)
    dc = cfg["dcf"]
    mos_mode = str(dc.get("mos_min_mode", "min")).lower()
    if mos_mode == "min":
        mos_candidates = [v for v in (mos_avg3, mos_latest, mos_ttm, mos_ttm_only) if v == v]
        mos_rule = min(mos_candidates) if mos_candidates else float("nan")
    elif mos_mode == "auto":
        mos_rule = dcf.margin_of_safety
    else:
        mos_rule = mos_by_mode.get(mos_mode, float("nan"))

    # v21: Kandidatenregel auf Quality (statt Gesamtscore) umgestellt
    dcf.is_buy = is_buy_candidate(result["quality"], dcf, price, cfg, mos_rule=mos_rule)

    # MoS je Szenario + Kandidaten-Begruendung (welche Bedingung fehlt)
    quality_min = float(dc.get("buy_quality_min", 60))
    mos_min = float(dc.get("buy_margin_of_safety_min", 0.30))
    bear_floor = float(dc.get("buy_bear_floor", 0.80))
    watch_min = float(dc.get("watch_margin_of_safety_min", 0.30))
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
    if result["quality"] != result["quality"] or result["quality"] < quality_min:
        missing.append(f"Quality {result['quality']:.1f} < {quality_min:.0f}"
                       if result["quality"] == result["quality"] else "Quality n/a")
    if mos_rule != mos_rule or mos_rule < mos_min:
        if mos_rule == mos_rule:
            mos_label = {"min": "MoS min(Ø3J/jüngstes/TTM)",
                         "auto": "MoS Base"}.get(mos_mode, f"MoS {mos_mode}")
            missing.append(f"{mos_label} {mos_rule:.1%} < {mos_min:.0%}")
        else:
            missing.append("MoS Base n/a")
    if (bear_vps is None or bear_vps.value_per_share != bear_vps.value_per_share
            or bear_vps.value_per_share < bear_floor * (price if price == price else float("nan"))):
        if price == price and bear_vps is not None and bear_vps.value_per_share == bear_vps.value_per_share:
            missing.append(f"Bear {bear_vps.value_per_share / price:.0%} Kurs < {bear_floor:.0%} Kurs")
        else:
            missing.append("Bear n/a")

    # v27: Zwei Stufen -- "Kandidat" und "Beobachtung".
    # Kandidat: Minimum der Modi >= 30 %, Quality >= 60, Bear >= 80 % Kurs
    #   (bei Kandidat: der fuer das Minimum entscheidende Modus wird genannt).
    # Beobachtung: Minimum < 30 %, aber der BESTE Modus >= 30 % und Quality >= 60.
    #   (Bear spielt fuer die Beobachtungsliste keine Rolle.)
    mode_names = {"avg3": "Ø3J", "latest": "jüngstes GJ",
                  "ttm": "TTM Ø", "ttm_only": "TTM"}

    def _status_for(mos_rule_val: float, modes_for_rule: list[tuple[str, float]],
                    is_buy_flag: bool) -> tuple[str, str]:
        """Status (Kandidat/Beobachtung/nein) fuer eine Kandidatenregel (v30:
        dieselbe Logik fuer 'alle Modi' und 'juengste 2 Modi')."""
        if is_buy_flag:
            st = "Kandidat"
            detail = ""
            if modes_for_rule:
                min_val = min(v for _, v in modes_for_rule)
                deciding = [mode_names.get(k, k) for k, v in modes_for_rule if v == min_val]
                detail = (f"entscheidend: Minimum {mos_rule_val:.1%} "
                          f"(bei Modus {', '.join(deciding)})"
                          if mos_rule_val == mos_rule_val else "")
            return st, detail
        if (quality_ok_global and mos_rule_val == mos_rule_val and mos_rule_val < mos_min
                and modes_for_rule):
            best_mode, best_val = max(modes_for_rule, key=lambda kv: kv[1])
            if best_val >= watch_min:
                return "Beobachtung", (f"bester Modus {mode_names.get(best_mode, best_mode)} "
                                        f"{best_val:.1%} ≥ {watch_min:.0%}, "
                                        f"aber min {mos_rule_val:.1%} < {mos_min:.0%}")
        return "nein", ""

    # v34: SBC-Zeile fehlt in ALLEN Jahren -> Status "Pruefen (SBC fehlt)" (nie Kandidat);
    # FCF/DCF laufen ohne SBC (Fallback v33), Roh-FCF-Yield fliesst NICHT in den Value-Score
    sbc_missing_all = not any(
        "fcf_sbc" in m.years[fy] and not m.years[fy]["fcf_sbc"].is_na()
        for fy in m.years
    ) and not (
        getattr(m, "ttm", None) is not None
        and m.ttm.ttm.get("fcf_sbc") is not None and not m.ttm.ttm["fcf_sbc"].is_na()
    )
    if sbc_missing_all:
        dcf.is_buy = False  # nie Kandidat ohne SBC

    mos_vals = [(k, v) for k, v in mos_by_mode.items() if v == v]
    mos_vals_global = mos_vals
    quality_ok = result["quality"] == result["quality"] and result["quality"] >= quality_min
    quality_ok_global = quality_ok
    status, status_detail = _status_for(mos_rule, mos_vals, dcf.is_buy)

    # v30: zweite Regel -- Minimum aus den juengsten 2 Modi (juengstes GJ + TTM rein)
    dc_candidate_mode = str(dc.get("candidate_mode", "min_all")).lower()
    recent2 = [(k, v) for k, v in mos_vals if k in ("latest", "ttm_only")]
    mos_recent2 = min(v for _, v in recent2) if recent2 else float("nan")
    if dc_candidate_mode == "min_recent2":
        # aktive Regel = juengste 2
        status, status_detail = _status_for(
            mos_recent2, recent2,
            is_buy_candidate(result["quality"], dcf, price, cfg, mos_rule=mos_recent2))
        status_all, status_all_detail = _status_for(mos_rule, mos_vals, dcf.is_buy)
        status_recent2, status_recent2_detail = status, status_detail
        if sbc_missing_all:
            status = status_all = status_recent2 = "Prüfen (SBC fehlt)"
            status_detail = status_all_detail = status_recent2_detail = (
                "SBC fehlt in allen Jahren -> FCF/DCF ohne SBC; nie Kandidat")
    else:
        # Default min_all: aktive Regel = alle Modi
        status_all, status_all_detail = status, status_detail
        is_buy_recent2 = (False if sbc_missing_all else
                          is_buy_candidate(result["quality"], dcf, price, cfg, mos_rule=mos_recent2))
        status_recent2, status_recent2_detail = _status_for(mos_recent2, recent2, is_buy_recent2)

    # v34: SBC fehlt -> alle Status "Pruefen (SBC fehlt)" (ueberschreibt Kandidat/Beobachtung)
    if sbc_missing_all:
        status = status_all = status_recent2 = "Prüfen (SBC fehlt)"
        status_detail = status_all_detail = status_recent2_detail = (
            "SBC fehlt in allen Jahren -> FCF/DCF ohne SBC; nie Kandidat")

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
    # TTM unplausibel -> Flag + Log (Rueckfall auf Geschaeftsjahre im DCF)
    if getattr(m, "ttm", None) is not None and not getattr(m, "ttm_plausible", True):
        flag_parts.append("ttm:unplausibel")
        logger.warning("%s: Quartalsdaten unplausibel -> Rueckfall auf Geschaeftsjahre (DCF-Basis)",
                       m.ticker)
    # v26: SEC-EDGAR-Abgleich (US-Ticker) — Abweichung > tolerance -> Flag
    sec = None
    if cfg.get("sec", {}).get("enabled", True):
        try:
            from data.sec import sec_check
            sec = sec_check(m, cfg)
            if sec.flag:
                flag_parts.append("sec:abweichend")
                logger.warning("%s: %s", m.ticker, sec.note)
        except Exception as exc:  # SEC nicht erreichbar -> kein Absturz
            logger.warning("%s: SEC-Abgleich fehlgeschlagen: %s", m.ticker, exc)
    # v33: SBC fehlt -> DCF/FCF ohne SBC (Fallback Roh-FCF) -> Flag
    if dcf.sbc_missing:
        flag_parts.append("SBC n/a (ohne SBC)")
        logger.warning("%s: kein FCF-SBC verfuegbar -> FCF und DCF OHNE SBC (Roh-FCF) verwendet",
                       m.ticker)
    # v29: EBITDA unplausibel (EBITDA < EBIT) -> Flag + ND/EBITDA n/a
    if getattr(m, "ebitda_unplausible", False):
        flag_parts.append("ebitda:unplausibel")
        logger.warning("%s: EBITDA < EBIT in mind. einem Jahr -> Flag 'EBITDA unplausibel'; ND/EBITDA n/a",
                       m.ticker)
    # v28: Zykliker mit weniger Jahren als normalize_years -> Flag + Log
    if rule.group == "cyclicals" and 0 < norm_years < max(1, rule.normalized_earnings_years):
        flag_parts.append("zyk:norm<7J")
        logger.info("%s: Zykliker -- Gewinnnormalisierung ueber %d Jahre (< %d) -> Flag",
                    m.ticker, norm_years, rule.normalized_earnings_years)
    if rule.group == "reits":
        logger.info("%s: REIT (%s) -- %s", m.ticker, m.industry, rule.note)
    if dcf.is_buy:
        flag_parts.append("kauf")
        logger.info("%s: Kaufkandidat (Quality %.1f, MoS Base %.1f%%, Bear >= 80%% Kurs)",
                    m.ticker, result["quality"], dcf.margin_of_safety * 100)
    elif status == "Beobachtung":
        flag_parts.append("beobachten")
        logger.info("%s: Beobachtungsliste (%s)", m.ticker, status_detail)
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
        # v27: MoS (Base) je Startwert-Modus (Rangliste nebeneinander)
        "mos_avg3": mos_avg3,
        "mos_latest": mos_latest,
        "mos_ttm": mos_ttm,
        "mos_ttm_only": mos_ttm_only,
        "mos_rule": mos_rule,          # fuer Kandidatenregel verwendetes MoS (config mos_min_mode)
        "mos_rule_mode": mos_mode,
        # v27: Zwei Stufen -- Kandidat / Beobachtung (+ Detail, welcher Modus entscheidet)
        "status": status,
        "status_detail": status_detail,
        # v30: Status unter beiden Kandidatenregeln nebeneinander + aktive Regel
        "status_all": status_all,
        "status_all_detail": status_all_detail,
        "status_recent2": status_recent2,
        "status_recent2_detail": status_recent2_detail,
        "mos_recent2": mos_recent2,
        "candidate_mode": dc_candidate_mode,
        # v26: MoS (Base) mit alternativer Nettoverschuldung
        "mos_base_alt_nd": dcf.mos_base_alt,
        "dcf_net_debt_mode": dcf.net_debt_mode,
        "dcf_net_debt_alt": dcf.net_debt_alt,
        "dcf_net_debt_alt_source": dcf.net_debt_alt_source,
        "kandidat": ("ja" if dcf.is_buy else
                     (status if status != "nein" else "nein")
                     + (f" ({status_detail})" if status_detail else "")
                     if dcf.is_buy or status != "nein"
                     else ("nein: " + "; ".join(missing) if missing else "nein")),
        # TTM-Basis des DCF (Scorecard-Anzeige: Stichtag + Basis)
        "dcf_fcf_basis": dcf.fcf_basis,
        "dcf_ttm_quarter_end": dcf.ttm_quarter_end,
        "dcf_fcf_sources": dcf.fcf_sources,
        "dcf_net_debt": dcf.net_debt,
        "dcf_net_debt_source": dcf.net_debt_source,
        "dcf_customer_deposits": dcf.customer_deposits,
        "dcf_fcf_mode": dcf.fcf_mode,
        "ttm_plausible": getattr(m, "ttm_plausible", True),
        "dcf_value_per_share_base": dcf.scenarios.get("base").value_per_share
        if dcf.scenarios.get("base") else float("nan"),
        "dcf_value_per_share_bear": dcf.scenarios.get("bear").value_per_share
        if dcf.scenarios.get("bear") else float("nan"),
        "dcf_value_per_share_bull": dcf.scenarios.get("bull").value_per_share
        if dcf.scenarios.get("bull") else float("nan"),
        "is_buy": dcf.is_buy,
        "flags": flags,
        # v28: Sektorgruppe (Industry) + Sektor-Kennzahlen
        "sector_group": row_sector_group,
        "sector_note": row_sector_note,
        "industry": m.industry,
        "normalized_earnings": row_normalized_earnings,
        "normalized_earnings_years": row_normalized_earnings_years,
        "price_to_book": row_price_to_book,
        "dividend_yield": row_dividend_yield,
        # v26: SEC-EDGAR-Abgleich
        "sec_check_ok": bool(sec and sec.ok),
        "sec_check_flag": bool(sec and sec.flag),
        "sec_check_note": sec.note if sec else "",
        # v29: EBITDA-Plausibilitaet + Historie (Jahre mit Werten)
        "ebitda_unplausible": bool(getattr(m, "ebitda_unplausible", False)),
        "history_years": count_value_years(m),
        # v33: SBC-Fallback (DCF ohne SBC) + Start-FCF <= 0 + Value-n/a-Schwelle
        "dcf_sbc_missing": bool(dcf.sbc_missing),
        "status_pruefen_sbc": sbc_missing_all,
        "dcf_fcf_le0": bool(dcf.fcf_le0),
        "value_na_below_coverage": float(cfg.get("score_groups", {}).get("min_coverage_value", 0.70)),
    }
    out["row"] = row
    out["sec_check"] = sec
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
            excluded.append({"ticker": m.ticker, "name": m.name, "reasons": res["excluded"],
                             "history_years": res.get("history_years", 0)})
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
