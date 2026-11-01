"""Tests fuer v37-Anzeigekorrekturen in rohwerte_check.py (keine Aenderung der
Ranking-Logik):
(1) ERKLAERUNG nennt die tatsaechlichen Wachstumsraten je Szenario aus der
    DCF-Funktion (DcfResult.scenario_growth), z. B. "Bear -9.7%, Base -6.7%,
    Bull 0.0%" -- statt des Festtexts "Base-Wachstum 0 %".
(2) Bei Start-FCF <= 0 zeigt die Modus-Tabelle fuer Bear/Base/Bull
    "n/a (Start-FCF <= 0)" statt Zahlen.
"""

import pytest

from data.loader import Metric, TickerMetrics
from valuation.dcf import DcfResult, compute_dcf
import rohwerte_check as rc

DCF_CFG = {"dcf": {
    "discount_rate": 0.10, "terminal_growth": 0.025,
    "base_growth_cap": 0.06, "bull_growth_multiplier": 1.3,
    "bull_growth_cap": 0.10, "fade_to_growth": 0.025,
    "fcf_avg_years": 3, "fcf_mode": "latest", "net_debt_mode": "reported",
    "mos_min_mode": "min", "buy_quality_min": 60,
    "buy_margin_of_safety_min": 0.30, "buy_bear_floor": 0.80,
    "watch_margin_of_safety_min": 0.30,
    "bear_negative_spread": 0.03,
}}


def _mk(cagr: float, fcf: float) -> TickerMetrics:
    m = TickerMetrics(ticker="T", country="US")
    m.market_cap = Metric("market_cap", 100e9, "USD", "USD", 2025)
    rev0 = 100e9
    for fy in range(2021, 2026):
        rev = rev0 * (1.0 + cagr) ** (fy - 2021)
        m.years[fy] = {
            "revenue": Metric("revenue", rev, "USD", "USD", fy),
            "fcf": Metric("fcf", fcf, "USD", "USD", fy),
            "fcf_sbc": Metric("fcf_sbc", fcf, "USD", "USD", fy),
            "shares_diluted": Metric("shares_diluted", 2e9, "shares", "USD", fy),
            "net_debt": Metric("net_debt", 0.0, "USD", "USD", fy),
        }
        m.fiscal_ends[fy] = f"{fy}-12-31"
    return m


# ---------- (1) Erklaerung mit tatsaechlichen Szenario-Wachstumsraten ----------

def test_fmt_scenario_growth_mit_cagr_negativ():
    """CAGR < 0 (z. B. XOM -6.7 %): Bear = CAGR - 3 pp, Base = CAGR, Bull = 0 %."""
    m = _mk(cagr=-0.067, fcf=20e9)
    d = compute_dcf(m, DCF_CFG, fcf_mode="latest")
    txt = rc.fmt_scenario_growth(d)
    assert "Bear -9.7%" in txt
    assert "Base -6.7%" in txt
    assert "Bull 0.0%" in txt
    assert "Base-Wachstum 0 %" not in txt  # Festtext darf nicht mehr vorkommen


def test_fmt_scenario_growth_mit_cagr_positiv():
    """CAGR >= 0: Bear 0 %, Base = CAGR, Bull = CAGR*1.3."""
    m = _mk(cagr=0.04, fcf=20e9)
    d = compute_dcf(m, DCF_CFG, fcf_mode="latest")
    txt = rc.fmt_scenario_growth(d)
    assert "Bear 0.0%" in txt and "Base 4.0%" in txt and "Bull 5.2%" in txt


def test_erklaerung_xom_nennt_szenario_wachstum():
    """erklaerung_xom() enthaelt die Zeile mit Szenario-Wachstum aus scenario_growth."""
    m = _mk(cagr=-0.067, fcf=20e9)
    modes = {mode: compute_dcf(m, DCF_CFG, fcf_mode=mode)
             for mode in ("avg3", "latest", "ttm", "ttm_only")}
    xo = {"dcf": compute_dcf(m, DCF_CFG), "price": 178.02, "modes": modes}
    lines = rc.erklaerung_xom(xo)
    text = "\n".join(lines)
    assert text.startswith("XOM (MoS < -100 %):")
    assert "Szenario-Wachstum J. 1-5: Bear -9.7%, Base -6.7%, Bull 0.0%" in text
    assert "Base-Wachstum 0 %" not in text
    assert len(lines) == 4  # Ueberschrift + 3 Saetze


# ---------- (2) Start-FCF <= 0 -> "n/a (Start-FCF <= 0)" statt Zahlen ----------

def test_fmt_szenario_vps_bei_fcf_le0():
    """fcf_le0=True -> alle drei Szenarien 'n/a (Start-FCF <= 0)'."""
    m = _mk(cagr=0.04, fcf=-1.45e9)  # Start-FCF negativ (wie DOW latest)
    d = compute_dcf(m, DCF_CFG, fcf_mode="latest")
    assert d.fcf_le0 is True
    bear, base, bull = rc.fmt_szenario_vps(d)
    assert bear == "n/a (Start-FCF \u2264 0)"
    assert base == "n/a (Start-FCF \u2264 0)"
    assert bull == "n/a (Start-FCF \u2264 0)"


def test_fmt_szenario_vps_bei_normalem_fcf_zeigt_zahlen():
    """fcf_le0=False -> normale Zahlen aus den Szenarien (kein n/a-Text)."""
    m = _mk(cagr=0.04, fcf=20e9)
    d = compute_dcf(m, DCF_CFG, fcf_mode="latest")
    assert d.fcf_le0 is False
    bear, base, bull = rc.fmt_szenario_vps(d)
    for s in (bear, base, bull):
        assert "n/a" not in s  # formatierte Zahl, z. B. "148.48"
    assert float(bear) <= float(base) <= float(bull)  # Bear <= Base <= Bull


def test_fmt_szenario_vps_mit_leerem_dcf_result():
    """DcfResult ohne Szenarien (z. B. Sektor-Sonderregel) -> 'n/a' je Szenario."""
    d = DcfResult(fcf_normalized=float("nan"), fcf_years_used=0, revenue_cagr=float("nan"),
                  discount_rate=0.09, terminal_growth=0.025, shares=float("nan"),
                  fcf_mode="n/a (Sonderregel)")
    assert rc.fmt_szenario_vps(d) == ("n/a", "n/a", "n/a")
