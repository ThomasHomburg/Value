"""Abgeleitete Kennzahlen mit dokumentierten Formeln.

Formeln (Kapitalbasis jeweils Ende des Geschaeftsjahres):
- NOPAT = EBIT * (1 - Steuersatz); Steuersatz = Steueraufwand / Vorsteuergewinn.
- Investiertes Kapital = Eigenkapital + Nettoverschuldung.
- ROIC = NOPAT / investiertes Kapital.
- FCF-Yield = FCF / Marktkapitalisierung.
- ROE = Nettogewinn / Eigenkapital (Banken-Ersatzkennzahl).

Fehlende Eingangsdaten -> NaN, nie 0 (CLAUDE.md).
"""

from __future__ import annotations

import math

from .loader import TickerMetrics


class _NoFX:
    """Fallback-Konverter ohne FX: Konvertierung nur bei gleicher Waehrung."""

    def convert(self, value: float, from_cur: str, to_cur: str, year: int) -> float:
        if from_cur.upper() == to_cur.upper():
            return value
        return float("nan")


def _nan(*vals: float) -> bool:
    return any(math.isnan(v) for v in vals)


def tax_rate(m: TickerMetrics, fy: int) -> float:
    """Effektiver Steuersatz = Steueraufwand / Vorsteuergewinn."""
    y = m.years.get(fy, {})
    tax = y.get("income_tax_expense")
    pretax = y.get("income_before_tax")
    if tax is None or pretax is None:
        return float("nan")
    t, p = tax.value, pretax.value
    if _nan(t, p) or p == 0:
        return float("nan")
    return t / p


def nopat(m: TickerMetrics, fy: int) -> float:
    """NOPAT = EBIT * (1 - Steuersatz)."""
    ebit = m.years.get(fy, {}).get("ebit")
    if ebit is None:
        return float("nan")
    t = tax_rate(m, fy)
    if _nan(ebit.value, t):
        return float("nan")
    return ebit.value * (1 - t)


def invested_capital(m: TickerMetrics, fy: int) -> float:
    """Investiertes Kapital = Eigenkapital + Nettoverschuldung (Jahresende)."""
    eq = m.years.get(fy, {}).get("equity")
    nd = m.years.get(fy, {}).get("net_debt")
    if eq is None or nd is None or _nan(eq.value, nd.value):
        return float("nan")
    return eq.value + nd.value


def roic(m: TickerMetrics, fy: int) -> float:
    """ROIC = NOPAT / investiertes Kapital (Jahresende)."""
    ic = invested_capital(m, fy)
    np_ = nopat(m, fy)
    if _nan(ic, np_) or ic == 0:
        return float("nan")
    return np_ / ic


def fcf_yield(m: TickerMetrics, fy: int, fx=None) -> float:
    """FCF-Yield = FCF / Marktkapitalisierung (Marktkap. zum FX-End).

    Waehrungskonsistent: FMP liefert /profile (mktCap) in USD, Statements
    in reportedCurrency. Bei Mismatch wird der FCF zum historyischen
    Jahresendkurs in die Marktkap.-Waehrung konvertiert. Ohne fx-Converter
    oder ohne Kurs -> NaN.

    Fuer die Anzeige gibt es fcf_yield_raw (zusatzliche Spalte, unkonvertiert).
    """
    fcf = m.years.get(fy, {}).get("fcf")
    if fcf is None or m.market_cap is None or _nan(fcf.value, m.market_cap.value):
        return float("nan")
    if m.market_cap.value == 0:
        return float("nan")
    converter = fx or _NoFX()
    fcf_conv = converter.convert(fcf.value, fcf.currency, m.market_cap.currency, fy)
    if _nan(fcf_conv):
        return float("nan")
    return fcf_conv / m.market_cap.value


def fcf_yield_sbc(m: TickerMetrics, fy: int, fx=None) -> float:
    """FCF-Yield nach SBC = (FCF - Aktienverguetung) / Marktkapitalisierung.

    Wie fcf_yield(), aber auf fcf_sbc (FCF abzuiglich SBC aus dem
    Cashflow-Statement). Fehlende SBC oder fehlender FCF -> NaN, nie 0.
    """
    fcf = m.years.get(fy, {}).get("fcf_sbc")
    if fcf is None or m.market_cap is None or _nan(fcf.value, m.market_cap.value):
        return float("nan")
    if m.market_cap.value == 0:
        return float("nan")
    converter = fx or _NoFX()
    fcf_conv = converter.convert(fcf.value, fcf.currency, m.market_cap.currency, fy)
    if _nan(fcf_conv):
        return float("nan")
    return fcf_conv / m.market_cap.value


def fcf_yield_raw(m: TickerMetrics, fy: int) -> float:
    """FCF-Yield ohne Waehrung, nur fuer Anzeige als zusaetzliche Spalte,
    nicht fuer Scoring verwenden.
    """
    fcf = m.years.get(fy, {}).get("fcf")
    if fcf is None or m.market_cap is None or _nan(fcf.value, m.market_cap.value):
        return float("nan")
    if m.market_cap.value <= 0:
        return float("nan")
    return fcf.value / m.market_cap.value


def roe(m: TickerMetrics, fy: int) -> float:
    """ROE = Nettogewinn / Eigenkapital (Banken-Ersatz fuer ROIC)."""
    ni = m.years.get(fy, {}).get("net_income")
    eq = m.years.get(fy, {}).get("equity")
    if ni is None or eq is None or _nan(ni.value, eq.value) or eq.value == 0:
        return float("nan")
    return ni.value / eq.value
