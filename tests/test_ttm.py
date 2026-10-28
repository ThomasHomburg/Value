"""Tests fuer TTM (data/ttm.py) und die TTM-Basis im DCF (valuation/dcf.py).

- Flussgroessen = Summe der letzten 4 Quartale; Bestandsgoessen = Stichtag.
- Plausibilitaet: TTM zum Geschaeftsjahresende ~ Jahreswert (Abweichung < 2 %).
- Unplausibel -> Flag + Rueckfall auf Geschaeftsjahre (annual).
- DCF-Start-FCF = Ø aus TTM + den zwei davor liegenden, NICHT ueberlappenden
  Geschaeftsjahren (FY-Enddatum strikt vor dem ersten TTM-Quartal).
"""

import math
from types import SimpleNamespace

import pandas as pd
import pytest

from data.loader import Metric, TickerMetrics
from data.ttm import TtmResult, compute_ttm
from valuation.dcf import compute_dcf

DCF_CFG = {"dcf": {
    "discount_rate": 0.10,
    "terminal_growth": 0.025,
    "base_growth_cap": 0.06,
    "bull_growth_multiplier": 1.3,
    "bull_growth_cap": 0.10,
    "fade_to_growth": 0.025,
    "buy_score_min": 70,
    "buy_margin_of_safety_min": 0.30,
    "buy_bear_floor": 0.80,
}}

ROW_MAP = {
    "revenue": ["Total Revenue"],
    "ebit": ["Operating Income"],
    "operating_cashflow": ["Operating Cash Flow"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
    "stock_based_compensation": ["Stock Based Compensation"],
    "equity": ["Stockholders Equity"],
    "net_debt": ["Net Debt"],
    "_total_debt": ["Total Debt"],
    "_cash": ["Cash And Cash Equivalents"],
    "shares_diluted": ["Diluted Average Shares"],
}


def _qframes(quarters, rev_per_q, fcf_per_q, sbc_per_q=0.0, net_debt=1e9, equity=10e9):
    """Quartals-DataFrames: quarters = [Timestamp, ...] (neueste zuerst).

    Jedes Quartal hat Umsatz/FCF/SBC; Bilanz konstant (Bestand).
    yfinance-Layout: Zeilen = Kennzahlen, Spalten = Quartale (wie im Provider).
    """
    cols = list(quarters)
    n = len(cols)

    def _frame(rows: dict[str, list]) -> pd.DataFrame:
        # yfinance-Layout: Zeilen = Kennzahlen-Labels, Spalten = Quartale.
        # pd.DataFrame(data, index=labels) erwartet data als {spalte: {zeile: wert}}
        # -> transponieren: DataFrame({label: werte}, index=cols).T
        return pd.DataFrame(rows, index=cols).T

    inc = _frame({
        "Total Revenue": list(rev_per_q),
        "Operating Income": [r * 0.3 for r in rev_per_q],
        "Diluted Average Shares": [10e9] * n,
    })
    cf = _frame({
        "Operating Cash Flow": [f + 1e9 for f in fcf_per_q],
        "Capital Expenditure": [-1e9] * n,
        "Free Cash Flow": list(fcf_per_q),
        "Stock Based Compensation": [sbc_per_q] * n,
    })
    bal = _frame({
        "Net Debt": [net_debt] * n,
        "Stockholders Equity": [equity] * n,
        "Total Debt": [net_debt + 5e9] * n,
        "Cash And Cash Equivalents": [5e9] * n,
    })
    return {"income": inc, "balance": bal, "cashflow": cf, "row_map": ROW_MAP}


def _annual_ticker(fcf_sbc_by_fy: dict[int, float], rev_by_fy: dict[int, float],
                   fiscal_ends: dict[int, str], mcap: float = 1000e9,
                   shares: float = 10e9) -> TickerMetrics:
    m = TickerMetrics(ticker="TEST")
    m.market_cap = Metric("market_cap", mcap, "USD", "USD", max(fiscal_ends))
    m.fiscal_ends = dict(fiscal_ends)
    for fy in sorted(fiscal_ends):
        m.years[fy] = {
            "fcf_sbc": Metric("fcf_sbc", fcf_sbc_by_fy[fy], "USD", "USD", fy),
            "revenue": Metric("revenue", rev_by_fy[fy], "USD", "USD", fy),
            "shares_diluted": Metric("shares_diluted", shares, "shares", "USD", fy),
        }
    return m


def test_ttm_flussgroessen_summe_letzte_4_quartale():
    """Umsatz/FCF TTM = Summe der letzten 4 Quartale."""
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31"),
                pd.Timestamp("2026-02-28"), pd.Timestamp("2025-11-30"),
                pd.Timestamp("2025-08-31")]
    # 5 Quartale: das aelteste (2025-08) darf NICHT in die TTM-Summe einfliessen
    rev = [6e9, 6e9, 6e9, 6e9, 100e9]
    fcf = [2e9, 2e9, 2e9, 2e9, 100e9]
    frames = _qframes(quarters, rev, fcf, sbc_per_q=0.5e9)
    res = compute_ttm(TickerMetrics(ticker="T"), frames)
    assert res.ttm["revenue"].value == pytest.approx(24e9)   # 4 x 6e9
    assert res.ttm["fcf"].value == pytest.approx(8e9)
    assert res.ttm["fcf_sbc"].value == pytest.approx(8e9 - 2e9)  # - 4 x 0.5e9 SBC
    assert res.quarter_end == "2026-08-31"
    assert res.base_label == "TTM bis 2026-08"


def test_ttm_bestandsgroessen_stichtag():
    """Nettoverschuldung/Eigenkapital = Wert des neuesten Quartals."""
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31"),
                pd.Timestamp("2026-02-28"), pd.Timestamp("2025-11-30")]
    frames = _qframes(quarters, [6e9] * 4, [2e9] * 4, net_debt=2.5e9, equity=12e9)
    res = compute_ttm(TickerMetrics(ticker="T"), frames)
    assert res.ttm["net_debt"].value == pytest.approx(2.5e9)
    assert res.ttm["equity"].value == pytest.approx(12e9)


def test_ttm_plausibel_bei_jahreswert_naehe():
    """Letztes Quartal = Geschaeftsjahresende; TTM ~ Jahreswert (< 2 %)."""
    # ADBE-artig: FY endet 2026-08-31 (Q4). Jahresumsatz = Summe der 4 Quartale.
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31"),
                pd.Timestamp("2026-02-28"), pd.Timestamp("2025-11-30")]
    rev_q = [6.76e9, 6.62e9, 6.40e9, 6.19e9]
    fcf_q = [2.44e9, 2.11e9, 2.92e9, 3.13e9]
    frames = _qframes(quarters, rev_q, fcf_q, sbc_per_q=0.5e9)
    m = _annual_ticker(
        {2026: sum(fcf_q) - 2e9, 2025: 10e9, 2024: 9e9, 2023: 8e9},
        {2026: sum(rev_q), 2025: 20e9, 2024: 19e9, 2023: 18e9},
        {2026: "2026-08-31", 2025: "2025-11-30", 2024: "2024-11-30", 2023: "2023-11-30"},
    )
    res = compute_ttm(m, frames)
    assert res.plausible
    assert not res.fall_back_to_annual
    assert res.deviation < 0.02


def test_ttm_kein_rueckfall_bei_q1_bis_q3():
    """Letztes Quartal mitten im GJ (Q1-Q3) -> kein Jahresvergleich, TTM
    direkt verwendbar (kein Rueckfall), auch wenn TTM vom (partiellen)
    Jahreswert abweicht."""
    # ADBE: letztes Quartal 2026-08-31, aber FY2026 endet erst 2026-11-30
    # -> 2026-08-31 ist Q3, nicht Q4.
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31"),
                pd.Timestamp("2026-02-28"), pd.Timestamp("2025-11-30")]
    frames = _qframes(quarters, [6e9] * 4, [2e9] * 4, sbc_per_q=0.5e9)
    m = _annual_ticker(
        {2026: 23.77e9 - 2e9, 2025: 10e9, 2024: 9e9, 2023: 8e9},
        {2026: 23.77e9, 2025: 20e9, 2024: 19e9, 2023: 18e9},
        {2026: "2026-11-30", 2025: "2025-11-30", 2024: "2024-11-30", 2023: "2023-11-30"},
    )
    res = compute_ttm(m, frames)
    assert res.plausible                      # kein Rueckfall
    assert not res.fall_back_to_annual
    assert math.isnan(res.deviation)          # kein Vergleich durchgefuehrt
    assert any("kein Geschaeftsjahresende" in c for c in res.checks)


def test_ttm_unplausibel_abweichung_ueber_2_prozent():
    """Letztes Quartal = GJ-Ende; TTM weicht > 2 % vom Jahreswert ab
    -> unplausibel + Rueckfall auf Geschaeftsjahre."""
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31"),
                pd.Timestamp("2026-02-28"), pd.Timestamp("2025-11-30")]
    # Quartalsumsatz bewusst doppelt so hoch wie der gemeldete Jahreswert
    frames = _qframes(quarters, [12e9] * 4, [4e9] * 4)
    m = _annual_ticker(
        {2026: 16e9, 2025: 10e9, 2024: 9e9, 2023: 8e9},
        {2026: 24e9, 2025: 20e9, 2024: 19e9, 2023: 18e9},
        {2026: "2026-08-31", 2025: "2025-11-30", 2024: "2024-11-30", 2023: "2023-11-30"},
    )
    res = compute_ttm(m, frames)
    assert not res.plausible
    assert res.fall_back_to_annual
    assert res.deviation > 0.02
    assert any("unplausibel" in c for c in res.checks)


def test_ttm_keine_quartalsdaten_na():
    """Zu wenige Quartale (< 4) -> TTM NaN."""
    quarters = [pd.Timestamp("2026-08-31"), pd.Timestamp("2026-05-31")]
    frames = _qframes(quarters, [6e9, 6e9], [2e9, 2e9])
    res = compute_ttm(TickerMetrics(ticker="T"), frames)
    assert math.isnan(res.ttm["revenue"].value)
    assert math.isnan(res.ttm["fcf_sbc"].value)


# --- DCF: TTM-Basis ----------------------------------------------------------

def _ticker_with_ttm(fy_fcf_sbc: dict[int, float], ttm_fcf_sbc: float,
                     fiscal_ends: dict[int, str], ttm_end: str = "2026-08-31"):
    """Ticker mit Jahresdaten + TTM-Resultat (TTM plausibel)."""
    m = _annual_ticker(fy_fcf_sbc,
                       {fy: 100e9 for fy in fy_fcf_sbc},
                       fiscal_ends)
    ttm = TtmResult(
        ttm={"fcf_sbc": Metric("fcf_sbc", ttm_fcf_sbc, "USD", "USD",
                               int(ttm_end[:4]))},
        quarter_end=ttm_end, base_label=f"TTM bis {ttm_end[:7]}",
        plausible=True,
    )
    m.ttm = ttm
    m.ttm_plausible = True
    m.ttm_fallback = False
    return m


def test_dcf_ttm_basis_mit_nicht_ueberlappenden_gj():
    """Start-FCF = Ø aus TTM + 2 davor liegenden, nicht ueberlappenden GJ.

    ADBE-artig: FY2026 endet 2026-08-31 (ueberlappt das TTM-Fenster) ->
    verwendet werden TTM + FY2025 + FY2024 (FY2026 ausgeschlossen!).
    """
    fiscal_ends = {2026: "2026-08-31", 2025: "2025-08-31",
                   2024: "2024-08-31", 2023: "2023-08-31"}
    fy_fcf = {2026: 999e9, 2025: 30e9, 2024: 20e9, 2023: 10e9}
    m = _ticker_with_ttm(fy_fcf, ttm_fcf_sbc=60e9, fiscal_ends=fiscal_ends)
    res = compute_dcf(m, DCF_CFG)
    assert res.fcf_basis == "ttm"
    assert res.ttm_quarter_end == "2026-08-31"
    # Ø = (60 + 30 + 20) / 3 = 36.67e9 -- NICHT (60+30+20+999)/4
    assert res.fcf_normalized == pytest.approx((60e9 + 30e9 + 20e9) / 3)
    assert res.fcf_years_used == 3
    names = [n for n, _, _ in res.fcf_sources]
    assert names == ["TTM", "FY2025", "FY2024"]


def test_dcf_ttm_rueckfall_bei_unplausibel():
    """TTM unplausibel -> Rueckfall auf Ø letzte 3 Geschaeftsjahre."""
    fiscal_ends = {2026: "2026-08-31", 2025: "2025-08-31",
                   2024: "2024-08-31", 2023: "2023-08-31"}
    fy_fcf = {2026: 30e9, 2025: 20e9, 2024: 10e9, 2023: 5e9}
    m = _ticker_with_ttm(fy_fcf, ttm_fcf_sbc=60e9, fiscal_ends=fiscal_ends)
    m.ttm_plausible = False
    m.ttm_fallback = True
    res = compute_dcf(m, DCF_CFG)
    assert res.fcf_basis == "annual"
    # letzte 3 GJ: 2026, 2025, 2024 -> Ø = 20e9
    assert res.fcf_normalized == pytest.approx((30e9 + 20e9 + 10e9) / 3)


def test_dcf_ttm_rueckfall_wenn_fy_ueberlappt_und_zu_wenig_vorherige():
    """Nur ueberlappende GJ vor dem TTM-Fenster -> Rueckfall auf annual.

    Kalenderjahr-FYs: TTM endet 2026-08-31 -> Fenster startet 2025-12-01
    (9 Monate zurueck). FY2025 endet 2025-12-31 -> ueberlappt (nicht verwendbar),
    FY2024 endet 2024-12-31 -> verwendbar, aber nur 1 GJ -> Rueckfall.
    """
    fiscal_ends = {2025: "2025-12-31", 2024: "2024-12-31", 2023: "2023-12-31"}
    fy_fcf = {2025: 30e9, 2024: 20e9, 2023: 10e9}
    m = _ticker_with_ttm(fy_fcf, ttm_fcf_sbc=60e9, fiscal_ends=fiscal_ends,
                         ttm_end="2026-08-31")
    res = compute_dcf(m, DCF_CFG)
    # Fensterstart 2025-12-01: FY2025 (endet 2025-12-31) ueberlappt,
    # FY2024 (endet 2024-12-31) und FY2023 (endet 2023-12-31) liegen davor
    # -> 2 nicht ueberlappende GJ vorhanden -> TTM-Basis mit FY2024+FY2023
    assert res.fcf_basis == "ttm"
    assert res.fcf_normalized == pytest.approx((60e9 + 20e9 + 10e9) / 3)
    names = [n for n, _, _ in res.fcf_sources]
    assert names == ["TTM", "FY2024", "FY2023"]


def test_dcf_ttm_rueckfall_wenn_alle_fy_ueberlappen():
    """Alle GJ ueberlappen das TTM-Fenster -> Rueckfall auf annual."""
    # TTM endet 2026-08-31, Fenster startet 2025-12-01.
    # Nur FY2026 (endet 2026-08-31) vorhanden -> ueberlappt -> Rueckfall.
    fiscal_ends = {2026: "2026-08-31"}
    m = _ticker_with_ttm({2026: 30e9}, ttm_fcf_sbc=60e9,
                         fiscal_ends=fiscal_ends, ttm_end="2026-08-31")
    res = compute_dcf(m, DCF_CFG)
    assert res.fcf_basis == "annual"
    assert res.fcf_normalized == pytest.approx(30e9)


def test_dcf_ohne_ttm_annual_basis():
    """Kein TTM geladen -> annual (bisheriges Verhalten, abwaertskompatibel)."""
    m = _annual_ticker({2025: 30e9, 2024: 20e9, 2023: 10e9},
                       {2025: 100e9, 2024: 95e9, 2023: 90e9},
                       {2025: "2025-12-31", 2024: "2024-12-31", 2023: "2023-12-31"})
    res = compute_dcf(m, DCF_CFG)
    assert res.fcf_basis == "annual"
    assert res.fcf_normalized == pytest.approx(20e9)


def test_pipeline_flag_ttm_unplausibel(aapl_metrics, cfg):
    """TTM unplausibel -> Flag 'ttm:unplausibel' in der Row + Log."""
    from scoring.pipeline import evaluate_ticker
    ttm = TtmResult(ttm={"fcf_sbc": Metric("fcf_sbc", 1e9, "USD", "USD", 2025)},
                    quarter_end="2026-08-31", plausible=False,
                    fall_back_to_annual=True)
    aapl_metrics.ttm = ttm
    aapl_metrics.ttm_plausible = False
    aapl_metrics.ttm_fallback = True
    res = evaluate_ticker(aapl_metrics, cfg)
    assert "ttm:unplausibel" in res["row"]["flags"]
    assert res["row"]["dcf_fcf_basis"] == "annual"
