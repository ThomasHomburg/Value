"""DCF-Modul: innerer Wert je Aktie mit 3 Szenarien (Bear / Base / Bull).

Nach CLAUDE.md (Build-Schritt 6), aber mit normalisiertem FCF nach SBC
(Durchschnitt der letzten 3 Jahre mit verfuegbaren Daten):

- Basis: normalisierter FCF = Ø FCF-SBC der letzten 3 Jahre (fcf_sbc je Jahr).
- Wachstum Jahre 1-5: Bear 0 %, Base = min(Umsatz-CAGR ueber verfuegbare
  Jahre, base_growth_cap), Bull = min(CAGR x bull_growth_multiplier,
  bull_growth_cap).
- Wachstum Jahre 6-10: linear abnehmend von der Jahr-5-Rate auf
  terminal_growth (fade_to_growth).
- Terminal Value = FCF_10 x (1 + g) / (r - g); Diskontsatz r aus Config
  (discount_rate bzw. discount_rate_cyclicals).
- Innerer Wert = Barwert der FCFs (Jahre 1-10) + Barwert Terminal Value.
- Innerer Wert je Aktie = Innerer Wert / verwässerte Aktien (neuestes FY).
- Margin of Safety (Base) = 1 - Kurs / innerer Wert je Aktie (Base).

Alle Parameter kommen aus config.yaml (Block `dcf`), keine Magic Numbers.
Fehlende Daten -> NaN, nie 0 (CLAUDE.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from data.loader import TickerMetrics


@dataclass
class DcfScenario:
    name: str                      # "bear" | "base" | "bull"
    growth_rates: list[float]      # 10 Wachstumsraten (Jahre 1-10)
    fcfs: list[float]              # projizierte FCFs (Jahre 1-10), Berichtswährung
    pv_fcfs: float                 # Barwert der 10 FCFs
    terminal_value: float          # Barwert des Terminal Value (abgezinst)
    enterprise_value: float        # pv_fcfs + terminal_value
    value_per_share: float         # EV / Aktien (NaN wenn keine Aktienanzahl)


@dataclass
class DcfResult:
    fcf_normalized: float          # Ø FCF-SBC letzte 3 Jahre (absolut, Berichtswährung)
    fcf_years_used: int            # Anzahl verwendeter Jahre
    revenue_cagr: float            # Umsatz-CAGR ueber verfuegbare Jahre (Basis-Wachstum)
    discount_rate: float
    terminal_growth: float
    shares: float                  # verwässerte Aktien, neuestes FY
    scenarios: dict[str, DcfScenario] = field(default_factory=dict)
    margin_of_safety: float = float("nan")   # MoS Base = 1 - Kurs / Wert je Aktie (Base)
    is_buy: bool = False           # Kaufkandidat (Score/MoS/Bear-Regeln, siehe pipeline)
    fcf_normalized_conv: float = float("nan")  # normalisierter FCF in Marktkap.-Waehrung
    fcf_basis: str = "annual"   # "ttm" (Ø TTM + 2 nicht ueberlappende GJ) oder "annual" (Rueckfall)
    ttm_quarter_end: str = ""   # Stichtag letztes Quartal (ISO), nur bei fcf_basis="ttm"
    fcf_sources: list = field(default_factory=list)  # verwendete FCF-SBC-Werte [TTM, FY-1, FY-2]


def _cagr(values: list[float]) -> float:
    """Jaehrliche Wachstumsrate ueber n-1 Jahre (chronologisch)."""
    if len(values) < 2 or values[0] <= 0:
        return float("nan")
    n = len(values) - 1
    return (values[-1] / values[0]) ** (1 / n) - 1


def _growth_path(g5: float, g_terminal: float, cfg: dict) -> list[float]:
    """10 Wachstumsraten: Jahre 1-5 konstant g5, Jahre 6-10 linear auf g_terminal."""
    fade = float(cfg.get("fade_to_growth", g_terminal))
    rates = [g5] * 5
    for i in range(1, 6):  # Jahre 6-10: linear von g5 auf fade
        t = i / 5.0
        rates.append(g5 + (fade - g5) * t)
    return rates


def _pv(fcf: float, rate: float, year: int) -> float:
    return fcf / (1.0 + rate) ** year


def compute_dcf(m: TickerMetrics, cfg: dict, fx=None) -> DcfResult:
    """Berechnet den DCF fuer einen Ticker nach Config-Block `cfg['dcf']`.

    fx: optionaler FX-Converter (wie in data/metrics.py) — der normalisierte
    FCF wird in die Marktkap.-Währung konvertiert, damit Kurs und Wert
    konsistent sind.
    """
    dcfg = cfg["dcf"]
    nan = float("nan")
    result = DcfResult(
        fcf_normalized=nan, fcf_years_used=0, revenue_cagr=nan,
        discount_rate=float(dcfg.get("discount_rate", 0.09)),
        terminal_growth=float(dcfg.get("terminal_growth", 0.025)),
        shares=nan,
    )

    # --- normalisierter FCF nach SBC ----------------------------------------
    # TTM-Basis (falls Quartalsdaten plausibel): Ø aus TTM (letzte 4 Quartale)
    # und den zwei davor liegenden, NICHT ueberlappenden Geschaeftsjahren.
    # Nicht ueberlappend: das Geschaeftsjahr muss vor dem ersten Quartal des
    # TTM-Fensters enden (exaktes FY-Enddatum vs. erstes TTM-Quartal).
    # Rueckfall: Ø der letzten 3 Geschaeftsjahre (bisheriges Verhalten).
    ttm = getattr(m, "ttm", None)
    ttm_fcf = None
    use_ttm = (ttm is not None and getattr(m, "ttm_plausible", True)
               and not getattr(m, "ttm_fallback", False))
    if use_ttm:
        ttm_fcf = ttm.ttm.get("fcf_sbc")
        ttm_end = ttm.quarter_end  # ISO-Stichtag letztes Quartal
        # erstes Quartal des TTM-Fensters = ttm_end - 9 Monate (naeherung)
        from datetime import date as _date
        y, mo, d = (int(x) for x in ttm_end.split("-"))
        first_q_month = ((mo - 10) % 12) + 1   # 9 Monate vor Endmonat
        first_q_year = y - (1 if mo <= 9 else 0)
        window_start = _date(first_q_year, first_q_month, 1)
        # Geschaeftsjahre, deren Enddatum STRICT vor dem TTM-Fenster liegt
        prior_fys = []
        for fy in sorted(m.years, reverse=True):
            fe = m.fiscal_ends.get(fy)
            if not fe:
                continue
            fy_end = _date.fromisoformat(fe)
            if fy_end < window_start:
                prior_fys.append(fy)
        fy_vals = []
        for fy in prior_fys[:2]:
            met = m.years[fy].get("fcf_sbc")
            if met is not None and not met.is_na():
                fy_vals.append((fy, met.value, met.currency))
        if (ttm_fcf is not None and not ttm_fcf.is_na() and len(fy_vals) >= 2):
            vals = [ttm_fcf.value] + [v for _, v, _ in fy_vals]
            fcf_norm = sum(vals) / len(vals)
            result.fcf_normalized = fcf_norm
            result.fcf_years_used = len(vals)
            result.fcf_basis = "ttm"
            result.ttm_quarter_end = ttm_end
            result.fcf_sources = ([("TTM", ttm_fcf.value, ttm_fcf.currency)]
                                  + [(f"FY{fy}", v, c) for fy, v, c in fy_vals])
        else:
            use_ttm = False  # nicht genug nicht-ueberlappende GJ -> Rueckfall
    if not use_ttm:
        sbc_series = [m.years[fy]["fcf_sbc"] for fy in sorted(m.years)
                      if "fcf_sbc" in m.years[fy] and not m.years[fy]["fcf_sbc"].is_na()]
        if not sbc_series:
            return result
        last3 = sbc_series[-3:]
        fcf_norm = sum(x.value for x in last3) / len(last3)
        result.fcf_normalized = fcf_norm
        result.fcf_years_used = len(last3)
        result.fcf_basis = "annual"
        fys = sorted(m.years)[-len(last3):]
        result.fcf_sources = [(f"FY{fy}", x.value, x.currency)
                              for fy, x in zip(fys, last3)]

    # --- Umsatz-CAGR ueber verfuegbare Jahre (Basis-Wachstum) ---------------
    rev_series = [m.years[fy]["revenue"] for fy in sorted(m.years)
                  if "revenue" in m.years[fy] and not m.years[fy]["revenue"].is_na()]
    rev_vals = [x.value for x in rev_series if x.value > 0]
    cagr = _cagr(rev_vals) if len(rev_vals) >= 2 else nan
    result.revenue_cagr = cagr

    # --- Aktienanzahl (verwässert, neuestes FY) -----------------------------
    for fy in sorted(m.years, reverse=True):
        sh = m.years[fy].get("shares_diluted")
        if sh is not None and not sh.is_na() and sh.value > 0:
            result.shares = sh.value
            break

    # --- Szenario-Wachstumsraten ---------------------------------------------
    base_cap = float(dcfg.get("base_growth_cap", 0.06))
    bull_mult = float(dcfg.get("bull_growth_multiplier", 1.3))
    bull_cap = float(dcfg.get("bull_growth_cap", 0.10))
    g_terminal = result.terminal_growth
    if cagr != cagr:  # NaN -> kein Wachstum bestimmbar
        g_bear, g_base, g_bull = 0.0, 0.0, 0.0
    else:
        g_bear = 0.0
        g_base = min(cagr, base_cap)
        g_bull = min(cagr * bull_mult, bull_cap)

    # --- FX: FCF in Marktkap.-Waehrung konvertieren (Kurs und Wert konsistent)
    mcap = m.market_cap
    if mcap is None or mcap.is_na() or mcap.value <= 0:
        return result
    converter = fx
    if converter is None:
        from data.metrics import _NoFX
        converter = _NoFX()
    latest_fy = max(m.years)
    # Waehrung der FCF-Quelle: TTM-Metric bzw. letztes verwendetes Jahr
    if result.fcf_basis == "ttm" and ttm_fcf is not None:
        fcf_cur = ttm_fcf.currency
    else:
        fcf_cur = sbc_series[-1].currency
    fcf_conv = converter.convert(fcf_norm, fcf_cur, mcap.currency, latest_fy)
    if math.isnan(fcf_conv):
        return result
    result.fcf_normalized_conv = fcf_conv

    for name, g5 in (("bear", g_bear), ("base", g_base), ("bull", g_bull)):
        rates = _growth_path(g5, g_terminal, dcfg)
        fcfs, fcf_t = [], fcf_conv
        for g in rates:
            fcf_t = fcf_t * (1.0 + g)
            fcfs.append(fcf_t)
        r = result.discount_rate
        pv_fcfs = sum(_pv(f, r, i + 1) for i, f in enumerate(fcfs))
        tv = fcfs[-1] * (1.0 + g_terminal) / (r - g_terminal) if r > g_terminal else nan
        tv_pv = _pv(tv, r, 10) if tv == tv else nan
        ev = pv_fcfs + tv_pv if tv_pv == tv_pv else nan
        vps = ev / result.shares if (ev == ev and result.shares == result.shares) else nan
        result.scenarios[name] = DcfScenario(
            name=name, growth_rates=rates, fcfs=fcfs, pv_fcfs=pv_fcfs,
            terminal_value=tv_pv, enterprise_value=ev, value_per_share=vps,
        )

    # --- Margin of Safety (Base) ----------------------------------------------
    base = result.scenarios.get("base")
    if base is not None and base.value_per_share == base.value_per_share and base.value_per_share > 0:
        price = mcap.value / result.shares if result.shares == result.shares else nan
        if price == price and price > 0:
            result.margin_of_safety = 1.0 - price / base.value_per_share
    return result


def sensitivity_mos_base(m: TickerMetrics, cfg: dict, fx=None,
                         discount_rates=(0.08, 0.09, 0.10, 0.11),
                         terminal_growths=(0.02, 0.025, 0.03)) -> list[dict]:
    """Sensitivitaet: MoS (Base) je Aktie fuer Diskontsatz x Terminal Growth.

    Pro Kombination (r, g) wird der Base-Szenario-Pfad (Wachstum aus der
    CAGR, wie in compute_dcf) mit dem jeweiligen r/g neu diskontiert.
    Rueckgabe: [{discount_rate, terminal_growth, value_per_share, mos}].
    """
    dcfg = cfg["dcf"]
    nan = float("nan")
    base_res = compute_dcf(m, cfg, fx=fx)
    if base_res.fcf_normalized != base_res.fcf_normalized:
        return []
    mcap = m.market_cap
    if mcap is None or mcap.is_na() or mcap.value <= 0:
        return []
    if base_res.shares != base_res.shares or base_res.shares <= 0:
        return []

    # FCF in Marktkap.-Waehrung (wie in compute_dcf: TTM-Waehrung falls TTM-Basis)
    converter = fx
    if converter is None:
        from data.metrics import _NoFX
        converter = _NoFX()
    latest_fy = max(m.years)
    if base_res.fcf_basis == "ttm" and base_res.fcf_sources:
        fcf_cur = base_res.fcf_sources[0][2]
    else:
        sbc_series = [m.years[fy]["fcf_sbc"] for fy in sorted(m.years)
                      if "fcf_sbc" in m.years[fy] and not m.years[fy]["fcf_sbc"].is_na()]
        fcf_cur = sbc_series[-1].currency
    fcf_conv = converter.convert(base_res.fcf_normalized, fcf_cur,
                                 mcap.currency, latest_fy)
    if math.isnan(fcf_conv):
        return []

    price = mcap.value / base_res.shares
    cagr = base_res.revenue_cagr
    base_cap = float(dcfg.get("base_growth_cap", 0.06))
    g5 = 0.0 if cagr != cagr else min(cagr, base_cap)
    rates = _growth_path(g5, float(dcfg.get("fade_to_growth", 0.025)), dcfg)
    fcfs, fcf_t = [], fcf_conv
    for g in rates:
        fcf_t = fcf_t * (1.0 + g)
        fcfs.append(fcf_t)

    out = []
    for r in discount_rates:
        for g in terminal_growths:
            if r <= g:
                out.append({"discount_rate": r, "terminal_growth": g,
                            "value_per_share": nan, "mos": nan})
                continue
            pv_fcfs = sum(_pv(f, r, i + 1) for i, f in enumerate(fcfs))
            tv = fcfs[-1] * (1.0 + g) / (r - g)
            ev = pv_fcfs + _pv(tv, r, 10)
            vps = ev / base_res.shares
            mos = 1.0 - price / vps if vps > 0 else nan
            out.append({"discount_rate": r, "terminal_growth": g,
                        "value_per_share": vps, "mos": mos})
    return out


def is_buy_candidate(score: float, dcf: DcfResult, current_price: float, cfg: dict) -> bool:
    """Kaufkandidat (CLAUDE.md): Score >= buy_score_min UND MoS (Base) >=
    buy_margin_of_safety_min UND Bear-Szenario >= Kurs x buy_bear_floor."""
    dcfg = cfg["dcf"]
    if score != score or dcf.margin_of_safety != dcf.margin_of_safety:
        return False
    if current_price != current_price or current_price <= 0:
        return False
    if score < float(dcfg.get("buy_score_min", 70)):
        return False
    if dcf.margin_of_safety < float(dcfg.get("buy_margin_of_safety_min", 0.30)):
        return False
    bear = dcf.scenarios.get("bear")
    if bear is None or bear.value_per_share != bear.value_per_share:
        return False
    floor = float(dcfg.get("buy_bear_floor", 0.80))
    return bear.value_per_share >= floor * current_price
