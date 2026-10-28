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
    "buy_quality_min": 60,
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
    """Rueckgabe: zwei Tabellen (mos + vps), je 12 Zeilen (4 r x 3 g)."""
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    assert set(sens) == {"mos", "vps"}
    assert len(sens["mos"]) == 12 and len(sens["vps"]) == 12
    rates = set(sens["mos"]["discount_rate"])
    gs = set(sens["mos"]["terminal_growth"])
    assert rates == {0.08, 0.09, 0.10, 0.11}
    assert gs == {0.02, 0.025, 0.03}


def test_sensitivity_center_matches_dcf_base():
    """Zelle (r=10 %, g=2,5 %) entspricht exakt dem Base-Szenario des DCF.

    Erforderlich: Wert bei 9 %/2,5 % (Config-Default) == compute_dcf-Base.
    """
    m = _ticker()
    dcf = compute_dcf(m, DCF_CFG)
    sens = sensitivity_mos_base(m, DCF_CFG)
    center = sens["mos"][(sens["mos"]["discount_rate"] == 0.10)
                         & (sens["mos"]["terminal_growth"] == 0.025)].iloc[0]
    assert center["value_per_share"] == pytest.approx(
        dcf.scenarios["base"].value_per_share, rel=1e-9)
    assert center["mos"] == pytest.approx(dcf.margin_of_safety, rel=1e-9)
    # vps-Tabelle enthaelt denselben Wert
    vps_row = sens["vps"][(sens["vps"]["discount_rate"] == 0.10)
                          & (sens["vps"]["terminal_growth"] == 0.025)].iloc[0]
    assert vps_row["value_per_share"] == pytest.approx(
        dcf.scenarios["base"].value_per_share, rel=1e-9)


def test_sensitivity_center_matches_dcf_base_config_default_9_pct():
    """Mit Config-Default (r=9 %, g=2,5 %): Zelle == compute_dcf-Base exakt."""
    cfg9 = {"dcf": dict(DCF_CFG["dcf"], discount_rate=0.09, terminal_growth=0.025)}
    m = _ticker()
    dcf = compute_dcf(m, cfg9)
    sens = sensitivity_mos_base(m, cfg9)
    center = sens["mos"][(sens["mos"]["discount_rate"] == 0.09)
                         & (sens["mos"]["terminal_growth"] == 0.025)].iloc[0]
    assert center["value_per_share"] == pytest.approx(
        dcf.scenarios["base"].value_per_share, rel=1e-9)
    assert center["mos"] == pytest.approx(dcf.margin_of_safety, rel=1e-9)


def test_sensitivity_explicit_price_parameter():
    """Kurs als Parameter: MoS = 1 - Kurs / Wert je Aktie."""
    m = _ticker()
    price = 100.0
    sens = sensitivity_mos_base(m, DCF_CFG, current_price=price)
    center = sens["mos"][(sens["mos"]["discount_rate"] == 0.10)
                         & (sens["mos"]["terminal_growth"] == 0.025)].iloc[0]
    assert center["mos"] == pytest.approx(1.0 - price / center["value_per_share"], rel=1e-9)
    # Ohne Parameter: Kurs aus Marktkap./Aktien = 1000/10 = 100 -> gleiches Ergebnis
    sens2 = sensitivity_mos_base(m, DCF_CFG)
    center2 = sens2["mos"][(sens2["mos"]["discount_rate"] == 0.10)
                           & (sens2["mos"]["terminal_growth"] == 0.025)].iloc[0]
    assert center2["mos"] == pytest.approx(center["mos"], rel=1e-9)


def test_sensitivity_mos_decreases_with_rate_and_increases_with_growth():
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    grid = {(r["discount_rate"], r["terminal_growth"]): r["mos"]
            for _, r in sens["mos"].iterrows()}
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
    sens = sensitivity_mos_base(m, DCF_CFG)
    assert sens["mos"].empty and sens["vps"].empty


def test_sensitivity_empty_without_market_cap():
    m = _ticker()
    m.market_cap = None
    sens = sensitivity_mos_base(m, DCF_CFG)
    assert sens["mos"].empty and sens["vps"].empty


def test_sensitivity_no_nan_in_grid():
    sens = sensitivity_mos_base(_ticker(), DCF_CFG)
    assert sens["mos"]["mos"].notna().all()
    assert sens["mos"]["value_per_share"].notna().all()
    assert sens["vps"]["value_per_share"].notna().all()
