"""Tests fuer die Behandlung kurzer Historien (Punkte 1 und 2 der Scorecard-Fixes).

(1) fcf_positive_years bewertet den Anteil positiver Jahre an den VERFUEGBAREN
    Jahren (mindestens 4), nicht gegen 10. Volle Punkte bei 100 %, null bei
    <= 50 %. years_total traegt die Fensterlaenge fuer die Anzeige "x / y".
(2) revenue_cagr_5y und gross_margin_trend nutzen die verfuegbaren Jahre
    (mindestens 4 Punkte = 3 Intervalle), konsistent mit der CAGR im DCF.
"""

import pytest

from data.loader import Metric, TickerMetrics
from scoring.criteria import compute_criteria
from scoring.score import interpolate, score_ticker

CFG = {
    "data": {
        "thin_years": 5,
        "min_points_5y": 3,
        "min_points_3y": 2,
        "min_points_10y": 5,
        "cagr_min_points": 4,
        "fcf_pos_min_years": 4,
        "trend_min_points": 4,
    }
}


def _ticker(fcf_vals: list[float], revenue_vals: list[float] | None = None,
            gross_margins: list[float] | None = None, start_year: int = 2022) -> TickerMetrics:
    """Synthetischer Ticker mit wählbarer Historienlänge."""
    m = TickerMetrics(ticker="TEST")
    n = len(fcf_vals)
    for i, fy in enumerate(range(start_year, start_year + n)):
        ym = {
            "fcf": Metric("fcf", fcf_vals[i], "USD", "USD", fy),
            "revenue": Metric("revenue", (revenue_vals or [100e9] * n)[i], "USD", "USD", fy),
        }
        if gross_margins is not None:
            ym["gross_profit"] = Metric("gross_profit", gross_margins[i] * ym["revenue"].value,
                                        "USD", "USD", fy)
        m.years[fy] = ym
    return m


# --- (1) fcf_positive_years ---------------------------------------------------

def test_fcf_positive_years_4_of_4_is_full_points():
    """4 verfuegbare Jahre, alle positiv -> Anteil 100 % -> volle Punkte (nicht 4/10)."""
    m = _ticker([10e9, 11e9, 12e9, 13e9])
    crit = compute_criteria(m, CFG)["fcf_positive_years"]
    assert not crit.is_na
    assert crit.value == pytest.approx(1.0)          # 4 / 4 = 100 %
    assert crit.years_total == 4                      # Fensterlaenge fuer Anzeige "4 / 4"
    assert crit.years_available == 4
    assert crit.thin                                   # 4 < thin_years (5)


def test_fcf_positive_years_3_of_4_interpolates():
    """3 von 4 Jahren positiv -> 75 % -> 50 Punkte (linear 50 %..100 %)."""
    m = _ticker([10e9, -1e9, 12e9, 13e9])
    crit = compute_criteria(m, CFG)["fcf_positive_years"]
    assert crit.value == pytest.approx(0.75)
    assert interpolate(crit.value, "higher", 1.0, 0.5) == pytest.approx(50.0)


def test_fcf_positive_years_2_of_4_is_zero_points():
    """2 von 4 Jahren positiv -> 50 % -> null Punkte."""
    m = _ticker([10e9, -1e9, -2e9, 13e9])
    crit = compute_criteria(m, CFG)["fcf_positive_years"]
    assert crit.value == pytest.approx(0.5)
    assert interpolate(crit.value, "higher", 1.0, 0.5) == pytest.approx(0.0)


def test_fcf_positive_years_na_below_4_years():
    """Weniger als 4 verfuegbare Jahre -> n/a."""
    m = _ticker([10e9, 11e9, 12e9])
    crit = compute_criteria(m, CFG)["fcf_positive_years"]
    assert crit.is_na


def test_fcf_positive_years_uses_available_not_10():
    """Regression: frueher wurde 4 gegen 10 gerechnet (40 % -> 0 Punkte)."""
    m = _ticker([10e9, 11e9, 12e9, 13e9])
    crit = compute_criteria(m, CFG)["fcf_positive_years"]
    assert crit.value == pytest.approx(1.0), "Anteil an verfuegbaren Jahren, nicht an 10"


# --- (2) revenue_cagr_5y -----------------------------------------------------

def test_revenue_cagr_uses_available_years():
    """CAGR ueber alle verfuegbaren Jahre (4 Punkte = 3 Intervalle), wie im DCF."""
    # 100 -> 108.1793 ueber 3 Intervalle = 2,5 % p. a.
    revs = [100e9, 102.5e9, 105.0625e9, 107.6891e9]
    m = _ticker([10e9] * 4, revenue_vals=revs)
    crit = compute_criteria(m, CFG)["revenue_cagr_5y"]
    assert not crit.is_na
    expected = (revs[-1] / revs[0]) ** (1 / 3) - 1
    assert crit.value == pytest.approx(expected, rel=1e-9)
    assert crit.value == pytest.approx(0.025, rel=1e-3)
    assert crit.years_available == 4


def test_revenue_cagr_na_below_4_points():
    m = _ticker([10e9] * 3, revenue_vals=[100e9, 101e9, 102e9])
    crit = compute_criteria(m, CFG)["revenue_cagr_5y"]
    assert crit.is_na


def test_revenue_cagr_matches_dcf_cagr():
    """Konsistenz mit valuation/dcf.py: beide nutzen CAGR ueber verfuegbare Jahre."""
    from valuation.dcf import _cagr
    revs = [100e9, 104e9, 108e9, 112e9]
    m = _ticker([10e9] * 4, revenue_vals=revs)
    crit = compute_criteria(m, CFG)["revenue_cagr_5y"]
    assert crit.value == pytest.approx(_cagr(revs))


# --- (2) gross_margin_trend --------------------------------------------------

def test_gross_margin_trend_with_4_points():
    """Bruttomarge ueber 4 Punkte (3 Intervalle) -> Steigung bestimmbar."""
    margins = [0.40, 0.42, 0.44, 0.46]   # +2 PP pro Jahr
    m = _ticker([10e9] * 4, gross_margins=margins)
    crit = compute_criteria(m, CFG)["gross_margin_trend"]
    assert not crit.is_na
    assert crit.value == pytest.approx(2.0)   # 2 Prozentpunkte pro Jahr


def test_gross_margin_trend_na_below_4_points():
    m = _ticker([10e9] * 3, gross_margins=[0.40, 0.42, 0.44])
    crit = compute_criteria(m, CFG)["gross_margin_trend"]
    assert crit.is_na


def test_gross_margin_trend_full_history_still_works(aapl_metrics, cfg):
    """AAPL (5 Jahre) bleibt berechenbar und nicht duenn-beeinflusst."""
    crits = compute_criteria(aapl_metrics, cfg)
    gm = crits["gross_margin_trend"]
    assert not gm.is_na
    assert gm.years_available == 5
