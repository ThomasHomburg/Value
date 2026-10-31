"""Tests fuer v30/v31:
(a) dcf.candidate_mode: min_all (Default) vs. min_recent2 -- Status unter beiden
    Regeln nebeneinander in der Row ("status_all" / "status_recent2").
(b) Quartalstabelle: 8 Quartale (4 aktuelle + 4 Vorjahresquartale) + YoY je
    Quartal (quarters[i]["yoy"] vs. quarters[i+4]).
(c) Matrix (app.py page_matrix): Farbe nach Status, y = MoS (min der Modi) auf
    -100 % begrenzt, Hilfslinien aus config (buy_quality_min /
    buy_margin_of_safety_min), Ziel-Quadrant + Tabelle mit MoS je Modus.
(5) Smoke ueber alle Demo-Ticker + v30-Spalten.
"""

import math

import pandas as pd
import pytest

from data.demo import demo_companies
from data.loader import Metric, TickerMetrics
from data.ttm import compute_ttm
from scoring.pipeline import evaluate_all, evaluate_ticker


def _mk(ticker="T", mcap=1e12, fcf_by_fy=None):
    """5 Jahre; fcf_by_fy steuert den FCF je Jahr (fuer Kandidat/Beobachtung)."""
    m = TickerMetrics(ticker=ticker, country="US")
    m.name = ticker
    m.sector = "Technology"
    m.market_cap = Metric("market_cap", mcap, "USD", "USD", 2025)
    rev = 100e9
    for i, fy in enumerate(range(2021, 2026)):
        rev *= 1.08
        ocf = 0.28 * rev
        capex = -0.05 * rev
        sbc = 0.02 * rev
        fcf = (fcf_by_fy or {}).get(fy, ocf + capex)
        m.years[fy] = {
            "revenue": Metric("revenue", rev, "USD", "USD", fy),
            "gross_profit": Metric("gross_profit", 0.6 * rev, "USD", "USD", fy),
            "ebit": Metric("ebit", 0.25 * rev, "USD", "USD", fy),
            "ebitda": Metric("ebitda", 0.30 * rev, "USD", "USD", fy),
            "net_income": Metric("net_income", 0.20 * rev, "USD", "USD", fy),
            "operating_cashflow": Metric("operating_cashflow", ocf, "USD", "USD", fy),
            "capex": Metric("capex", capex, "USD", "USD", fy),
            "fcf": Metric("fcf", fcf, "USD", "USD", fy),
            "stock_based_compensation": Metric("stock_based_compensation", sbc, "USD", "USD", fy),
            "fcf_sbc": Metric("fcf_sbc", fcf - sbc, "USD", "USD", fy),
            "interest_expense": Metric("interest_expense", 0.5e9, "USD", "USD", fy),
            "income_tax_expense": Metric("income_tax_expense", 0.05 * rev, "USD", "USD", fy),
            "income_before_tax": Metric("income_before_tax", 0.25 * rev, "USD", "USD", fy),
            "shares_diluted": Metric("shares_diluted", 2e9, "shares", "USD", fy),
            "equity": Metric("equity", 80e9, "USD", "USD", fy),
            "net_debt": Metric("net_debt", 5e9, "USD", "USD", fy),
        }
    return m


# ---------- (a) candidate_mode ----------

def test_candidate_mode_default_min_all(cfg):
    """Default candidate_mode = min_all: aktive Regel = alle Modi."""
    assert cfg["dcf"].get("candidate_mode", "min_all") == "min_all"
    m = _mk()
    out = evaluate_ticker(m, cfg)
    row = out["row"]
    assert row["candidate_mode"] == "min_all"
    assert row["status"] == row["status_all"]
    for k in ("status_all", "status_all_detail", "status_recent2",
              "status_recent2_detail", "mos_recent2"):
        assert k in row


def test_candidate_mode_min_recent2_aktiv(cfg):
    """candidate_mode = min_recent2: Spalte 'status' = Status der juengsten 2 Modi."""
    cfg2 = dict(cfg)
    cfg2["dcf"] = dict(cfg["dcf"])
    cfg2["dcf"]["candidate_mode"] = "min_recent2"
    m = _mk()
    out = evaluate_ticker(m, cfg2)
    row = out["row"]
    assert row["candidate_mode"] == "min_recent2"
    assert row["status"] == row["status_recent2"]
    # mos_recent2 = min(juengstes GJ, TTM) -- hier ohne TTM = min(latest) oder NaN
    mos_latest = row["mos_latest"]
    mos_ttm_only = row["mos_ttm_only"]
    vals = [v for v in (mos_latest, mos_ttm_only) if v == v]
    if vals:
        assert row["mos_recent2"] == pytest.approx(min(vals))


def test_status_unter_beiden_regeln_nebeneinander(cfg):
    """Beide Status-Spalten in der Row; bei min_all koennen sie sich unterscheiden."""
    rows, _ = evaluate_all(demo_companies(), cfg)
    for r in rows:
        assert r["status_all"] in ("Kandidat", "Beobachtung", "nein")
        assert r["status_recent2"] in ("Kandidat", "Beobachtung", "nein")
        assert "status_all_detail" in r and "status_recent2_detail" in r


def test_app_zeigt_beide_status_spalten():
    import io as _io
    with _io.open("app.py", encoding="utf-8") as f:
        src = f.read()
    assert '"Status (alle Modi)"' in src
    assert '"Status (j' in src and 'ngste 2)"' in src


# ---------- (b) 8 Quartale + YoY ----------

def _qframes(quarters, ocf_per_q):
    cols = list(quarters)
    n = len(cols)
    cf = pd.DataFrame({
        "Operating Cash Flow": list(ocf_per_q),
        "Capital Expenditure": [-1e9] * n,
        "Free Cash Flow": [o - 1e9 for o in ocf_per_q],
        "Stock Based Compensation": [0.5e9] * n,
    }, index=cols).T
    inc = pd.DataFrame({"Total Revenue": [1e9] * n}, index=cols).T
    bal = pd.DataFrame({"Net Debt": [0.0] * n, "Stockholders Equity": [1e9] * n},
                       index=cols).T
    from data.providers.yfinance_provider import _ROW_MAP
    return {"income": inc, "balance": bal, "cashflow": cf, "row_map": _ROW_MAP}


def test_quarters_8_mit_yoy():
    quarters = [pd.Timestamp(f"{y}-{m}-28") for y, m in
                [(2026, 8), (2026, 5), (2026, 2), (2025, 11),
                 (2025, 8), (2025, 5), (2025, 2), (2024, 11),
                 (2024, 8)]]
    ocf = [4e9, 3e9, 3e9, 3e9, 2e9, 2e9, 2e9, 2e9, 999e9]  # letzte 8 zaehlen
    res = compute_ttm(TickerMetrics(ticker="T"), _qframes(quarters, ocf))
    assert len(res.quarters) == 8
    assert res.quarters[0]["quarter_end"] == "2026-08-28"
    assert res.quarters[-1]["quarter_end"] == "2024-11-28"
    # YoY: quarters[0] (OCF 4e9 -> FCF-SBC 2.5e9) vs. quarters[4] (OCF 2e9 -> 0.5e9)
    assert res.quarters[0]["fcf_sbc"] == pytest.approx(4e9 - 1e9 - 0.5e9)
    assert res.quarters[4]["fcf_sbc"] == pytest.approx(2e9 - 1e9 - 0.5e9)
    assert res.quarters[0]["yoy"] == pytest.approx((2.5e9 / 0.5e9) - 1.0)
    # Vorjahresquartale ohne Vorjahresquartal -> yoy NaN
    assert math.isnan(res.quarters[5]["yoy"])


def test_app_quartalstabelle_8_und_yoy():
    import io as _io
    with _io.open("app.py", encoding="utf-8") as f:
        src = f.read()
    assert "Letzte 8 Quartale" in src
    assert "YoY je Quartal" in src
    assert "quarters[:8]" not in src  # ttm.py liefert die 8
    assert "q4 = ttm_obj.quarters[:4]" in src  # Summenzeile nur ueber 4 aktuelle


# ---------- (c) Matrix ----------

def test_matrix_umgebaut_auf_status_mos():
    """page_matrix: Farbe nach Status, y = MoS min der Modi (>= -100 %), Hilfslinien
    aus config, Ziel-Quadrant + Tabelle mit MoS je Modus."""
    import io as _io
    with _io.open("app.py", encoding="utf-8") as f:
        src = f.read()
    assert "def page_matrix" in src
    assert "mos_axis" in src and "max(v, -1.0)" in src          # y begrenzt auf -100 %
    assert "status_cat" in src and '"#2e7d32"' in src           # Kandidat gruen
    assert '"#1565c0"' in src and '"#9e9e9e"' in src             # Beobachtung blau, sonst grau
    assert "buy_quality_min" in src and "buy_margin_of_safety_min" in src  # Hilfslinien aus config
    assert "Ziel-Quadrant" in src
    # Tabelle: Ticker, Status, Quality, MoS je Modus
    for col in ("mos_avg3", "mos_latest", "mos_ttm", "mos_ttm_only", "status_all",
                "status_recent2"):
        assert col in src


# ---------- (5) Smoke ----------

def test_smoke_v30_columns(cfg):
    rows, excluded = evaluate_all(demo_companies(), cfg)
    assert rows
    for r in rows:
        for k in ("status_all", "status_recent2", "mos_recent2", "candidate_mode"):
            assert k in r
    assert excluded
