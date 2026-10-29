"""Tests fuer die Provider-Schnittstelle (data/providers/) und 'Daten duenn'.

Abgedeckt:
- split_suffix: Ticker mit/ohne Boersen-Suffix
- select_provider: Suffix-Map, US->FMP (mit Key), Fallback yfinance, force-Override
- build_providers: Registry mit/ohne FMP_API_KEY
- FmpProvider: normalisiertes Schema + source='fmp', Fehler ohne Key
- YfinanceProvider (gemockt): Row-Mapping, FCF/Net-Debt-Fallbacks, Schema, years-Truncation
- load_with_provider: setzt source pro Ticker
- Demo-Daten haben source='demo'
- 'Daten duenn': Kriterium mit < thin_years Jahren -> thin=True, Pipeline-Flag + Log
- Quelle pro Ticker wird geloggt (Pipeline) und gesetzt (load_with_provider)
"""

import math
from types import SimpleNamespace

import pandas as pd
import pytest

from data.demo import AAPL_BALANCE, AAPL_CASHFLOW, AAPL_INCOME, AAPL_PROFILE, demo_companies
from data.fmp_client import FMPClient
from data.loader import TickerMetrics
from data.providers.base import (
    ProviderError,
    build_providers,
    load_with_provider,
    select_provider,
    split_suffix,
)
from data.providers.fmp import FmpProvider
from data.providers.yfinance_provider import YfinanceProvider
from scoring.criteria import compute_criteria
from scoring.pipeline import evaluate_ticker


# --- split_suffix ------------------------------------------------------------

@pytest.mark.parametrize("ticker,base,suffix", [
    ("AAPL", "AAPL", None),
    ("BRK-B", "BRK-B", None),
    ("SAP.DE", "SAP", ".DE"),
    ("ASML.AS", "ASML", ".AS"),
    ("NOVO-B.CO", "NOVO-B", ".CO"),
    ("SAP.PA", "SAP", ".PA"),
    ("sap.de", "SAP", ".DE"),   # Gross-/Kleinschreibung egal
])
def test_split_suffix(ticker, base, suffix):
    assert split_suffix(ticker) == (base, suffix)


# --- select_provider ---------------------------------------------------------

def _providers(with_fmp: bool = True) -> dict:
    prows = {"yfinance": YfinanceProvider()}
    if with_fmp:
        prows["fmp"] = FmpProvider(FMPClient("test-key"))
    return prows


def test_select_suffix_map_routes_to_yfinance(cfg):
    prows = _providers()
    assert select_provider("SAP.DE", cfg, prows).name == "yfinance"
    assert select_provider("ASML.AS", cfg, prows).name == "yfinance"
    assert select_provider("NOVO-B.CO", cfg, prows).name == "yfinance"
    assert select_provider("JOD.L", cfg, prows).name == "yfinance"


def test_select_us_prefers_fmp_when_available(cfg):
    assert select_provider("AAPL", cfg, _providers(True)).name == "fmp"


def test_select_us_falls_back_to_yfinance_without_fmp(cfg):
    assert select_provider("AAPL", cfg, _providers(False)).name == "yfinance"


def test_select_force_overrides_suffix(cfg):
    cfg2 = {"providers": {"force": "yfinance", "suffix_map": {".DE": "fmp"}}}
    assert select_provider("SAP.DE", cfg2, _providers(True)).name == "yfinance"
    assert select_provider("AAPL", cfg2, _providers(True)).name == "yfinance"


def test_select_force_unknown_provider_raises():
    cfg2 = {"providers": {"force": "bloomberg"}}
    with pytest.raises(ProviderError):
        select_provider("AAPL", cfg2, _providers(True))


def test_select_unknown_suffix_uses_default():
    cfg2 = {"providers": {"default": "yfinance", "suffix_map": {}}}
    assert select_provider("XYZ.XY", cfg2, _providers(False)).name == "yfinance"


def test_select_suffix_mapped_to_missing_provider_raises():
    cfg2 = {"providers": {"suffix_map": {".DE": "fmp"}}}
    with pytest.raises(ProviderError):
        select_provider("SAP.DE", cfg2, {"yfinance": YfinanceProvider()})


def test_select_logs_choice(cfg, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="value_screener.providers"):
        select_provider("SAP.DE", cfg, _providers(True))
    assert any("SAP.DE" in r.message and "Quelle=yfinance" in r.message for r in caplog.records)


# --- build_providers ---------------------------------------------------------

def test_build_providers_without_key():
    prows = build_providers("")
    assert set(prows) == {"yfinance"}


def test_build_providers_with_key():
    prows = build_providers("test-key")
    assert set(prows) == {"fmp", "yfinance"}
    assert prows["fmp"].client.configured


# --- FmpProvider -------------------------------------------------------------

class _FakeFMPClient:
    """FMPClient-Ersatz mit Fixture-Daten (kein Netzwerk)."""

    configured = True

    def income_statements(self, ticker, years=5):
        return AAPL_INCOME[:years]
    def balance_sheets(self, ticker, years=5):
        return AAPL_BALANCE[:years]
    def cash_flows(self, ticker, years=5):
        return AAPL_CASHFLOW[:years]
    def profile(self, ticker):
        return AAPL_PROFILE


def test_fmp_provider_loads_normalized_schema():
    m = FmpProvider(_FakeFMPClient()).load("AAPL")
    assert m.source == "fmp"
    assert m.ticker == "AAPL"
    assert m.market_cap.value == pytest.approx(5.07e12)
    assert m.market_cap.currency == "USD"
    assert len(m.years) == 5
    fcf24 = m.years[2024]["fcf"]
    assert fcf24.value == pytest.approx(108807000000)   # absolut USD
    assert fcf24.currency == "USD"
    assert fcf24.fiscal_year == 2024


def test_fmp_provider_without_key_raises():
    with pytest.raises(ProviderError):
        FmpProvider(FMPClient("")).load("AAPL")


# --- YfinanceProvider (gemockt) ---------------------------------------------

def _yf_module(ticker_obj):
    return SimpleNamespace(Ticker=lambda t: ticker_obj)


def _frames(cols, rows):
    """bows: {row_label: [wert_pro_spalte]} -> DataFrame mit Timestamps-Spalten."""
    labels = list(rows)
    data = [[rows[label][i] for label in labels] for i in range(len(cols))]
    return pd.DataFrame(data, index=cols, columns=labels).T


FIN_ROWS = {
    "Total Revenue": [100e9, 90e9],
    "Gross Profit": [40e9, 35e9],
    "Operating Income": [30e9, 25e9],
    "EBITDA": [45e9, 40e9],
    "Net Income": [20e9, 18e9],
    "Interest Expense": [-1e9, -0.8e9],   # yfinance berichtet teils negativ
    "Income Tax Expense": [5e9, 4e9],
    "Pretax Income": [25e9, 21e9],
    "Diluted Average Shares": [10e9, 10e9],
}
BAL_ROWS = {
    "Stockholders Equity": [50e9, 45e9],
    "Total Debt": [10e9, 8e9],
    "Cash And Cash Equivalents": [40e9, 38e9],   # kein 'Net Debt' -> Fallback Total Debt - Cash
}
CF_ROWS = {
    "Operating Cash Flow": [80e9, 70e9],
    "Capital Expenditure": [-5e9, -4e9],          # kein 'Free Cash Flow' -> Fallback OCF + Capex
    "Stock Based Compensation": [3e9, 2e9],
}
COLS = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")]
INFO = {"currency": "EUR", "marketCap": 200e9, "longName": "Test AG",
        "sector": "Industrials", "country": "Germany"}


def _load_yf(years=5, info=INFO, fin_rows=FIN_ROWS, bal_rows=BAL_ROWS, cf_rows=CF_ROWS, cols=COLS):
    tk = SimpleNamespace(
        info=info,
        financials=_frames(cols, fin_rows),
        balance_sheet=_frames(cols, bal_rows),
        cashflow=_frames(cols, cf_rows),
    )
    prov = YfinanceProvider()
    prov._yf = _yf_module(tk)
    return prov.load("TEST.DE", years=years)


def test_yfinance_provider_normalized_schema():
    m = _load_yf()
    assert m.source == "yfinance"
    assert m.name == "Test AG"
    assert m.sector == "Industrials"
    assert m.country == "Germany"
    assert sorted(m.years) == [2024, 2025]
    y25 = m.years[2025]
    assert y25["revenue"].value == pytest.approx(100e9)
    assert y25["revenue"].currency == "EUR"   # Konvention wie FMP-Loader: unit=Waehrung, currency=ISO
    assert y25["revenue"].unit == "currency"  # Konvention wie FMP-Loader: unit=Waehrung, currency=ISO
    assert y25["revenue"].fiscal_year == 2025
    # Marktkap in Quote-Waehrung, absolut
    assert m.market_cap.value == pytest.approx(200e9)
    assert m.market_cap.currency == "EUR"


def test_yfinance_provider_fcf_fallback_ocf_plus_capex():
    y25 = _load_yf().years[2025]
    # kein 'Free Cash Flow'-Row -> OCF 80e9 + Capex (-5e9) = 75e9
    assert y25["fcf"].value == pytest.approx(75e9)
    assert y25["fcf"].currency == "EUR"


def test_yfinance_provider_fcf_sbc(monkeypatch):
    y25 = _load_yf().years[2025]
    # FCF 75e9 - SBC 3e9 = 72e9
    assert y25["fcf_sbc"].value == pytest.approx(72e9)
    assert y25["fcf_sbc"].currency == "EUR"
    # Roh-FCF bleibt unveraendert
    assert y25["fcf"].value == pytest.approx(75e9)


def test_yfinance_provider_fcf_sbc_nan_without_sbc_row():
    # 'Stock Based Compensation'-Row entfernen -> fcf_sbc = NaN, nie Roh-FCF
    cf_rows = {k: v for k, v in CF_ROWS.items() if k != "Stock Based Compensation"}
    y25 = _load_yf(cf_rows=cf_rows).years[2025]
    assert math.isnan(y25["fcf_sbc"].value)
    assert y25["fcf"].value == pytest.approx(75e9)


def test_yfinance_provider_prefers_reported_fcf():
    cf_rows = dict(CF_ROWS, **{"Free Cash Flow": [77e9, 66e9]})
    y25 = _load_yf(cf_rows=cf_rows).years[2025]
    assert y25["fcf"].value == pytest.approx(77e9)   # gemeldeter FCF gewinnt


def test_yfinance_provider_net_debt_fallback_total_debt_minus_cash():
    y25 = _load_yf().years[2025]
    # kein 'Net Debt'-Row -> Total Debt 10e9 - Cash 40e9 = -30e9 (Net Cash)
    assert y25["net_debt"].value == pytest.approx(-30e9)


def test_yfinance_provider_prefers_reported_net_debt():
    bal_rows = dict(BAL_ROWS, **{"Net Debt": [-2e9, -1e9]})
    y25 = _load_yf(bal_rows=bal_rows).years[2025]
    assert y25["net_debt"].value == pytest.approx(-2e9)   # gemeldetes Net Debt gewinnt


def test_yfinance_provider_interest_expense_abs():
    y25 = _load_yf().years[2025]
    assert y25["interest_expense"].value == pytest.approx(1e9)


def test_yfinance_provider_truncates_to_years():
    cols = [pd.Timestamp(f"{y}-12-31") for y in (2025, 2024, 2023)]
    fin_rows = {k: v * 3 for k, v in ((k, [10.0]) for k in FIN_ROWS)}
    # drei Spalten, gleiche Werte je Spalte
    fin_rows = {k: [v[0]] * 3 for k, v in FIN_ROWS.items()}
    bal_rows = {k: [v[0]] * 3 for k, v in BAL_ROWS.items()}
    cf_rows = {k: [v[0]] * 3 for k, v in CF_ROWS.items()}
    m = _load_yf(years=2, fin_rows=fin_rows, bal_rows=bal_rows, cf_rows=cf_rows, cols=cols)
    assert sorted(m.years) == [2024, 2025]


def test_yfinance_provider_currency_fallback(caplog):
    info = {"financialCurrency": "DKK", "marketCap": 300e9}   # currency fehlt
    m = _load_yf(info=info)
    assert m.years[2025]["revenue"].currency == "DKK"


def test_yfinance_provider_empty_financials_raises():
    tk = SimpleNamespace(info={}, financials=pd.DataFrame(),
                         balance_sheet=pd.DataFrame(), cashflow=pd.DataFrame())
    prov = YfinanceProvider()
    prov._yf = _yf_module(tk)
    with pytest.raises(ProviderError):
        prov.load("XXX")


# --- load_with_provider ------------------------------------------------------

def test_load_with_provider_sets_source(cfg):
    class _Dummy:
        name = "yfinance"

        def supports(self, ticker):
            return True

        def load(self, ticker, years=5):
            return TickerMetrics(ticker=ticker)

    m = load_with_provider("SAP.DE", cfg, {"yfinance": _Dummy()}, years=5)
    assert m.source == "yfinance"


def test_demo_companies_have_source():
    assert all(c.source == "demo" for c in demo_companies())


# --- 'Daten duenn' -----------------------------------------------------------

def test_criterion_thin_when_metric_has_fewer_years(aapl_metrics, cfg):
    # gross_profit in 2 Jahren entfernen -> Bruttomarge nur 3 Jahre
    for fy in (2021, 2022):
        aapl_metrics.years[fy]["gross_profit"].value = float("nan")
    crits = compute_criteria(aapl_metrics, cfg)
    gm = crits["gross_margin_trend"]
    assert gm.years_available == 3
    assert gm.thin  # 3 < thin_years (5)
    assert not crits["roic_avg5"].thin
    assert crits["roic_avg5"].years_available == 5


def test_criterion_full_history_not_thin(aapl_metrics, cfg):
    crits = compute_criteria(aapl_metrics, cfg)
    assert crits["roic_avg5"].years_available == 5
    assert not crits["roic_avg5"].thin


def test_pipeline_marks_thin_criteria_in_row_and_log(aapl_metrics, cfg, caplog):
    import logging
    for fy in (2021, 2022):
        aapl_metrics.years[fy]["gross_profit"].value = float("nan")
    with caplog.at_level(logging.INFO, logger="value_screener.pipeline"):
        res = evaluate_ticker(aapl_metrics, cfg)
    assert res["row"] is not None
    assert "gross_margin_trend" in res["thin_criteria"]
    assert "duenn" in res["row"]["flags"]
    assert any("Daten duenn" in r.message for r in caplog.records)


def test_pipeline_logs_source_per_ticker(aapl_metrics, cfg, caplog):
    import logging
    aapl_metrics.source = "yfinance"
    with caplog.at_level(logging.INFO, logger="value_screener.pipeline"):
        evaluate_ticker(aapl_metrics, cfg)
    assert any("AAPL" in r.message and "Quelle=yfinance" in r.message for r in caplog.records)
