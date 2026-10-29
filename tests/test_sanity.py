"""Tests fuer den Sanity-Check (plausible Bereiche, NaN = n/a nie Alarm)."""

import logging
import math

import pytest

from data.loader import Metric, TickerMetrics
from data.metrics import fcf_yield
from data.sanity import check_ticker

SANITY_CFG = {
    "fcf_yield": [-0.50, 0.50],
    "roic": [-1.0, 5.0],
    "roe": [-2.0, 2.0],
    "net_debt_ebitda": [-10.0, 50.0],
    "interest_coverage": [-100.0, 1000.0],
    "ev_ebit": [0.0, 200.0],
    "gross_margin": [-1.0, 1.5],
    "fcf_margin": [-1.0, 1.0],
    "revenue_cagr": [-0.9, 3.0],
    "market_cap_over_revenue": [0.01, 1000.0],
}


def _metric(name, value, currency="USD", fy=2024):
    return Metric(name, value, currency, currency, fy)


def _ticker(latest_year: dict, market_cap: float | None = 100e9) -> TickerMetrics:
    m = TickerMetrics(ticker="TEST")
    m.years = {2024: latest_year}
    if market_cap is not None:
        m.market_cap = _metric("market_cap", market_cap)
    return m


def test_implausible_fcf_yield_logged(caplog):
    # mktCap absichtlich 1e6 zu klein -> FCF-Yield x1.000.000
    ym = {
        "revenue": _metric("revenue", 100e9),
        "ebit": _metric("ebit", 10e9),
        "ebitda": _metric("ebitda", 15e9),
        "fcf": _metric("fcf", 10e9),
        "net_debt": _metric("net_debt", 5e9),
        "equity": _metric("equity", 50e9),
        "interest_expense": _metric("interest_expense", 1e9),
        "gross_profit": _metric("gross_profit", 40e9),
    }
    m = _ticker(ym, market_cap=10e3)  # 10 Tsd. statt 100 Mrd.
    with caplog.at_level("WARNING", logger="value_screener.sanity"):
        violations = check_ticker(m, SANITY_CFG)
    assert violations
    assert any("market_cap_over_revenue" in v for v in violations)
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_nan_is_na_not_violation(caplog):
    ym = {
        "revenue": _metric("revenue", float("nan")),
        "ebit": _metric("ebit", float("nan")),
        "ebitda": _metric("ebitda", float("nan")),
        "fcf": _metric("fcf", float("nan")),
        "net_debt": _metric("net_debt", float("nan")),
        "equity": _metric("equity", float("nan")),
        "interest_expense": _metric("interest_expense", float("nan")),
        "gross_profit": _metric("gross_profit", float("nan")),
    }
    m = _ticker(ym, market_cap=float("nan"))
    with caplog.at_level("WARNING", logger="value_screener.sanity"):
        violations = check_ticker(m, SANITY_CFG)
    assert violations == []
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_implausible_roic_logged(caplog):
    # Investiertes Kapital nahe 0 -> ROIC riesig
    ym = {
        "revenue": _metric("revenue", 100e9),
        "ebit": _metric("ebit", 10e9),
        "ebitda": _metric("ebitda", 15e9),
        "fcf": _metric("fcf", 10e9),
        "net_debt": _metric("net_debt", -49.999e9),  # EK fast ausgeloescht
        "equity": _metric("equity", 50e9),
        "interest_expense": _metric("interest_expense", 1e9),
        "income_tax_expense": _metric("income_tax_expense", 2e9),
        "income_before_tax": _metric("income_before_tax", 8e9),
        "gross_profit": _metric("gross_profit", 40e9),
    }
    m = _ticker(ym)
    with caplog.at_level("WARNING", logger="value_screener.sanity"):
        check_ticker(m, SANITY_CFG)
    assert any("roic" in r.message for r in caplog.records if r.levelname == "WARNING")


def test_plausible_ticker_no_warnings(aapl_metrics, cfg, caplog):
    with caplog.at_level("WARNING", logger="value_screener.sanity"):
        violations = check_ticker(aapl_metrics, cfg["sanity"])
    assert violations == []
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_sanity_detects_million_scaling_bug(aapl_metrics, cfg, caplog):
    """Reproduziert den urspruenglichen Bug: mktCap faelschlich /1e6 -> Alarm."""
    buggy = aapl_metrics
    buggy.market_cap.value = buggy.market_cap.value / 1e6  # Mio.-Skalierung (Bug)
    with caplog.at_level("WARNING", logger="value_screener.sanity"):
        violations = check_ticker(buggy, cfg["sanity"])
    assert violations, "Sanity-Check muss den Skalenfehler erkennen"
    assert any("market_cap_over_revenue" in v for v in violations)
    y = fcf_yield(buggy, 2024)
    assert y > 1000.0  # der gemeldete Fehler
