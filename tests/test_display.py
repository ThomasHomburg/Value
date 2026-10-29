"""Tests fuer Anzeige-Hilfen: country_code (Land-Kuerzel) und market_cap_date."""

from data.demo import AAPL_BALANCE, AAPL_CASHFLOW, AAPL_INCOME, AAPL_PROFILE
from data.loader import country_code, extract_metrics


def test_country_code_bekannte_laender():
    assert country_code("US") == "US"
    assert country_code("United States") == "US"
    assert country_code("Germany") == "DE"
    assert country_code("Deutschland") == "DE"
    assert country_code("Denmark") == "DK"
    assert country_code("Netherlands") == "NL"


def test_country_code_unbekannt_und_leer():
    assert country_code("") == "?"
    assert country_code("Wakanda") == "WA"   # Fallback: erste 2 Buchstaben


def test_market_cap_date_gesetzt(aapl_metrics):
    # Stichtag der Marktkapitalisierung ist ein ISO-Datum (YYYY-MM-DD)
    assert aapl_metrics.market_cap_date
    y, m, d = aapl_metrics.market_cap_date.split("-")
    assert len(y) == 4 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31


def test_market_cap_date_default_leer():
    m = extract_metrics("X", [], [], [], None)
    assert m.market_cap_date == ""
    assert m.market_cap is None
