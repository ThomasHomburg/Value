"""Tests fuer die DCF-Sensitivitaet (valuation/dcf.py: sensitivity_mos_base).

MoS (Base) ueber Diskontsatz x Terminal Growth (8/9/10/11 % x 2/2,5/3 %).
"""

import math

import pytest

from data.loader import Metric, TickerMetrics
from valuation.dcf import compute_dcf, sensitivity_mos_base

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


def _ticker(fcf_sbc: float = 100.0, mcap: float = 1000.0, shares: float = 10.0,
            cagr: float = 0.05) -> TickerMetrics:
    m = TickerMetrics(ticker="TEST")
    m.market_cap = Metric("market_cap", mcap, "USD", "USD", 2025)
    for i, fy in enumerate((2023, 2024, 2025)):
        m.years[fy] = {
            "fcf_sbc": Metric("fcf_sbc", fcf_sbc, "USD", "USD", fy),
            "revenue": Metric("revenue", 1000.0 * (1 + cagr) ** i, "USD", "USD", fy),
            "shares_diluted": Metric("shares_diluted", shares, "shares", "USD", fy),
        }
    return m


def test_sensitivity_grid_4x3():
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    assert len(sens) == 12  # 4 Diskontsaetze x 3 Terminal Growths
    rates = {s["discount_rate"] for s in sens}
    gs = {s["terminal_growth"] for s in sens}
    assert rates == {0.08, 0.09, 0.10, 0.11}
    assert gs == {0.02, 0.025, 0.03}


def test_sensitivity_center_matches_dcf_base():
    """Zelle (r=10 %, g=2,5 %) entspricht exakt dem Base-Szenario des DCF."""
    m = _ticker()
    dcf = compute_dcf(m, DCF_CFG)
    sens = sensitivity_mos_base(m, DCF_CFG)
    center = next(s for s in sens
                  if s["discount_rate"] == 0.10 and s["terminal_growth"] == 0.025)
    assert center["value_per_share"] == pytest.approx(
        dcf.scenarios["base"].value_per_share, rel=1e-9)
    assert center["mos"] == pytest.approx(dcf.margin_of_safety, rel=1e-9)


def test_sensitivity_mos_decreases_with_rate_and_increases_with_growth():
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    grid = {(s["discount_rate"], s["terminal_growth"]): s["mos"] for s in sens}
    # hoeherer Diskontsatz -> niedrigerer MoS (bei gleichem g)
    for g in (0.02, 0.025, 0.03):
        assert grid[(0.08, g)] > grid[(0.09, g)] > grid[(0.10, g)] > grid[(0.11, g)]
    # hoeheres Terminal Growth -> hoeherer MoS (bei gleichem r)
    for r in (0.08, 0.09, 0.10, 0.11):
        assert grid[(r, 0.02)] < grid[(r, 0.025)] < grid[(r, 0.03)]


def test_sensitivity_empty_without_fcf_sbc():
    m = _ticker()
    for fy in m.years:
        m.years[fy]["fcf_sbc"] = Metric("fcf_sbc", float("nan"), "USD", "USD", fy)
    assert sensitivity_mos_base(m, DCF_CFG) == []


def test_sensitivity_empty_without_market_cap():
    m = _ticker()
    m.market_cap = None
    assert sensitivity_mos_base(m, DCF_CFG) == []


def test_sensitivity_no_nan_in_grid():
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    assert all(s["mos"] == s["mos"] for s in sens)
    assert all(s["value_per_share"] == s["value_per_share"] for s in sens)
