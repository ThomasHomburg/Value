"""Tests fuer Pipeline-Flags und Quality/Value-Scores."""

import math

from config import load_config
from scoring.pipeline import evaluate_ticker
from scoring.score import score_ticker


def test_aapl_roic_flag_kapitalbasis_klein(aapl_metrics):
    """AAPL hat Net Cash -> ROIC > 100 % -> kompaktes Flag in der Ranglisten-Zeile."""
    cfg = load_config()
    res = evaluate_ticker(aapl_metrics, cfg)
    row = res["row"]
    assert row is not None
    assert row["roic_5y"] > 1.0
    assert "kl.Kapital" in row["flags"]


def test_normal_roic_has_no_kapitalbasis_flag():
    from data.demo import demo_companies

    cfg = load_config()
    qual = next(c for c in demo_companies() if c.ticker == "QUAL")
    res = evaluate_ticker(qual, cfg)
    assert res["row"] is not None
    assert res["row"]["roic_5y"] < 1.0
    assert "kl.Kapital" not in res["row"]["flags"]


def test_quality_value_scores_present(aapl_metrics):
    """Quality und Value werden getrennt berechnet; Gesamtscore = gewichtete Summe."""
    cfg = load_config()
    res = evaluate_ticker(aapl_metrics, cfg)
    s = res["score"]
    assert s["quality"] == s["quality"]  # nicht NaN
    assert s["value"] == s["value"]
    gw = cfg["score_groups"]["weights"]
    expected = gw["quality"] * s["quality"] + gw["value"] * s["value"]
    assert abs(s["total"] - expected) < 0.2  # Rundung auf 1 Nachkommastelle


def test_coverage_is_fraction(aapl_metrics):
    """Datenabdeckung liegt zwischen 0 und 1 (hier: alle Kriterien bewertet -> 100 %)."""
    cfg = load_config()
    res = evaluate_ticker(aapl_metrics, cfg)
    cov = res["score"]["coverage"]
    assert 0.0 <= cov <= 1.0
    assert cov == 1.0  # AAPL hat fuer alle 10 Kriterien Daten


def test_na_criteria_excluded_and_renormalized(aapl_metrics):
    """n/a-Kriterien werden herausgenommen; uebrige Gewichte renormalisieren sich."""
    from scoring.criteria import compute_criteria
    cfg = load_config()
    crits = compute_criteria(aapl_metrics, cfg)
    # EBITDA loeschen -> net_debt_ebitda wird n/a
    for fy in aapl_metrics.years:
        aapl_metrics.years[fy]["ebitda"].value = float("nan")
    crits = compute_criteria(aapl_metrics, cfg)
    res = score_ticker(crits, cfg["criteria"], cfg.get("score_groups"))
    assert crits["net_debt_ebitda"].is_na
    # Deckung sinkt unter 100 % (Gewicht 0.10 fehlt)
    assert res["coverage"] < 1.0
    assert res["coverage"] == round(0.90, 1)
    # Quality-Score trotzdem definiert (renormalisiert auf verbleibende Bloecke)
    assert res["quality"] == res["quality"]


def test_sbc_yield_is_na_when_sbc_missing(aapl_metrics):
    """Ohne SBC in den Rohdaten -> fcf_yield_sbc_avg3 n/a (nie Roh-FCF-Yield)."""
    from scoring.criteria import compute_criteria
    cfg = load_config()
    for fy in aapl_metrics.years:
        aapl_metrics.years[fy]["fcf_sbc"].value = float("nan")
    crits = compute_criteria(aapl_metrics, cfg)
    assert crits["fcf_yield_sbc_avg3"].is_na


def test_row_has_both_yield_columns(aapl_metrics):
    """Ranglisten-Zeile enthaelt Roh-FCF-Yield UND FCF-Yield nach SBC."""
    cfg = load_config()
    res = evaluate_ticker(aapl_metrics, cfg)
    row = res["row"]
    assert "fcf_yield" in row and "fcf_yield_sbc" in row
    assert row["fcf_yield_sbc"] < row["fcf_yield"]  # SBC abgezogen
    # 3J-Spalte nutzt den SBC-Wert (Value-Score)
    assert row["fcf_yield_3y"] == res["score"]["details"]["fcf_yield_sbc_avg3"]["value"]


def test_scores_rounded_to_1_decimal(aapl_metrics):
    """Alle Scores sind auf 1 Nachkommastelle gerundet."""
    cfg = load_config()
    res = evaluate_ticker(aapl_metrics, cfg)
    s = res["score"]
    for key in ("total", "quality", "value", "coverage"):
        v = s[key]
        if v == v:
            assert v == round(v, 1), f"{key}={v} nicht auf 1 Nachkommastelle gerundet"
