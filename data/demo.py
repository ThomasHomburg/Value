"""Demo-Daten: AAPL aus echten oeffentlichen Daten + synthetische Referenzunternehmen.

 Wird verwendet von tests/conftest.py, run_ranking.py und app.py (Streamlit),
damit alle drei dieselben Fixture-Daten nutzen. Ohne FMP_API_KEY laeuft die
gesamte Pipeline auf diesen Daten (Demo-Modus).
"""

from __future__ import annotations

from data.loader import TickerMetrics, extract_metrics

AAPL_PROFILE = {
    "symbol": "AAPL",
    "companyName": "Apple Inc.",
    "sector": "Technology",
    "country": "US",
    "currency": "USD",
    "mktCap": 5.07e12,   # ca. 1,49 Mrd. Aktien x 347,73 USD (aktuell, absolut)
}

AAPL_INCOME = [
    {"date": "2021-09-25", "calendarYear": "2021", "reportedCurrency": "USD", "period": "FY", "revenue": 365817000000, "grossProfit": 152836000000, "operatingIncome": 108949000000, "ebitda": 120233000000, "netIncome": 94680000000, "interestExpense": -2645000000, "incomeTaxExpense": 14527000000, "incomeBeforeTax": 109207000000, "weightedAverageSharesDiluted": 16864700000},
    {"date": "2022-09-24", "calendarYear": "2022", "reportedCurrency": "USD", "period": "FY", "revenue": 394328000000, "grossProfit": 170782000000, "operatingIncome": 119437000000, "ebitda": 130541000000, "netIncome": 99803000000, "interestExpense": -2931000000, "incomeTaxExpense": 19300000000, "incomeBeforeTax": 119103000000, "weightedAverageSharesDiluted": 16326000000},
    {"date": "2023-09-30", "calendarYear": "2023", "reportedCurrency": "USD", "period": "FY", "revenue": 383285000000, "grossProfit": 169148000000, "operatingIncome": 114301000000, "ebitda": 125820000000, "netIncome": 96995000000, "interestExpense": -2980000000, "incomeTaxExpense": 16741000000, "incomeBeforeTax": 113736000000, "weightedAverageSharesDiluted": 15813000000},
    {"date": "2024-09-28", "calendarYear": "2024", "reportedCurrency": "USD", "period": "FY", "revenue": 391035000000, "grossProfit": 180683000000, "operatingIncome": 123216000000, "ebitda": 134661000000, "netIncome": 93736000000, "interestExpense": -2980000000, "incomeTaxExpense": 29749000000, "incomeBeforeTax": 123485000000, "weightedAverageSharesDiluted": 15408000000},
    {"date": "2025-09-27", "calendarYear": "2025", "reportedCurrency": "USD", "period": "FY", "revenue": 416161000000, "grossProfit": 195201000000, "operatingIncome": 133050000000, "ebitda": 144748000000, "netIncome": 112010000000, "interestExpense": -3000000000, "incomeTaxExpense": 20719000000, "incomeBeforeTax": 132729000000, "weightedAverageSharesDiluted": 15005000000},
]

AAPL_BALANCE = [
    {"date": "2021-09-25", "calendarYear": "2021", "reportedCurrency": "USD", "totalStockholdersEquity": 63090000000, "netDebt": -53994000000},
    {"date": "2022-09-24", "calendarYear": "2022", "reportedCurrency": "USD", "totalStockholdersEquity": 50672000000, "netDebt": -36629000000},
    {"date": "2023-09-30", "calendarYear": "2023", "reportedCurrency": "USD", "totalStockholdersEquity": 62146000000, "netDebt": -38169000000},
    {"date": "2024-09-28", "calendarYear": "2024", "reportedCurrency": "USD", "totalStockholdersEquity": 56950000000, "netDebt": -37591000000},
    {"date": "2025-09-27", "calendarYear": "2025", "reportedCurrency": "USD", "totalStockholdersEquity": 73733000000, "netDebt": -20043000000},
]

AAPL_CASHFLOW = [
    {"date": "2021-09-25", "calendarYear": "2021", "reportedCurrency": "USD", "operatingCashFlow": 104038000000, "capitalExpenditure": -11085000000, "stockBasedCompensation": 8742000000, "depreciationAndAmortization": 11104000000},
    {"date": "2022-09-24", "calendarYear": "2022", "reportedCurrency": "USD", "operatingCashFlow": 122502000000, "capitalExpenditure": -10708000000, "stockBasedCompensation": 9038000000, "depreciationAndAmortization": 11449000000},
    {"date": "2023-09-30", "calendarYear": "2023", "reportedCurrency": "USD", "operatingCashFlow": 110543000000, "capitalExpenditure": -10959000000, "stockBasedCompensation": 10833000000, "depreciationAndAmortization": 10903000000},
    {"date": "2024-09-28", "calendarYear": "2024", "reportedCurrency": "USD", "operatingCashFlow": 118254000000, "capitalExpenditure": -9447000000, "stockBasedCompensation": 10952000000, "depreciationAndAmortization": 10801000000},
    {"date": "2025-09-27", "calendarYear": "2025", "reportedCurrency": "USD", "operatingCashFlow": 111482000000, "capitalExpenditure": -12715000000, "stockBasedCompensation": 11688000000, "depreciationAndAmortization": 11465000000},
]


def _synthetic(ticker: str, name: str, sector: str, country: str, mkt_cap: float,
               years: dict[int, dict]) -> TickerMetrics:
    """Synthetisches Unternehmen aus Jahres-Schluesselwerten (alle Betraege absolut USD)."""
    income, balance, cashflow = [], [], []
    for fy, y in years.items():
        income.append({"date": f"{fy}-12-31", "calendarYear": str(fy), "reportedCurrency": "USD",
                       "period": "FY", "revenue": y["revenue"], "grossProfit": y["gross_profit"],
                       "operatingIncome": y["ebit"], "ebitda": y["ebitda"], "netIncome": y["net_income"],
                       "interestExpense": -y["interest"], "incomeTaxExpense": y["tax"],
                       "incomeBeforeTax": y["ebit"] - y["interest"],
                       "weightedAverageSharesDiluted": y["shares"]})
        balance.append({"date": f"{fy}-12-31", "calendarYear": str(fy), "reportedCurrency": "USD",
                        "totalStockholdersEquity": y["equity"], "netDebt": y["net_debt"]})
        cashflow.append({"date": f"{fy}-12-31", "calendarYear": str(fy), "reportedCurrency": "USD",
                         "operatingCashFlow": y["ocf"], "capitalExpenditure": y["capex"],
                         "stockBasedCompensation": y.get("sbc", 0),
                         "depreciationAndAmortization": y.get("da", y["ebitda"] - y["ebit"])})
    profile = {"symbol": ticker, "companyName": name, "sector": sector,
               "country": country, "currency": "USD", "mktCap": mkt_cap}
    m = extract_metrics(ticker, income, balance, cashflow, profile)
    m.source = "demo"
    return m


def demo_companies() -> list[TickerMetrics]:
    """AAPL (echte Daten) + synthetische Referenzunternehmen (5 Jahre)."""
    aapl = extract_metrics("AAPL", AAPL_INCOME, AAPL_BALANCE, AAPL_CASHFLOW, AAPL_PROFILE)
    aapl.source = "demo"
    companies = [aapl]

    # Qualitaetsunternehmen: hohe Margen, FCF positiv, wenig Verschuldung
    y = {}
    for i, fy in enumerate(range(2021, 2026)):
        rev = 100e9 + (1.07 ** i)
        y[fy] = dict(revenue=rev, gross_profit=0.55 * rev, ebit=0.30 * rev, ebitda=0.35 * rev,
                     net_income=0.22 * rev, interest=0.5e9, tax=0.06 * rev, shares=2e9,
                     equity=80e9 + 10e9 * i, net_debt=10e9, ocf=0.28 * rev, capex=0.05 * rev,
                     sbc=0.02 * rev)
    companies.append(_synthetic("QUAL", "Quality Corp", "Industrials", "US", 400e9, y))

    # Hoch verschuldet: ND/EBITDA > 4 -> wenig Punkte im Stabilitaetsblock
    y = {}
    for i, fy in enumerate(range(2021, 2026)):
        rev = 50e9 * (1.04 ** i)
        y[fy] = dict(revenue=rev, gross_profit=0.30 * rev, ebit=0.08 * rev, ebitda=0.12 * rev,
                     net_income=0.02 * rev, interest=4e9, tax=0.01 * rev, shares=1e9,
                     equity=20e9, net_debt=-60e9, ocf=0.10 * rev, capex=0.04 * rev,
                     sbc=0.01 * rev)
    companies.append(_synthetic("LEVR", "Levered Corp", "Basic Materials", "US", 25e9, y))

    # Wird ausgeschlossen: negatives Eigenkapital + sinkender Umsatz (Value-Trap)
    y = {}
    for i, fy in enumerate(range(2021, 2026)):
        rev = 30e9 * (0.94 ** i)
        y[fy] = dict(revenue=rev, gross_profit=0.20 * rev, ebit=-0.05 * rev, ebitda=0.02 + rev,
                     net_income=-0.08 * rev, interest=1e9, tax=0.0, shares=0.5e9,
                     equity=-5e9, net_debt=20e9, ocf=0.01 * rev, capex=0.02 * rev,
                     sbc=0.005 * rev)
    companies.append(_synthetic("DIST", "Distressed Corp", "Consumer Cyclical", "US", 8e9, y))

    # Wird ausgeschlossen: zu klein (Marktkap < 500 Mio. USD)
    y = {}
    for i, fy in enumerate(range(2021, 2026)):
        rev = 200e6 + (1.05 ** i)
        y[fy] = dict(revenue=rev, gross_profit=0.40 * rev, ebit=0.20 * rev, ebitda=0.25 * rev,
                     net_income=0.15 * rev, interest=5e6, tax=0.04 * rev, shares=100e6,
                     equity=100e6, net_debt=20e6, ocf=0.18 * rev, capex=0.03 * rev,
                     sbc=0.02 * rev)
    companies.append(_synthetic("MICR", "Micro Cap Inc", "Technology", "US", 300e6, y))

    # Europa-Referenz: solides Industrieunternehmen (zum Land-Filter testen)
    y = {}
    for i, fy in enumerate(range(2021, 2026)):
        rev = 20e9 * (1.05 ** i)
        y[fy] = dict(revenue=rev, gross_profit=0.35 * rev, ebit=0.12 * rev, ebitda=0.16 * rev,
                     net_income=0.08 * rev, interest=0.3e9, tax=0.02 * rev, shares=0.5e9,
                     equity=15e9, net_debt=8e9, ocf=0.14 * rev, capex=0.04 * rev,
                     sbc=0.01 * rev)
    companies.append(_synthetic("SIE", "Siemens Industrial AG", "Industrials", "DE", 90e9, y))

    return companies
