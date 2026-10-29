"""Value-Screener UI (Streamlit).

Start lokal:  streamlit run app.py
Oeffnet http://localhost:8501 im Browser.

Seite 1 Rangliste : sortierbare Tabelle, Filter Sektor/Land/Score (CLAUDE.md).
Seite 2 Scorecard: Block-Scores als Balken, Jahres-Charts, Rohdaten mit Quelle.
Seite 3 Import   : CSV-Upload (Tickerliste) und manuelle Ticker-Eingabe.

Live-Modus ueber Provider-Schnittstelle (FMP fuer US-Ticker mit API-Key,
yfinance fuer alle anderen -- yfinance braucht keinen Key). Demo-Daten
(data/demo.py) nur als Fallback, wenn kein Live-Ticker geladen werden kann.
"""

from __future__ import annotations

import logging
import math
import os

import pandas as pd
import streamlit as st

import altair as alt

from config import load_config
from data.demo import demo_companies
from data.loader import TickerMetrics, country_code
from data.metrics import fcf_yield, fcf_yield_sbc, invested_capital, nopat, roic, roe, tax_rate
from data.providers.base import ProviderError, build_providers, load_with_provider
from data.tickerlist import load_ticker_file, parse_ticker_csv, parse_ticker_text
from scoring.criteria import compute_criteria
from scoring.pipeline import evaluate_all, evaluate_ticker, rank_rows

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("value_screener.app")

CFG = load_config()


# --- Daten laden (gecacht) ---------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def load_demo() -> list[TickerMetrics]:
    return demo_companies()


@st.cache_data(ttl=3600, show_spinner=False)
def load_live(tickers: tuple[str, ...], years: int) -> list[TickerMetrics]:
    providers = build_providers(os.environ.get("FMP_API_KEY", ""))
    out = []
    for ticker in tickers:
        try:
            out.append(load_with_provider(ticker, CFG, providers, years=years))
        except ProviderError as exc:
            logger.error("Provider-Fehler bei %s: %s", ticker, exc)
            st.warning(f"Provider-Fehler bei {ticker}: {exc}")
    return out


def get_companies() -> tuple[list[TickerMetrics], str, str]:
    """(companies, source_label, source_kind). Session-State (Seite 3 Import)
    hat Vorrang; sonst Live ueber Provider-Schnittstelle (FMP/yfinance).
    Demo-Daten nur als Fallback, wenn kein Live-Ticker geladen werden kann.
    Default-Ticker: tickers.csv (20 Stueck voreingestellt).
    """
    if "imported_companies" in st.session_state:
        return st.session_state["imported_companies"], "Import (Seite 3)", "import"
    tickers = tuple(st.session_state.get("live_tickers") or load_ticker_file("tickers.csv") or ["AAPL"])
    api_key = os.environ.get("FMP_API_KEY", "")
    sources = sorted(build_providers(api_key))
    label = f"LIVE ({len(tickers)} Ticker, Provider: {', '.join(sources)})"
    if len(tickers) <= 5:
        label += "  " + ", ".join(tickers)
    companies = load_live(tickers, CFG["data"]["years"])
    if not companies:
        return load_demo(), "DEMO-DATEN (Fallback: Live-Laden fehlgeschlagen)", "demo"
    return companies, label, "live"


def _fmt_pct(v: float) -> str:
    # Anzeige auf 1 Nachkommastelle; Berechnung bleibt ungerundet
    return "n/a" if (v != v) else f"{v:.1%}"


# --- Seite 1: Rangliste ------------------------------------------------------

def page_ranking() -> None:
    rows = st.session_state["rows"]
    excluded = st.session_state["excluded"]
    source = st.session_state["source"]
    kind = st.session_state["source_kind"]
    st.header("Rangliste")
    # Banner: eine Zeile (Quelle + Ticker-Anzahl), nicht doppelt
    total_tickers = len(rows) + len(excluded)
    if kind == "live":
        st.success(f"LIVE · yfinance · {total_tickers} Ticker")
    elif kind == "import":
        st.info(f"{source} · {total_tickers} Ticker")
    else:
        st.warning(f"{source} · {total_tickers} Ticker")
        st.caption("Tipp: `tickers.csv` im Projektordner legt die Live-Ticker fest (20 Stueck voreingestellt). "
                   "US-Ticker -> FMP (mit FMP_API_KEY), alle anderen -> yfinance.")

    with st.expander("Ausgeschlossene Ticker (harte Filter)", expanded=False):
        if excluded:
            for e in excluded:
                st.write(f"**{e['ticker']}** ({e['name']}): " + "; ".join(e["reasons"]))
        else:
            st.write("Keine Ausschluesse.")

    if not rows:
        st.info("Keine Ticker nach den Filtern uebrig.")
        return

    df = pd.DataFrame(rows)
    sectors = sorted(df["sector"].unique())
    countries = sorted(df["country"].unique())

    col1, col2, col3 = st.columns(3)
    with col1:
        # Default: alle (leer = alle anzeigen)
        sel_sectors = st.multiselect("Sektor", sectors, default=[])
    with col2:
        sel_countries = st.multiselect("Land", countries, default=[])
    with col3:
        min_score = st.slider("Min. Score", 0, 100, 0)

    mask = (
        df["sector"].isin(sel_sectors if sel_sectors else sectors)
        & df["country"].isin(sel_countries if sel_countries else countries)
        & (df["score"].fillna(-1) >= min_score)
    )
    view = df[mask].copy()
    # Land als Kuerzel (US, DE); Scores/Prozente auf 1 Nachkommastelle (Anzeige)
    view["Land"] = view["country"].map(country_code)
    view["FCF-Yield"] = view["fcf_yield"].map(_fmt_pct)
    view["FCF-Yield nach SBC"] = view["fcf_yield_sbc"].map(_fmt_pct)
    view["FCF-Yield nach SBC Ø3J"] = view["fcf_yield_3y"].map(_fmt_pct)
    view["ROIC Ø"] = view["roic_5y"].map(_fmt_pct)
    view["ROIC letztes GJ"] = view["roic_latest"].map(_fmt_pct)
    q_rank = rank_rows(rows, "quality")
    view["Quality-Rang"] = view["ticker"].map(lambda t: "n/a" if q_rank.get(t) is None else str(q_rank[t]))
    view["ND/EBITDA"] = view["nd_ebitda"].map(lambda v: "n/a" if math.isnan(v) else f"{v:.2f}")
    view["EV/EBIT rel."] = view["ev_ebit_med"].map(lambda v: "n/a" if math.isnan(v) else f"{v:.1f}")
    view["MoS (Base)"] = view["margin_of_safety"].map(_fmt_pct)   # DCF, Build-Schritt 6
    view["MoS Bear"] = view["mos_bear"].map(_fmt_pct)
    view["MoS Bull"] = view["mos_bull"].map(_fmt_pct)
    view["Kandidat"] = view["kandidat"].map(lambda v: str(v))
    view["Datenabdeckung"] = view["coverage"].map(lambda v: "n/a" if (v != v) else f"{v:.1%}")
    view = view.rename(columns={"ticker": "Ticker", "name": "Name", "sector": "Sektor",
                                "source": "Quelle", "score": "Score",
                                "quality": "Quality", "value": "Value", "flags": "Flags"})
    show_cols = ["Ticker", "Name", "Sektor", "Land", "Quelle", "Score", "Quality", "Quality-Rang", "Value",
                 "Datenabdeckung", "FCF-Yield", "FCF-Yield nach SBC", "FCF-Yield nach SBC Ø3J",
                 "ROIC Ø", "ROIC letztes GJ", "ND/EBITDA", "EV/EBIT rel.", "MoS (Base)", "MoS Bear", "MoS Bull", "Kandidat", "Flags"]
    # Standard-Sortierung: Kaufkandidat zuerst, dann MoS (Base) absteigend
    view["_kauf"] = (view["Kandidat"] == "ja").astype(int)
    view["_mos"] = pd.to_numeric(view["MoS (Base)"].str.replace("n/a", "").str.rstrip("%"), errors="coerce")
    view = view.sort_values(["_kauf", "_mos"], ascending=[False, False])
    view = view[show_cols]
    st.caption(f"{len(view)} bewertet, {len(excluded)} ausgeschlossen "
               f"({total_tickers} Ticker gesamt, {len(view)} nach Filter)")
    # Durch Sektor-/Land-Filter ausgeblendete Ticker anzeigen
    hidden = df[~mask]
    hidden_tickers = sorted(hidden["ticker"].tolist())
    if hidden_tickers:
        st.caption("Durch Filter ausgeblendet: " + ", ".join(hidden_tickers))
    buys = sorted(df[df["is_buy"]]["ticker"].tolist()) if "is_buy" in df.columns else []
    if buys:
        st.success("Kaufkandidaten: " + ", ".join(buys))
    # Zeileninhalt umbrechen (lange Namen/Flags), Name-Spalte breiter
    styler = view.style.set_table_styles([
        {"selector": "th", "props": [("white-space", "nowrap")]},
        {"selector": "td", "props": [("white-space", "normal"), ("word-break", "break-word"),
                                     ("max-width", "260px")]},
        {"selector": "td:nth-child(2)", "props": [("min-width", "200px"), ("max-width", "320px")]},
    ])
    # Tooltips je Spalte (eindeutige Namen + Erklaerung)
    col_cfg = {
        "Ticker": st.column_config.TextColumn("Ticker", help="Börsenticker"),
        "Name": st.column_config.TextColumn("Name", help="Firmenname"),
        "Sektor": st.column_config.TextColumn("Sektor", help="Branche (Sektor)"),
        "Land": st.column_config.TextColumn("Land", help="Land als Kürzel (US, DE, ...)"),
        "Quelle": st.column_config.TextColumn("Quelle", help="Datenquelle (yfinance / fmp / demo)"),
        "Score": st.column_config.NumberColumn("Score", help="Gesamtscore = 0,75×Quality + 0,25×Value (0–100)", format="%.1f"),
        "Quality": st.column_config.NumberColumn("Quality", help="Quality-Score (0–100): Profitabilität, Stabilität, Cashflow, Moat", format="%.1f"),
        "Quality-Rang": st.column_config.TextColumn("Quality-Rang", help="Rang nach Quality-Score im Universum (1 = bester); Gleichstand = gleicher Rang; n/a = Quality nicht berechenbar"),
        "Value": st.column_config.NumberColumn("Value", help="Value-Score (0–100): Bewertungs-Kriterien", format="%.1f"),
        "Datenabdeckung": st.column_config.TextColumn("Datenabdeckung", help="Anteil bewerteter Kriterien-Gewichte (n/a-Kriterien herausgerechnet, übrige renormalisiert)"),
        "FCF-Yield": st.column_config.TextColumn("FCF-Yield", help="FCF / Marktkapitalisierung (aktuelles Geschäftsjahr)"),
        "FCF-Yield nach SBC": st.column_config.TextColumn("FCF-Yield nach SBC", help="(FCF − Aktienverguetung) / Marktkapitalisierung (aktuelles Jahr)"),
        "FCF-Yield nach SBC Ø3J": st.column_config.TextColumn("FCF-Yield nach SBC Ø3J", help="3-Jahres-Durchschnitt des FCF-Yield nach SBC – geht in den Value-Score ein"),
        "ROIC Ø": st.column_config.TextColumn("ROIC Ø", help="Ø (NOPAT / investiertes Kapital) über verfügbare Jahre (aktuell 4; yfinance liefert das 5-Jahres-Fenster gekürzt); > 100 % = Kapitalbasis klein (Flag kl.Kapital)"),
        "ROIC letztes GJ": st.column_config.TextColumn("ROIC letztes GJ", help="ROIC des neuesten Geschäftsjahrs: NOPAT / (Eigenkapital + Nettoverschuldung), Kapitalbasis Jahresende; > 100 % = Kapitalbasis klein"),
        "ND/EBITDA": st.column_config.TextColumn("ND/EBITDA", help="Nettoverschuldung / EBITDA (x, neuestes Jahr)"),
        "EV/EBIT rel.": st.column_config.TextColumn("EV/EBIT rel.", help="EV/EBIT im Vergleich zum Sektor-Median (1,0 = Median)"),
        "MoS (Base)": st.column_config.TextColumn("MoS (Base)", help="Margin of Safety = 1 − Kurs / innerer Wert je Aktie (DCF-Base-Szenario)"),
        "MoS Bear": st.column_config.TextColumn("MoS Bear", help="Margin of Safety = 1 − Kurs / innerer Wert je Aktie (DCF-Bear-Szenario)"),
        "MoS Bull": st.column_config.TextColumn("MoS Bull", help="Margin of Safety = 1 − Kurs / innerer Wert je Aktie (DCF-Bull-Szenario)"),
        "Kandidat": st.column_config.TextColumn("Kandidat", help="Kaufkandidat: ja = alle 3 Bedingungen erfuellt (Quality ≥ 60, MoS Base ≥ 30 %, Bear ≥ 80 % Kurs); nein: mit Begruendung, welche Bedingung fehlt"),
        "Flags": st.column_config.TextColumn("Flags", help="blk:duenn = Block mit >30 % fehlenden Daten · duenn = Kriterium mit < 5 Jahren Daten · kl.Kapital = ROIC > 100 % (kleine/negative Kapitalbasis) · kauf = Kaufkandidat (Quality ≥ 60, MoS Base ≥ 30 %, Bear ≥ 80 % Kurs)"),
    }
    st.dataframe(styler, width="stretch", hide_index=True, column_config=col_cfg)
    st.caption("Klick auf eine Spaltenueberschrift sortiert die Tabelle; Maus über die "
               "Überschrift zeigt den Tooltip. n/a = Daten fehlen (nie mit 0 gefuellt). "
               "Alle Scores und Prozentwerte auf 1 Nachkommastelle angezeigt "
               "(Berechnung ungerundet).")


# --- Seite 2: Scorecard ------------------------------------------------------

def page_scorecard() -> None:
    companies = st.session_state["companies"]
    rows = st.session_state["rows"]
    st.header("Scorecard")
    if not rows:
        st.info("Keine Ticker zum Anzeigen.")
        return
    tickers = [r["ticker"] for r in rows]
    choice = st.selectbox("Unternehmen", tickers, format_func=lambda t: f"{t} – {next((r['name'] for r in rows if r['ticker'] == t))}")
    m = next(c for c in companies if c.ticker == choice)
    res = evaluate_ticker(m, CFG)
    result = res["score"]
    criteria = res["criteria"]

    st.subheader(f"{m.name} ({m.ticker}) – {m.sector}, Land: {m.country or 'n/a'}")
    if getattr(m, "ttm", None) is not None and not getattr(m, "ttm_plausible", True):
        st.warning("[!] Quartalsdaten unplausibel (Abweichung > 2 % zum Jahreswert) "
                   "→ DCF-Basis fällt auf Geschäftsjahre zurück.")
    if m.market_cap is not None and not m.market_cap.is_na():
        st.write(f"Marktkapitalisierung: **{m.market_cap.value / 1e9:,.2f} Mrd. {m.market_cap.currency}**  "
                 f"(Stichtag: {m.market_cap_date or 'n/a'}, Quelle: {m.source or 'unbekannt'}; "
                 f"Einheit: absolute Betraege)")

    total = result["total"]
    # ROIC letztes Geschaeftsjahr (gleiche Formel wie unten: NOPAT / (EK + ND))
    latest_fy0 = max(m.years)
    roic_last = roic(m, latest_fy0)
    roic_last_str = "n/a" if (roic_last != roic_last) else f"{roic_last:.1%}"
    if roic_last == roic_last and roic_last > 1.0:
        roic_last_str += "  Kapitalbasis klein"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gesamtscore", "n/a" if math.isnan(total) else f"{total:.1f} / 100")
    c2.metric("Quality", "n/a" if math.isnan(result["quality"]) else f"{result['quality']:.1f}")
    c3.metric("Value", "n/a" if math.isnan(result["value"]) else f"{result['value']:.1f}")
    c4.metric(f"ROIC letztes GJ ({latest_fy0})", roic_last_str,
              help="ROIC = NOPAT / (Eigenkapital + Nettoverschuldung), Kapitalbasis Jahresende")
    cov = result["coverage"]
    c5.metric("Datenabdeckung", "n/a" if (cov != cov) else f"{cov:.1%}")

    # Block-Scores als Balken: jeder Balken mit deutschem Blocknamen und Wert
    # beschriftet; Bloecke ohne Daten als "n/a" statt als Luecke (Wert 0 mit Label).
    st.subheader("Block-Scores")
    BLOCK_NAMES = {
        "profitability": "Rentabilität",
        "stability": "Stabilität",
        "cashflow": "Cashflow",
        "moat": "Moat",
        "valuation": "Bewertung",
    }
    block_rows = []
    for b in result["blocks"]:
        s = result["blocks"][b]
        label = BLOCK_NAMES.get(b, b)
        if s != s:  # NaN -> n/a statt Luecke
            block_rows.append({"Block": label, "Score": 0.0, "Beschriftung": f"{label}: n/a"})
        else:
            block_rows.append({"Block": label, "Score": s,
                               "Beschriftung": f"{label}: {s:.1f}"})
    block_df = pd.DataFrame(block_rows)
    block_chart = (
        alt.Chart(block_df)
        .mark_bar()
        .encode(
            x=alt.X("Score:Q", title="Score (0–100)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("Block:N", sort=list(block_df["Block"]), title="Block",
                    axis=alt.Axis(labelLimit=200, labelOverlap=False)),
            color=alt.Color("Score:Q", scale=alt.Scale(scheme="blues"), legend=None),
            tooltip=[
                alt.Tooltip("Block:N", title="Block"),
                alt.Tooltip("Score:Q", title="Score", format=".1f"),
            ],
        )
        .properties(height=max(160, 36 * len(block_df)))
        + alt.Chart(block_df)
        .mark_text(align="left", dx=4, fontSize=12, fontWeight="bold")
        .encode(
            x=alt.X("Score:Q"),
            y=alt.Y("Block:N", sort=list(block_df["Block"])),
            text=alt.Text("Beschriftung:N"),
        )
    )
    st.altair_chart(block_chart, use_container_width=True)
    for _, r in block_df.iterrows():
        flag = ""
        for b, f in result["block_flags"].items():
            if BLOCK_NAMES.get(b, b) == r["Block"] and f:
                flag = f" [!] {f} (>30 % fehlende Daten)"
        score_str = "n/a" if r["Beschriftung"].endswith("n/a") else f"{r['Score']:.1f} / 100"
        st.write(f"- **{r['Block']}**: {score_str}{flag}")

    # Kriterien im Detail (inkl. "Daten duenn"-Markierung bei < thin_years Jahren)
    st.subheader("Kriterien im Detail")
    crit_rows = []
    for name, crit in criteria.items():
        cfg_c = CFG["criteria"][name]
        pts = result["details"][name]["points"]
        if crit.is_na:
            val_str = "n/a"
        elif name in ("roic_avg5", "roe_avg5", "fcf_margin_avg5", "revenue_cagr_5y", "fcf_yield_sbc_avg3"):
            val_str = f"{crit.value:.1%}"
        elif name == "fcf_positive_years":
            total_years = crit.years_total or crit.years_available
            val_str = f"{crit.value * total_years:.0f} / {total_years} ({crit.value:.0%})"
        else:
            val_str = f"{crit.value:.1f}"
        years = f"Daten dünn ({crit.years_available} J.)" if crit.thin else f"{crit.years_available} J."
        crit_rows.append({
            "Kriterium": name, "Block": cfg_c["block"], "Gewicht": f"{cfg_c['weight']:.1%}",
            "Wert": val_str, "Punkte": "n/a" if (pts != pts) else f"{pts:.1f}",
            "Daten": years,
        })
    st.dataframe(pd.DataFrame(crit_rows), width="stretch", hide_index=True)
    if res.get("thin_criteria"):
        st.caption(f"'Daten dünn (x J.)' = weniger als {CFG['data'].get('thin_years', 5)} Jahre Daten "
                   f"(Fenster: {CFG['data'].get('years', 5)} J.) – Score-Aussage eingeschränkt.")

    # ROIC: Definition + Rohwerte mit Einheit/Waehrung (neuestes FY)
    st.subheader("ROIC – Definition und Rohwerte (neuestes FY)")
    latest_fy = max(m.years)
    ym = m.years[latest_fy]
    ebit_m = ym.get("ebit")
    tax = tax_rate(m, latest_fy)
    np_ = nopat(m, latest_fy)
    ic = invested_capital(m, latest_fy)
    roic_val = roic(m, latest_fy)
    cur = ebit_m.currency if ebit_m else "n/a"

    def _fmt_abs(v: float) -> str:
        return "n/a" if (v != v) else f"{v / 1e9:,.2f} Mrd. {cur}"

    st.markdown(
        "**Formel:** ROIC = NOPAT / investiertes Kapital =  "
        "EBIT × (1 − Steuersatz) / (Eigenkapital + Nettoverschuldung), "
        "Kapitalbasis jeweils zum Jahresende des Geschaeftsjahres. "
    )
    roic_rows = pd.DataFrame([
        {"Komponente": "EBIT (Operating Income)", "Wert": _fmt_abs(ebit_m.value) if ebit_m else "n/a", "Jahr": latest_fy},
        {"Komponente": "Steuersatz (Steueraufwand / Vorsteuergewinn)", "Wert": "n/a" if tax != tax else f"{tax:.1%}", "Jahr": latest_fy},
        {"Komponente": "NOPAT = EBIT × (1 − Steuersatz)", "Wert": _fmt_abs(np_), "Jahr": latest_fy},
        {"Komponente": "Investiertes Kapital = EK + Nettoverschuldung", "Wert": _fmt_abs(ic), "Jahr": latest_fy},
        {"Komponente": "ROIC = NOPAT / investiertes Kapital", "Wert": "n/a" if roic_val != roic_val else f"{roic_val:.1%}", "Jahr": latest_fy},
    ])
    st.dataframe(roic_rows, width="stretch", hide_index=True)
    if roic_val == roic_val and roic_val > 1.0:
        st.warning(f"[!] ROIC {roic_val:.1%} > 100 % -> Flag **'kl.Kapital'**: "
                   f"die Kapitalbasis (EK + Nettoverschuldung = {_fmt_abs(ic)}) ist klein oder negativ "
                   "(z. B. Net-Cash-Position), daher ist der ROIC wenig aussagekraeftig.")

    # Formeln + Rohwerte fuer ROIC Ø, FCF-Yield, ND/EBITDA (mit Einheit/Jahr)
    st.subheader("Formeln & Rohwerte: ROIC Ø, FCF-Yield, ND/EBITDA")
    crit = res["criteria"]

    # --- ROIC Ø (ueber verfuegbare Jahre) ---
    st.markdown("**ROIC Ø** = Ø ( NOPAT / investiertes Kapital ) über die verfügbaren Jahre "
                f"(aktuell {crit['roic_avg5'].years_available}); "
                "NOPAT = EBIT × (1 − Steuersatz); investiertes Kapital = Eigenkapital + Nettoverschuldung "
                "(jeweils Jahresende).")
    roic_rows = []
    for fy in sorted(m.years, reverse=True)[:5]:
        y = m.years[fy]
        ebit = y.get("ebit"); eq = y.get("equity"); nd = y.get("net_debt")
        t = tax_rate(m, fy); n_ = nopat(m, fy); ic_ = invested_capital(m, fy); r_ = roic(m, fy)
        cur_y = ebit.currency if ebit else "n/a"
        roic_rows.append({
            "Jahr": fy,
            "EBIT": "n/a" if (not ebit or ebit.is_na()) else f"{ebit.value / 1e9:,.2f} Mrd. {cur_y}",
            "Steuersatz": "n/a" if t != t else f"{t:.1%}",
            "NOPAT": "n/a" if (n_ != n_) else f"{n_ / 1e9:,.2f} Mrd. {cur_y}",
            "EK": "n/a" if (not eq or eq.is_na()) else f"{eq.value / 1e9:,.2f} Mrd. {cur_y}",
            "Nettoversch.": "n/a" if (not nd or nd.is_na()) else f"{nd.value / 1e9:,.2f} Mrd. {cur_y}",
            "Inv. Kapital": "n/a" if (ic_ != ic_) else f"{ic_ / 1e9:,.2f} Mrd. {cur_y}",
            "ROIC": "n/a" if (r_ != r_) else f"{r_:.1%}",
        })
    st.dataframe(pd.DataFrame(roic_rows), width="stretch", hide_index=True)
    roic5 = crit["roic_avg5"]
    st.caption(f"ROIC Ø = Ø der obigen Jahre = "
               f"{'n/a' if roic5.is_na else f'{roic5.value:.1%}'} "
               f"({roic5.years_available} Jahre mit Daten). "
               f"Gewichtung im Quality-Score: {CFG['criteria']['roic_avg5']['weight']:.1%}.")

    # --- FCF-Yield (roh + nach SBC) ---
    st.markdown("**FCF-Yield** = FCF / Marktkapitalisierung; FCF = Operating Cashflow − |Capex|; "
                "**FCF-Yield (SBC)** = (FCF − Aktienverguetung) / Marktkapitalisierung "
                "(SBC aus dem Cashflow-Statement). "
                "Marktkap. in Quote-Währung (absolut), FCF in Berichtswährung → FX-Korrektur nötig.")
    mcap = m.market_cap
    fcf_rows = []
    for fy in sorted(m.years, reverse=True)[:3]:
        y = m.years[fy]
        f = y.get("fcf"); ocf = y.get("operating_cashflow"); cap = y.get("capex")
        sbc_m = y.get("stock_based_compensation"); fsbc = y.get("fcf_sbc")
        cur_y = f.currency if f else "n/a"
        yld = fcf_yield(m, fy)
        yld_sbc = fcf_yield_sbc(m, fy)
        fcf_rows.append({
            "Jahr": fy,
            "OCF": "n/a" if (not ocf or ocf.is_na()) else f"{ocf.value / 1e9:,.2f} Mrd. {cur_y}",
            "Capex": "n/a" if (not cap or cap.is_na()) else f"{cap.value / 1e9:,.2f} Mrd. {cur_y}",
            "FCF = OCF − |Capex|": "n/a" if (not f or f.is_na()) else f"{f.value / 1e9:,.2f} Mrd. {cur_y}",
            "SBC": "n/a" if (not sbc_m or sbc_m.is_na()) else f"{sbc_m.value / 1e9:,.2f} Mrd. {cur_y}",
            "FCF-SBC": "n/a" if (not fsbc or fsbc.is_na()) else f"{fsbc.value / 1e9:,.2f} Mrd. {cur_y}",
            "Marktkap.": ("n/a" if (not mcap or mcap.is_na())
                          else f"{mcap.value / 1e9:,.2f} Mrd. {mcap.currency}"),
            "FCF-Yield": "n/a" if (yld != yld) else f"{yld:.1%}",
            "FCF-Yield nach SBC": "n/a" if (yld_sbc != yld_sbc) else f"{yld_sbc:.1%}",
        })
    st.dataframe(pd.DataFrame(fcf_rows), width="stretch", hide_index=True)
    fy3 = crit["fcf_yield_sbc_avg3"]
    st.caption(f"FCF-Yield 3J (SBC) = Ø der letzten 3 Jahre = "
               f"{'n/a' if fy3.is_na else f'{fy3.value:.1%}'} "
               f"({fy3.years_available} Jahre). "
               f"Gewichtung im Value-Score: {CFG['criteria']['fcf_yield_sbc_avg3']['weight']:.1%}.")

    # --- ND/EBITDA ---
    st.markdown("**ND/EBITDA** = Nettoverschuldung / EBITDA (neuestes Geschäftsjahr); "
                "Nettoverschuldung = Finanzverbindlichkeiten − liquide Mittel (Jahresende).")
    nd_rows = []
    for fy in sorted(m.years, reverse=True)[:5]:
        y = m.years[fy]
        nd = y.get("net_debt"); eb = y.get("ebitda")
        cur_y = eb.currency if eb else "n/a"
        ratio = (nd.value / eb.value) if (nd and eb and not nd.is_na() and not eb.is_na() and eb.value != 0) else float("nan")
        nd_rows.append({
            "Jahr": fy,
            "EBITDA": "n/a" if (not eb or eb.is_na()) else f"{eb.value / 1e9:,.2f} Mrd. {cur_y}",
            "Nettoverschuldung": "n/a" if (not nd or nd.is_na()) else f"{nd.value / 1e9:,.2f} Mrd. {cur_y}",
            "ND/EBITDA": "n/a" if (ratio != ratio) else f"{ratio:.1f}",
        })
    st.dataframe(pd.DataFrame(nd_rows), width="stretch", hide_index=True)
    nde = crit["net_debt_ebitda"]
    st.caption(f"ND/EBITDA (neuestes Jahr) = "
               f"{'n/a' if nde.is_na else f'{nde.value:.1f}'} "
               f"({nde.years_available} Jahre). "
               f"Gewichtung im Quality-Score: {CFG['criteria']['net_debt_ebitda']['weight']:.1%}.")

    # --- DCF: 3 Szenarien mit Annahmen und Jahres-Cashflows -------------------
    st.subheader("DCF – Innerer Wert je Aktie (3 Szenarien)")
    dcf_section(m, res["row"])

    # Jahres-Charts
    st.subheader("Kennzahlen im Zeitverlauf (5 Jahre)")
    years = sorted(m.years)
    chart_df = pd.DataFrame(index=years)

    def _num(y: dict, key: str) -> float | None:
        m_ = y.get(key)
        return None if (m_ is None or m_.is_na()) else m_.value

    rev = [_num(m.years[fy], "revenue") for fy in years]
    chart_df["Umsatz (Mrd.)"] = [None if r is None else r / 1e9 for r in rev]
    fcf = [_num(m.years[fy], "fcf") for fy in years]
    chart_df["FCF-Marge"] = [
        None if (f is None or r is None or r == 0) else f / r for f, r in zip(fcf, rev)
    ]
    chart_df["ROIC"] = [roic(m, fy) for fy in years]
    nd = [_num(m.years[fy], "net_debt") for fy in years]
    chart_df["Nettoverschuldung (Mrd.)"] = [None if v is None else v / 1e9 for v in nd]
    st.line_chart(chart_df)

    if res["violations"]:
        st.subheader("Sanity-Verstoesse (Log)")
        for v in res["violations"]:
            st.warning(v)

    # Rohdaten mit Einheit, Waehrung, Jahr, Quelle
    st.subheader(f"Rohdaten (Quelle: {m.source or 'unbekannt'})")
    raw_rows = []
    for fy in years:
        ym = m.years[fy]
        for key in ("revenue", "ebit", "ebitda", "net_income", "operating_cashflow", "capex",
                    "fcf", "equity", "net_debt", "interest_expense"):
            met = ym.get(key)
            if met is None:
                continue
            raw_rows.append({
                "Jahr": fy, "Kennzahl": key, "Wert": "n/a" if met.is_na() else f"{met.value:,.0f}",
                "Einheit": met.unit, "Waehrung": met.currency,
            })
    st.dataframe(pd.DataFrame(raw_rows), width="stretch", hide_index=True)

    # --- Referenz-Check: UBER, NVDA, KO (Rohwerte + Formeln) -----------------
    reference_formula_section()

    # --- Rohwerte ADBE & PYPL: FCF, SBC, Bilanz, Marktkapitalisierung ---------
    sbc_detail_section()



def _formula_block(m: TickerMetrics, label: str) -> None:
    """Kompakte Formel-Anzeige fuer einen Ticker: ROIC 5J, FCF-Yield, ND/EBITDA."""
    st.markdown(f"### {label} – {m.name} ({m.ticker})  ·  Quelle: {m.source or 'unbekannt'}")
    crit = compute_criteria(m, CFG)
    latest_fy = max(m.years)

    # ROIC 5J
    st.markdown("**ROIC 5J** = Ø (EBIT × (1 − Steuersatz) / (EK + Nettoverschuldung)) über 5 Jahre")
    rows = []
    for fy in sorted(m.years, reverse=True)[:5]:
        y = m.years[fy]
        ebit = y.get("ebit"); nd = y.get("net_debt"); eq = y.get("equity")
        t = tax_rate(m, fy); n_ = nopat(m, fy); ic_ = invested_capital(m, fy); r_ = roic(m, fy)
        cur = ebit.currency if ebit else "n/a"
        rows.append({
            "Jahr": fy,
            "EBIT": "n/a" if (not ebit or ebit.is_na()) else f"{ebit.value/1e9:,.2f} Mrd. {cur}",
            "NOPAT": "n/a" if (n_ != n_) else f"{n_/1e9:,.2f} Mrd. {cur}",
            "EK + ND": "n/a" if (ic_ != ic_) else f"{ic_/1e9:,.2f} Mrd. {cur}",
            "ROIC": "n/a" if (r_ != r_) else f"{r_:.1%}",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    r5 = crit["roic_avg5"]
    st.caption(f"ROIC 5J = {'n/a' if r5.is_na else f'{r5.value:.1%}'} ({r5.years_available} J.)")

    # FCF-Yield (roh + nach SBC)
    st.markdown("**FCF-Yield** = FCF / Marktkapitalisierung (FCF = OCF − |Capex|); "
                "**FCF-Yield (SBC)** = (FCF − Aktienverguetung) / Marktkapitalisierung")
    rows = []
    for fy in sorted(m.years, reverse=True)[:3]:
        y = m.years[fy]
        f = y.get("fcf"); ocf = y.get("operating_cashflow"); cap = y.get("capex")
        sbc_m = y.get("stock_based_compensation"); fsbc = y.get("fcf_sbc")
        cur = f.currency if f else "n/a"
        yld = fcf_yield(m, fy)
        yld_sbc = fcf_yield_sbc(m, fy)
        mc = m.market_cap
        rows.append({
            "Jahr": fy,
            "OCF": "n/a" if (not ocf or ocf.is_na()) else f"{ocf.value/1e9:,.2f} Mrd. {cur}",
            "Capex": "n/a" if (not cap or cap.is_na()) else f"{cap.value/1e9:,.2f} Mrd. {cur}",
            "FCF": "n/a" if (not f or f.is_na()) else f"{f.value/1e9:,.2f} Mrd. {cur}",
            "SBC": "n/a" if (not sbc_m or sbc_m.is_na()) else f"{sbc_m.value/1e9:,.2f} Mrd. {cur}",
            "FCF-SBC": "n/a" if (not fsbc or fsbc.is_na()) else f"{fsbc.value/1e9:,.2f} Mrd. {cur}",
            "Marktkap.": "n/a" if (not mc or mc.is_na()) else f"{mc.value/1e9:,.2f} Mrd. {mc.currency}",
            "FCF-Yield": "n/a" if (yld != yld) else f"{yld:.1%}",
            "FCF-Yield nach SBC": "n/a" if (yld_sbc != yld_sbc) else f"{yld_sbc:.1%}",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    fy3 = crit["fcf_yield_sbc_avg3"]
    st.caption(f"FCF-Yield 3J (SBC) = {'n/a' if fy3.is_na else f'{fy3.value:.1%}'} ({fy3.years_available} J.)")

    # ND/EBITDA
    st.markdown("**ND/EBITDA** = Nettoverschuldung / EBITDA (neuestes Jahr)")
    rows = []
    for fy in sorted(m.years, reverse=True)[:5]:
        y = m.years[fy]
        nd = y.get("net_debt"); eb = y.get("ebitda")
        cur = eb.currency if eb else "n/a"
        ratio = (nd.value / eb.value) if (nd and eb and not nd.is_na() and not eb.is_na() and eb.value != 0) else float("nan")
        rows.append({
            "Jahr": fy,
            "EBITDA": "n/a" if (not eb or eb.is_na()) else f"{eb.value/1e9:,.2f} Mrd. {cur}",
            "Nettoversch.": "n/a" if (not nd or nd.is_na()) else f"{nd.value/1e9:,.2f} Mrd. {cur}",
            "ND/EBITDA": "n/a" if (ratio != ratio) else f"{ratio:.1f}",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    nde = crit["net_debt_ebitda"]
    st.caption(f"ND/EBITDA (neuestes Jahr) = {'n/a' if nde.is_na else f'{nde.value:.1f}'} "
               f"({nde.years_available} J.) — Einheit: Verhältnis (x), Währungen konsistent.")


@st.cache_data(ttl=3600, show_spinner=False)
def _load_reference_tickers(tickers: tuple[str, ...]) -> list[TickerMetrics]:
    providers = build_providers(os.environ.get("FMP_API_KEY", ""))
    out = []
    for t in tickers:
        try:
            out.append(load_with_provider(t, CFG, providers, years=CFG["data"]["years"]))
        except ProviderError as exc:
            logger.warning("Referenz-Ticker %s nicht geladen: %s", t, exc)
    return out


def reference_formula_section() -> None:
    """Vergleich der Formeln + Rohwerte fuer UBER, NVDA, KO (live via Provider)."""
    st.divider()
    st.subheader("Referenz-Check: UBER, NVDA, KO — Rohwerte & Formeln")
    st.caption("ROIC 5J, FCF-Yield und ND/EBITDA mit Rohwerten, Einheit und Jahr. "
               "Live-Laden via yfinance/FMP; ohne Netzwerk/Key erscheint ein Hinweis.")

    refs = ("UBER", "NVDA", "KO")
    with st.spinner("Lade UBER, NVDA, KO (yfinance/FMP) …"):
        companies = _load_reference_tickers(refs)

    if not companies:
        st.info("UBER, NVDA, KO konnten nicht live geladen werden (kein yfinance/Netzwerk "
                "oder kein FMP_API_KEY). Installiere yfinance (`pip install yfinance`) und "
                "lasse die App mit Netzwerk neu starten. Die Formeln oben gelten fuer jeden "
                "auswählbaren Ticker.")
        return

    for m in companies:
        with st.expander(f"{m.ticker} – {m.name}", expanded=(m.ticker == "UBER")):
            _formula_block(m, "Referenz")


def _customer_deposit_note(cd, rc, cash) -> str:
    """Hinweis, ob Kundengelder in 'Cash' enthalten sind (Feld oder Hinweis)."""
    if cd is not None and not cd.is_na() and cash is not None and not cash.is_na() and cash.value > 0:
        return f"ja — {cd.value / 1e9:,.2f} Mrd. ({cd.value / cash.value:.0%} von Cash)"
    if cd is not None and not cd.is_na():
        return f"ja — {cd.value / 1e9:,.2f} Mrd. (Cash n/a)"
    if rc is not None and not rc.is_na() and rc.value > 0:
        return (f"unbekannt (keine Deposit-Liabilities-Zeile); Restricted Cash "
                f"{rc.value / 1e9:,.2f} Mrd. als Naeherung")
    if cash is not None and not cash.is_na():
        return "unbekannt — lt. 10-K sind Kundengelder in Cash enthalten"
    return "unbekannt (Cash n/a)"


def sbc_detail_section() -> None:
    """Expander mit Rohwerten fuer ADBE und PYPL: FCF je Jahr, SBC je Jahr,
    Bilanzdaten je Jahr (Cash, kurzfristige Anlagen, Finanzschulden,
    Nettoverschuldung + Kundengelder-Hinweis) und Marktkapitalisierung
    mit Waehrung und Stichtag (live via Provider)."""
    st.divider()
    st.subheader("Rohwerte: ADBE & PYPL — FCF, SBC, Bilanz, Marktkapitalisierung")
    st.caption("FCF = Operating Cashflow − |Capex|; SBC = Aktienverguetung (Stock Based "
               "Compensation); FCF nach SBC = FCF − SBC. Bilanz: Cash And Cash Equivalents, "
               "Short Term Investments (kurzfristige Anlagen), Total Debt (Finanzschulden), "
               "Net Debt (Nettoverschuldung; gemeldet, sonst Total Debt − Cash). "
               "Kundengelder = 'Deposit Liabilities' (z. B. PayPal Verwahrkundengelder, in "
               "Cash enthalten) — das DCF subtrahiert die Nettoverschuldung OHNE "
               "Kundengelder, addiert sie also hinzu. Betraege absolut in Berichtswährung. "
               "Marktkapitalisierung mit Stichtag (Abrufdatum). Live-Laden via yfinance/FMP.")

    with st.spinner("Lade ADBE, PYPL (yfinance/FMP) …"):
        companies = _load_reference_tickers(("ADBE", "PYPL"))
    if not companies:
        st.info("ADBE und PYPL konnten nicht live geladen werden (kein yfinance/Netzwerk "
                "oder kein FMP_API_KEY). Installiere yfinance (`pip install yfinance`) und "
                "lasse die App mit Netzwerk neu starten.")
        return
    for m in companies:
        with st.expander(f"{m.ticker} – {m.name}  ·  Quelle: {m.source or 'unbekannt'}",
                         expanded=(m.ticker == "ADBE")):
            mc = m.market_cap
            if mc is not None and not mc.is_na():
                st.write(f"**Marktkapitalisierung:** {mc.value / 1e9:,.2f} Mrd. "
                         f"{mc.currency} (Stichtag: {m.market_cap_date or 'n/a'})")
            else:
                st.write("**Marktkapitalisierung:** n/a")
            st.markdown("**Cashflow (je Geschaeftsjahr)**")
            rows = []
            for fy in sorted(m.years, reverse=True):
                y = m.years[fy]
                ocf = y.get("operating_cashflow"); cap = y.get("capex")
                f = y.get("fcf"); sbc = y.get("stock_based_compensation")
                fsbc = y.get("fcf_sbc")
                cur = f.currency if f else "n/a"
                rows.append({
                    "Jahr": fy,
                    "OCF": "n/a" if (not ocf or ocf.is_na()) else f"{ocf.value / 1e9:,.2f} Mrd. {cur}",
                    "Capex": "n/a" if (not cap or cap.is_na()) else f"{cap.value / 1e9:,.2f} Mrd. {cur}",
                    "FCF": "n/a" if (not f or f.is_na()) else f"{f.value / 1e9:,.2f} Mrd. {cur}",
                    "SBC": "n/a" if (not sbc or sbc.is_na()) else f"{sbc.value / 1e9:,.2f} Mrd. {cur}",
                    "FCF − SBC": "n/a" if (not fsbc or fsbc.is_na()) else f"{fsbc.value / 1e9:,.2f} Mrd. {cur}",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.markdown("**Bilanz (je Geschaeftsjahr, Jahresende)**")
            brows = []
            for fy in sorted(m.years, reverse=True):
                y = m.years[fy]
                cash = y.get("_cash"); sti = y.get("_short_term_investments")
                td = y.get("_total_debt"); nd = y.get("net_debt")
                cd = y.get("customer_deposits"); rc = y.get("_restricted_cash")

                def _b(met) -> str:
                    return "n/a" if (met is None or met.is_na()) else f"{met.value / 1e9:,.2f}"

                # Nettoverschuldung: gemeldetes Net Debt, sonst Total Debt - Cash
                if nd is not None and not nd.is_na():
                    nd_val, nd_src = nd.value, "Net Debt (gemeldet)"
                elif td is not None and not td.is_na() and cash is not None and not cash.is_na():
                    nd_val, nd_src = td.value - cash.value, "Total Debt − Cash"
                else:
                    nd_val, nd_src = float("nan"), "n/a"
                brows.append({
                    "Jahr": fy,
                    "Cash (Mrd.)": _b(cash),
                    "Kurzfr. Anlagen (Mrd.)": _b(sti),
                    "Finanzschulden (Mrd.)": _b(td),
                    "Nettoverschuldung (Mrd.)": "n/a" if nd_val != nd_val else f"{nd_val / 1e9:,.2f}",
                    "ND-Quelle": nd_src,
                    "Kundengelder (Mrd.)": "n/a" if (cd is None or cd.is_na()) else f"{cd.value / 1e9:,.2f}",
                    "Kundengelder in Cash?": _customer_deposit_note(cd, rc, cash),
                })
            st.dataframe(pd.DataFrame(brows), width="stretch", hide_index=True)
            st.caption("Einheit: Mrd. Berichtswährung; Jahr = Geschaeftsjahr (Jahresende). "
                       "n/a = Daten fehlen (nie mit 0 gefuellt). Kundengelder (Deposit "
                       "Liabilities, z. B. PayPal) sind in 'Cash And Cash Equivalents' "
                       "enthalten und gehoeren wirtschaftlich nicht zum Unternehmen; "
                       "das DCF zieht die Nettoverschuldung ohne Kundengelder ab "
                       "(addiert sie also zur gemeldeten Nettoverschuldung hinzu).")


def dcf_section(m: TickerMetrics, row: dict | None) -> None:
    """DCF-Tabelle: Annahmen je Szenario, Jahre 1-10 (FCF, Abzinsungsfaktor,
    Barwert), Terminal Value, Nettoverschuldung, Aktien, innerer Wert je Aktie,
    Kurs und MoS je Szenario + Sensitivitaetstabelle."""
    from valuation.dcf import compute_dcf, sensitivity_mos_base
    dcf = compute_dcf(m, CFG)
    dc = CFG["dcf"]
    if dcf.fcf_normalized != dcf.fcf_normalized or not dcf.scenarios:
        st.info("DCF nicht berechenbar (kein FCF nach SBC oder keine Marktkapitalisierung).")
        return
    cur = m.market_cap.currency if m.market_cap else "n/a"
    r = dcf.discount_rate
    g_term = dcf.terminal_growth
    cap = dc.get("base_growth_cap", 0.06)
    mult = dc.get("bull_growth_multiplier", 1.3)
    bull_cap = dc.get("bull_growth_cap", 0.10)
    fade = dc.get("fade_to_growth", 0.025)
    cagr_s = "n/a" if dcf.revenue_cagr != dcf.revenue_cagr else f"{dcf.revenue_cagr:.1%}"

    # --- Annahmen je Szenario ---
    st.markdown("**Annahmen je Szenario**")
    ann_rows = []
    for name in ("Bear", "Base", "Bull"):
        sc = dcf.scenarios.get(name.lower())
        g5_val = sc.growth_rates[0] if sc else float("nan")
        basis_short = ("TTM Ø" if dcf.fcf_basis == "ttm" else "Ø GJ")
        ann_rows.append({
            "Szenario": name,
            f"Start-FCF nach SBC ({basis_short})": f"{dcf.fcf_normalized_conv / 1e9:,.2f} Mrd. {cur}",
            "Wachstum J. 1–5": "n/a" if g5_val != g5_val else f"{g5_val:.1%}",
            "Wachstum J. 6–10": f"linear auf {fade:.1%}",
            "Terminal Growth": f"{g_term:.1%}",
            "Diskontsatz": f"{r:.1%}",
        })
    st.dataframe(pd.DataFrame(ann_rows), width="stretch", hide_index=True)
    # TTM-Basis: Stichtag des letzten Quartals + verwendete Quellen
    if dcf.fcf_basis == "ttm" and dcf.ttm_quarter_end:
        basis_label = f"TTM bis {dcf.ttm_quarter_end[:7]} (Stichtag {dcf.ttm_quarter_end})"
        src_labels = " + ".join(name for name, _, _ in dcf.fcf_sources)
        basis_note = (f"**Basis: {basis_label}** — Ø aus {src_labels} "
                      f"(TTM + nicht überlappende Geschäftsjahre)")
    else:
        src_labels = " + ".join(name for name, _, _ in dcf.fcf_sources) if dcf.fcf_sources else ""
        basis_note = (f"Basis: Geschäftsjahre (Ø letzte {dcf.fcf_years_used} Jahre"
                      + (f" — {src_labels}" if src_labels else "") + ")"
                      + (" · [!] Quartalsdaten unplausibel → Rückfall" if not getattr(m, "ttm_plausible", True) else ""))
    st.caption(
        f"Normalisierter FCF (Ø {dcf.fcf_years_used} Perioden, nach SBC): "
        f"**{dcf.fcf_normalized / 1e9:,.2f} Mrd. Berichtswährung** "
        f"→ {dcf.fcf_normalized_conv / 1e9:,.2f} Mrd. {cur} (FX) · "
        f"{basis_note} · "
        f"Umsatz-CAGR (verfügbare Jahre): {cagr_s} · "
        f"Verwässerte Aktien: {dcf.shares / 1e9:,.2f} Mrd. · "
        "Wachstum: Bear 0 % (J. 1–5) · Base = min(CAGR, "
        f"{cap:.0%}) · Bull = min(CAGR × {mult:.1f}, {bull_cap:.0%}); "
        f"J. 6–10 linear auf {fade:.1%}. Terminal Value = FCF_10 × (1 + g) / (r − g)."
    )

    # --- Jahre 1-10: FCF, Abzinsungsfaktor, Barwert je Szenario ---
    st.markdown("**Projizierte Cashflows (Jahre 1–10)**")
    rows = []
    for name in ("bear", "base", "bull"):
        sc = dcf.scenarios.get(name)
        if sc is None:
            continue
        for i, (g, f) in enumerate(zip(sc.growth_rates, sc.fcfs), start=1):
            df_ = 1.0 / (1.0 + r) ** i
            rows.append({
                "Szenario": name, "Jahr": i, "Wachstum": f"{g:.1%}",
                f"FCF (Mrd. {cur})": f"{f / 1e9:,.2f}",
                "Abzinsungsfaktor": f"{df_:.4f}",
                f"Barwert (Mrd. {cur})": f"{f * df_ / 1e9:,.2f}",
            })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # --- Nettoverschuldung, Aktien, innerer Wert je Aktie, Kurs, MoS ---
    # Nettoverschuldung OHNE Kundengelder (wie im DCF verwendet);
    # Kundengelder (z. B. PYPL) sitzen in Cash und werden hinzuaddiert.
    nd_val = dcf.net_debt
    nd_s = "n/a"
    if nd_val == nd_val:
        nd_s = f"{nd_val / 1e9:,.2f} Mrd. {cur}"
        if dcf.customer_deposits == dcf.customer_deposits:
            nd_s += f" (exkl. Kundengelder {dcf.customer_deposits / 1e9:,.2f} Mrd.)"
        if dcf.net_debt_source:
            nd_s += f" · {dcf.net_debt_source}"
    price = None
    if m.market_cap is not None and not m.market_cap.is_na() and dcf.shares == dcf.shares:
        price = m.market_cap.value / dcf.shares
    sum_rows = []
    for name in ("bear", "base", "bull"):
        sc = dcf.scenarios.get(name)
        if sc is None:
            continue
        vps = sc.value_per_share
        mos_s = "n/a"
        if vps == vps and price is not None and vps > 0:
            mos_s = f"{(1.0 - price / vps):.1%}"
        tv_share = "n/a"
        if sc.enterprise_value == sc.enterprise_value and sc.enterprise_value != 0:
            tv_share = f"{sc.terminal_value / sc.enterprise_value:.1%}"
        sum_rows.append({
            "Szenario": name,
            f"Barwert FCFs (Mrd. {cur})": f"{sc.pv_fcfs / 1e9:,.2f}",
            f"Terminal Value (Mrd. {cur})": f"{sc.terminal_value / 1e9:,.2f}",
            "TV-Anteil am Wert": tv_share,
            "Nettoverschuldung": nd_s,
            "Aktien (Mrd.)": f"{dcf.shares / 1e9:,.2f}",
            "Innerer Wert (Mrd.)": "n/a" if sc.enterprise_value != sc.enterprise_value else f"{sc.enterprise_value / 1e9:,.2f}",
            "Wert je Aktie": "n/a" if vps != vps else f"{vps:,.2f} {cur}",
            "Kurs": "n/a" if price is None else f"{price:,.2f} {cur}",
            "MoS": mos_s,
        })
    st.dataframe(pd.DataFrame(sum_rows), width="stretch", hide_index=True)
    mos = dcf.margin_of_safety
    st.write(f"**Kurs:** {'n/a' if price is None else f'{price:,.2f} {cur}'} · "
             f"**Margin of Safety (Base):** {'n/a' if mos != mos else f'{mos:.1%}'}")

    # --- Startwert umschaltbar: O3J / juengstes GJ / TTM -> MoS Base nebeneinander ---
    st.markdown("**Startwert (umschaltbar): MoS (Base) je FCF-Modus**")
    mode_rows = []
    for mode, label in (("avg3", "Ø letzte 3 GJ"), ("latest", "Jüngstes GJ"),
                        ("ttm", "TTM (4 Quartale)")):
        dcf_m = compute_dcf(m, CFG, fcf_mode=mode)
        base_m = dcf_m.scenarios.get("base")
        mos_m = dcf_m.margin_of_safety
        vps_m = base_m.value_per_share if base_m is not None else float("nan")
        basis_m = ("TTM" if dcf_m.fcf_basis == "ttm" else "GJ")
        if dcf_m.fcf_basis == "ttm" and dcf_m.ttm_quarter_end:
            basis_m = f"TTM bis {dcf_m.ttm_quarter_end[:7]}"
        mode_rows.append({
            "Modus": label,
            "Basis": basis_m,
            "Start-FCF n. SBC (Mrd.)": "n/a" if dcf_m.fcf_normalized != dcf_m.fcf_normalized
            else f"{dcf_m.fcf_normalized_conv / 1e9:,.2f} {cur}",
            "Wert je Aktie (Base)": "n/a" if vps_m != vps_m else f"{vps_m:,.2f} {cur}",
            "Kurs": "n/a" if price is None else f"{price:,.2f} {cur}",
            "MoS (Base)": "n/a" if mos_m != mos_m else f"{mos_m:.1%}",
            "Aktiv": "●" if dcf_m.fcf_mode == dcf.fcf_mode else "",
        })
    st.dataframe(pd.DataFrame(mode_rows), width="stretch", hide_index=True)
    st.caption("Startwert des DCF umschaltbar (config.yaml `dcf.fcf_mode`, Default 'auto': "
               "TTM falls plausibel, sonst Ø letzte 3 GJ). '●' markiert den aktiven Modus. "
               "MoS (Base) = 1 − Kurs / Wert je Aktie (Base) je Modus.")

    # --- Sensitivitaetstabelle: MoS (Base) ueber Diskontsatz x Terminal Growth ---
    st.markdown("**Sensitivität: MoS (Base) je Aktie**")
    sens = sensitivity_mos_base(m, CFG, current_price=price)
    if sens and not sens["mos"].empty:
        mos_df = sens["mos"].copy()
        vps_df = sens["vps"].copy()
        mos_df["label"] = mos_df["discount_rate"].map(lambda r: f"{r:.0%}") + " \\ " + \
            mos_df["terminal_growth"].map(lambda g: f"g = {g:.1%}")
        mos_pivot = mos_df.pivot(index="discount_rate", columns="terminal_growth", values="mos")
        mos_pivot = mos_pivot.sort_index().sort_index(axis=1)
        mos_pivot.index = [f"{r:.0%}" for r in mos_pivot.index]
        mos_pivot.columns = [f"g = {g:.1%}" for g in mos_pivot.columns]
        mos_pivot = mos_pivot.map(lambda v: "n/a" if v != v else f"{v:.1%}")
        mos_pivot.index.name = "Diskontsatz \\ Terminal Growth"
        st.dataframe(mos_pivot.reset_index(), width="stretch", hide_index=True)
        vps_pivot = vps_df.pivot(index="discount_rate", columns="terminal_growth",
                                 values="value_per_share")
        vps_pivot = vps_pivot.sort_index().sort_index(axis=1)
        vps_pivot.index = [f"{r:.0%}" for r in vps_pivot.index]
        vps_pivot.columns = [f"g = {g:.1%}" for g in vps_pivot.columns]
        vps_pivot = vps_pivot.map(lambda v: "n/a" if v != v else f"{v:,.2f} {cur}")
        vps_pivot.index.name = "Diskontsatz \\ Terminal Growth"
        st.markdown("**Innerer Wert je Aktie** (Base-Pfad) je Kombination")
        st.dataframe(vps_pivot.reset_index(), width="stretch", hide_index=True)
        st.caption(f"Innerer Wert je Aktie (Base-Pfad) ueber Diskontsatz × Terminal Growth; "
                   f"Kurs = {'n/a' if price is None else f'{price:,.2f} {cur}'}; "
                   f"MoS (Base) = 1 − Kurs / Wert je Aktie. "
                   f"Aktuell: Wert je Aktie Bear/Base/Bull = "
                   + ", ".join(
                       ("n/a" if dcf.scenarios[n].value_per_share != dcf.scenarios[n].value_per_share
                        else f"{dcf.scenarios[n].value_per_share:,.2f} {cur}")
                       for n in ("bear", "base", "bull") if n in dcf.scenarios)
                   + f"; Kurs = {'n/a' if price is None else f'{price:,.2f} {cur}'}; "
                     f"MoS (Base) = {'n/a' if mos != mos else f'{mos:.1%}'}.")

    buy = bool(row and row.get("is_buy"))
    if buy:
        st.success("[KAUF] Kaufkandidat (Quality >= 60, MoS Base >= 30 %, Bear >= 80 % des Kurses)")
    st.caption("Formel: Unternehmenswert = SUMME FCF_t/(1+r)^t (t=1..10) + [FCF_10 x (1+g)/(r-g)]/(1+r)^10; "
               "Innerer Wert = Unternehmenswert − Nettoverschuldung (ohne Kundengelder); "
               "Wert je Aktie = Innerer Wert / verwässerte Aktien; "
               "MoS (Base) = 1 − Kurs / Wert je Aktie (Base). "
               "Kaufkandidat: Quality ≥ 60 UND MoS Base ≥ 30 % UND Bear ≥ 80 % des Kurses "
               "(Schwellen in config.yaml, Block `dcf`).")


# --- Seite 3: Matrix (Quality vs. Value) -------------------------------------

def page_matrix() -> None:
    """Streudiagramm Quality (x) vs. Value (y); Punkte mit Ticker beschriftet.

    Quadrant oben rechts (Quality >= Median, Value >= Median) hervorgehoben --
    dort liegen die interessantesten Kandidaten (hohe Qualitaet UND guenstige
    Bewertung).
    """
    st.header("Matrix: Quality vs. Value")
    rows = st.session_state["rows"]
    if not rows:
        st.info("Keine Ticker zum Anzeigen.")
        return

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["quality", "value"])
    if df.empty:
        st.info("Keine Ticker mit Quality- und Value-Score verfuegbar.")
        return

    med_q = float(df["quality"].median())
    med_v = float(df["value"].median())

    base = alt.Chart(df).encode(
        x=alt.X("quality:Q", title="Quality-Score (0–100)", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("value:Q", title="Value-Score (0–100)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[
            alt.Tooltip("ticker:N", title="Ticker"),
            alt.Tooltip("name:N", title="Name"),
            alt.Tooltip("quality:Q", title="Quality", format=".1f"),
            alt.Tooltip("value:Q", title="Value", format=".1f"),
            alt.Tooltip("score:Q", title="Score", format=".1f"),
            alt.Tooltip("coverage:Q", title="Datenabdeckung", format=".1%"),
            alt.Tooltip("sector:N", title="Sektor"),
        ],
    )

    # Quadrant oben rechts hervorheben (Rechteck hinter den Punkten)
    quadrant = alt.Chart(pd.DataFrame([{
        "x0": med_q, "x1": 100, "y0": med_v, "y1": 100,
    }])).mark_rect(color="#2e7d32", opacity=0.12).encode(
        x=alt.X("x0:Q"), x2=alt.X2("x1:Q"),
        y=alt.Y("y0:Q"), y2=alt.Y2("y1:Q"),
    )

    # Mittellinien (Median)
    vline = alt.Chart(pd.DataFrame([{"x": med_q}])).mark_rule(
        color="#888", strokeDash=[4, 4]).encode(x="x:Q")
    hline = alt.Chart(pd.DataFrame([{"y": med_v}])).mark_rule(
        color="#888", strokeDash=[4, 4]).encode(y="y:Q")

    points = base.mark_circle(size=140, opacity=0.85).encode(
        color=alt.condition(
            (alt.datum.quality >= med_q) & (alt.datum.value >= med_v),
            alt.value("#2e7d32"),   # oben rechts: gruen
            alt.value("#9e9e9e"),   # sonst: grau
        ),
    )
    labels = base.mark_text(dx=8, dy=-8, fontSize=11, fontWeight="bold").encode(
        text="ticker:N",
    )

    chart = (quadrant + vline + hline + points + labels).properties(
        width=720, height=560,
        title=f"Quality vs. Value (Median: Q={med_q:.1f}, V={med_v:.1f})",
    ).interactive()
    st.altair_chart(chart, use_container_width=True)

    st.caption("Oben rechts (gruen): hohe Qualitaet UND guenstige Bewertung – "
               "bevorzugte Kaufkandidaten. Gestrichelte Linien = Median. "
               f"{int((df['quality'] >= med_q).sum() & (df['value'] >= med_v).sum())} "
               f"Ticker im Ziel-Quadranten.")

    # Tabelle der Ticker im Ziel-Quadranten
    target = df[(df["quality"] >= med_q) & (df["value"] >= med_v)].sort_values(
        "score", ascending=False)
    if not target.empty:
        st.subheader("Ziel-Quadrant (Quality ≥ Median UND Value ≥ Median)")
        tview = target[["ticker", "name", "quality", "value", "score", "coverage", "sector"]].copy()
        tview["quality"] = tview["quality"].map(lambda v: f"{v:.1f}")
        tview["value"] = tview["value"].map(lambda v: f"{v:.1f}")
        tview["score"] = tview["score"].map(lambda v: f"{v:.1f}")
        tview["coverage"] = tview["coverage"].map(lambda v: "n/a" if (v != v) else f"{v:.1%}")
        st.dataframe(
            tview.rename(columns={"ticker": "Ticker", "name": "Name", "quality": "Quality",
                                  "value": "Value", "score": "Score", "coverage": "Datenabdeckung",
                                  "sector": "Sektor"}),
            width="stretch", hide_index=True,
        )


# --- Seite 4: Import ---------------------------------------------------------

def page_import() -> None:
    st.header("Import / manuelle Eingabe")
    st.caption("CSV mit einer Spalte `ticker` (eine Zeile pro Ticker). "
               "US-Ticker -> FMP (FMP_API_KEY noetig), alle anderen (z. B. .DE, .CO) -> yfinance; "
               "yfinance funktioniert ohne API-Key.")

    uploaded = st.file_uploader("Ticker-CSV hochladen", type=["csv"])
    tickers: list[str] = []
    if uploaded is not None:
        try:
            tickers = parse_ticker_csv(uploaded.getvalue())
            st.write(f"{len(tickers)} Ticker gefunden: {', '.join(tickers[:20])}{' …' if len(tickers) > 20 else ''}")
        except Exception as exc:
            st.error(f"CSV konnte nicht gelesen werden: {exc}")

    manual = st.text_area("Oder Ticker manuell eingeben (kommagetrennt)", value="")
    if manual.strip():
        tickers = parse_ticker_text(manual) or tickers

    if tickers:
        if st.button(f"Ticker laden ({len(tickers)} Stueck, Provider je Suffix)"):
            with st.spinner(f"Lade {len(tickers)} Ticker (FMP/yfinance) …"):
                companies = load_live(tuple(tickers), CFG["data"]["years"])
            st.session_state["imported_companies"] = companies
            st.session_state["live_tickers"] = tickers
            st.success(f"{len(companies)} Ticker geladen. Weiter zu Seite 1/2.")
    if "imported_companies" in st.session_state:
        if st.button("Import zuruecksetzen (zurueck zu Live/Demo)"):
            st.session_state.pop("imported_companies", None)
            st.session_state.pop("live_tickers", None)
            st.rerun()


# --- App ---------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Value-Screener", page_icon=":material/trending_up:", layout="wide")
    st.title(":material/trending_up: Value-Screener")
    st.caption("Qualitaets- und Bewertungs-Screening (Buffett-Ansatz) – Einheiten konsistent in absoluten Betraegen")

    companies, source, source_kind = get_companies()
    with st.spinner(f"Werte Ticker aus ({source}) …"):
        rows, excluded = evaluate_all(companies, CFG)
    st.session_state["companies"] = companies
    st.session_state["rows"] = rows
    st.session_state["excluded"] = excluded
    st.session_state["source"] = source
    st.session_state["source_kind"] = source_kind

    page_ranking_fn = st.Page(page_ranking, title="Rangliste", icon=":material/emoji_events:", default=True)
    page_scorecard_fn = st.Page(page_scorecard, title="Scorecard", icon=":material/table_view:")
    page_matrix_fn = st.Page(page_matrix, title="Matrix", icon=":material/scatter_plot:")
    page_import_fn = st.Page(page_import, title="Import", icon=":material/upload_file:")
    nav = st.navigation([page_ranking_fn, page_scorecard_fn, page_matrix_fn, page_import_fn])
    nav.run()


if __name__ == "__main__":
    main()
