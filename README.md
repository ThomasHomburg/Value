# Value-Screener

Automatisches Aktien-Screening nach Qualität und Bewertung (Buffett-Tracker, Ausbau).

## Web-App starten (Streamlit)

```bash
# Windows (im Projektordner, venv aktiv oder mit venv-Python):
.\.venv\Scripts\python.exe -m streamlit run app.py
# Linux/Mac:
python3 -m streamlit run app.py
```

Öffnet automatisch **http://localhost:8501** im Browser. Vier Seiten:

1. **Rangliste** — sortierbar nach jeder Spalte; **Standard-Sortierung: Kaufkandidat zuerst, dann MoS (Base) absteigend**. Spalten mit Quality / **Quality-Rang** / Value / Datenabdeckung; eindeutige Spalten mit Tooltip: FCF-Yield, **FCF-Yield nach SBC**, **FCF-Yield nach SBC 🥺**, **ROIC Ø** (Ø über verfügbare Jahre, aktuell 4), **ROIC letztes GJ**, ND/EBITDA (2 Stellen), EV/EBIT rel., **MoS (Base)**, **MoS Bear**, **MoS Bull**, **MoS Ø3J** / **MoS jüngstes GJ** / **MoS TTM Ø** / **MoS TTM** (MoS Base je Startwert-Modus nebeneinander; TTM = reiner TTM-Start ohne Ø), **MoS alt. ND** (MoS Base mit alternativer Nettoverschuldung), **Status** (zwei Stufen: **Kandidat** = MoS min ≥ 30 % + Quality ≥ 60 + Bear ≥ 80 % Kurs, **Beobachtung** = min < 30 %, aber bester Modus ≥ 30 % und Quality ≥ 60; Kandidat nennt den entscheidenden Modus), **Kandidat** (ja/nein + Begründung; MoS-Bedingung nutzt das Minimum der vier Startwert-MoS, Config `dcf.mos_min_mode`), **SEC**-Spalte (EDGAR-Abgleich sichtbar: ok / ⚠ Quellen weichen ab / n/a), Flags (inkl. `sec:abweichend` bei SEC-EDGAR-Abweichung > 5 %, `beobachten` bei Beobachtungsliste); Land als Kürzel (US, DE); alle Scores/Prozente auf 1 Nachkommastelle (Berechnung ungerundet); Banner einzeilig „LIVE · yfinance · 20 Ticker“; Filter nach Sektor / Land / Mindest-Score (Default: alle); Anzeige „x bewertet, y ausgeschlossen“; **ausgeschlossene Ticker als Tabelle mit Grund direkt unter der Rangliste** (nicht im Expander versteckt); Liste der durch Filter ausgeblendeten Ticker + Kaufkandidaten (Flag `kauf`) + Beobachtungsliste (Flag `beobachten`)
2. **Scorecard** — Gesamtscore, Quality, Value, **ROIC letztes GJ (mit Geschäftsjahr)**, Datenabdeckung; Block-Scores als horizontale Balken (jeder Balken mit deutschem Blocknamen und Wert beschriftet, Achse vollständig sichtbar, Blöcke ohne Daten als „n/a“ statt Lücke); Kriterien-Details (inkl. „Daten dünn (x J.)“); **ROIC mit Formel und Rohwerten**; **FCF-Yield roh + nach SBC**; ND/EBITDA; **DCF-Tabelle mit 3 Szenarien** (Bear/Base/Bull: Annahmen je Szenario, Jahre 1–10 mit FCF/Abzinsungsfaktor/Barwert, Terminal Value, **TV-Anteil am Unternehmenswert**, Nettoverschuldung **ohne Kundengelder**, Aktien, innerer Wert je Aktie, Kurs + MoS je Szenario, Kaufkandidat, **Basis „TTM bis YYYY-MM“ (Stichtag letztes Quartal) oder Geschäftsjahre**, **Startwert umschaltbar (Ø3J / jüngstes GJ / TTM Ø / TTM rein) mit Wert je Aktie und MoS je Szenario (Bear/Base/Bull) je Modus** (Einheit Start-FCF: Mrd. in Marktkap.-Währung), **Nettoverschuldung umschaltbar** (gemeldet vs. Schulden − (Cash + kurzfristige Anlagen), Config `dcf.net_debt_mode`) mit beiden MoS nebeneinander; **Letzte 4 Quartale (Cashflow, mit Stichtag)** — OCF, Capex, SBC, FCF − SBC je Quartal (Einheit Mrd. <Währung> in der Überschrift); **SEC-EDGAR-Abgleich** (US-Ticker: OCF/Capex/SBC gegen data.sec.gov/api/xbrl/companyfacts, Flag „Quellen weichen ab“ bei > 5 % Abweichung je Jahr; User-Agent mit E-Mail in config.yaml `sec.user_agent`); **Sensitivität** (MoS Base über Diskontsatz 8/9/10/11 % × Terminal Growth 2/2,5/3 % + „Innerer Wert je Aktie“-Tabelle); Referenz-Check UBER/NVDA/KO; **Expander ADBE & PYPL: Rohwerte FCF je Jahr, SBC je Jahr, Marktkapitalisierung**; **Expander ADBE & PYPL: Bilanz je Jahr — Cash, kurzfristige Anlagen, Finanzschulden, Nettoverschuldung + Kundengelder-Markierung**; 5-Jahres-Charts; Rohdaten mit Quelle; Sanity-Verstösse
3. **Matrix** — Streudiagramm Quality (x) vs. Value (y), Punkte mit Ticker beschriftet, Ziel-Quadrant oben rechts (beide ≥ Median) grün hervorgehoben, Tabelle der Kandidaten
4. **Import** — CSV-Upload (Spalte `ticker`) oder manuelle Ticker-Eingabe

**Datenquelle (Banner oben auf Seite 1) — Provider-Schnittstelle `data/providers/`:**
- **LIVE** — Standard: lädt automatisch `tickers.csv` (20 Ticker). Auswahl pro Ticker: US (ohne Suffix) → **FMP** (falls `FMP_API_KEY` gesetzt), alle anderen (`.DE`, `.AS`, `.PA`, `.CO`, `.L` …) → **yfinance** (kein API-Key nötig). Die Rangliste zeigt eine **Quelle**-Spalte; pro Ticker wird die Quelle im Log ausgegeben.
- **Import** — eigene Liste über Seite 3 (gleiches Provider-Routing)
- **DEMO** — nur Fallback, wenn kein Live-Ticker geladen werden kann (AAPL aus echten öffentlichen Daten + synthetische Firmen)

## v30/v31: candidate_mode (2 Regeln), 8 Quartale + YoY, Matrix nach Status
- **`dcf.candidate_mode`** (`min_all` Default = Minimum aus allen 4 Modi Ø3J/jüngstes GJ/TTM Ø/TTM; `min_recent2` = Minimum aus jüngstem GJ + TTM). Rangliste zeigt **„Status (alle Modi)“ und „Status (jüngste 2)“** nebeneinander; die aktive Regel (config) ist die Spalte „Status“. Beispiel live: ADBE → alle Modi = Beobachtung (21,0 %), jüngste 2 = Kandidat (36,3 %).
- **Quartalstabelle (Scorecard)**: 8 Quartale (4 aktuelle + 4 Vorjahresquartale) mit Spalte **„YoY je Quartal“** (FCF−SBC vs. Vorjahresquartal); Summenzeile nur über die 4 aktuellen Quartale (= TTM).
- **Matrix (Seite 3)**: Farbe nach **Status** (Kandidat grün, Beobachtung blau, sonst grau), x = Quality, **y = MoS (Base), Minimum der Modi, auf −100 % begrenzt**; Hilfslinien bei Quality 60 und MoS 30 % (aus `dcf.buy_quality_min` / `dcf.buy_margin_of_safety_min`); Ziel-Quadrant = Quality ≥ 60 UND MoS ≥ 30 % (grün hinterlegt); Tabelle darunter: Ticker, Status (beide Regeln), Quality, MoS je Modus.

## v29: Historie-Filter, EBITDA aus Cashflow, Quartals-Summenzeile
- **Harter Filter "Historie"**: zaehlt Jahre mit tatsaechlichen Werten (nicht Spalten; Kernkennzahlen revenue/ebit/net_income/ocf/equity ungleich NaN), Schwelle `filters.min_history_years` (4). Die Ausschlusstabelle zeigt die gezählten Jahre je Ticker ("Jahre mit Werten").
- **EBITDA = EBIT + Abschreibungen (D&A)** aus dem Cashflow-Statement (`Depreciation And Amortization`), NICHT das Yahoo/FMP-EBITDA-Feld (weicht teils ab, z. B. UBER FY2025: 6,99 vs. 6,31 Mrd. USD). Fallback: gemeldetes EBITDA, wenn kein D&A gemeldet. EBITDA < EBIT in mind. einem Jahr -> Flag `ebitda:unplausibel` und ND/EBITDA = n/a.
- **Quartalstabelle** (Scorecard): alle 4 Quartale + **Summenzeile** (muss dem TTM entsprechen).
- **SEC-Status in der Rangliste**: Spalte "SEC" (ok / ⚠ Quellen weichen ab / n/a) aus dem EDGAR-Abgleich (v26).

## Universumslader (Schritt 8)
- **S&P 500**: Liste von der Wikipedia-Tabelle (`pandas.read_html` auf „List of S&P 500 companies“, eigener User-Agent), Ergebnis als **`tickers_sp500.csv`** gespeichert (503 Ticker, ist im Repo).
- **STOXX 600**: Import per CSV (`tickers_stoxx600.csv`, Spalte `ticker`; nicht im Repo, .gitignore).
- **Abruf in Batches** (config `universe.batch_size`, Default 20) mit Pause (`batch_pause_seconds`), **Fortschrittsanzeige** (Streamlit-Progress + CLI-Log), **Wiederaufnahme nach Abbruch** (`universe.resume`, Cache `.universe_cache.json`), **Fehlerlog je Ticker** (yfinance-Fehler stoppen den Lauf nicht).
- UI: Seite 3 „Import“ → Abschnitt „Universumslader“. CLI: `python run_universe.py sp500 [--refresh]` bzw. `python run_universe.py stoxx600 [--csv PFAD]`.

**Scoring:** Quality- und Value-Score getrennt (`score_groups` in config.yaml); Gesamtscore = 0,75×Quality + 0,25×Value. n/a-Kriterien werden ausgeschlossen und die übrigen Gewichte renormalisiert; **Datenabdeckung** zeigt den Anteil bewerteter Gewichte. Alle Scores und Prozentwerte werden in der Anzeige auf 1 Nachkommastelle gerundet (Berechnung ungerundet). Der Value-Score nutzt **FCF-Yield nach SBC** (FCF − Aktienverguetung, Ø3J) 30 %, **MoS (Base)** aus dem DCF 40 % (voll ab 40 %, null bei ≤ 0 %) und **EV/EBIT rel.** 30 %. Quality-Schwellen verschaerft: ROIC voll ab 35 %, Umsatz-CAGR voll ab 15 %, FCF-Marge voll ab 30 %. Marktkapitalisierung mit Stichtag (Abrufdatum, ISO).

**Flags** (entdoppelt): Blöcke mit >30 % fehlenden Daten (`blk:duenn`); ROIC > 100 % → `kl.Kapital` (kleine/negative Kapitalbasis, z. B. Net Cash); Kriterien mit < 5 Jahren Daten → `duenn` (konfigurierbar: `data.thin_years`); **Kaufkandidat → `kauf`** (Quality ≥ 60, MoS Base ≥ 30 %, Bear ≥ 80 % Kurs); EBITDA < EBIT → `ebitda:unplausibel` (ND/EBITDA n/a).

## CLI (ohne Browser)

```bash
python3 run_ranking.py                     # tickers.csv über Provider (FMP/yfinance)
python3 run_ranking.py AAPL SAP.DE NOVO-B.CO
python3 run_ranking.py --tickers tickers_sp500.csv --out ranking_sp500.csv   # v32: Volllauf S&P 500 (Batches, Cache, CSV)
python3 check_providers.py                 # Rohwerte (FCF, Marktkap., ROIC) für AAPL SAP.DE ASML.AS NOVO-B.CO
```

Ohne `FMP_API_KEY` läuft der CLI ebenfalls live (US-Ticker dann über yfinance);
Demo-Daten nur als Fallback, wenn kein Live-Ticker geladen werden kann.

## Setup

```bash
python3 -m pip install requests pyyaml pytest streamlit yfinance
# FMP_API_KEY als Umgebungsvariable setzen (optional — nur für US-Ticker via FMP;
# wird nie committed, siehe .gitignore):
#   Windows PowerShell:  $env:FMP_API_KEY="dein_key"
#   Linux/Mac:           export FMP_API_KEY="dein_key"
# Live-Ticker: tickers.csv im Projektordner editieren (Spalte `ticker`, 20 voreingestellt)
```

## Provider-Schnittstelle (`data/providers/`)

Alle Provider liefern dasselbe normalisierte Schema (`TickerMetrics`: Wert, Einheit, Währung, Berichtsjahr, Quelle `source`):

- `fmp.py` — US-Ticker über die FMP-API (nur wenn `FMP_API_KEY` gesetzt)
- `yfinance_provider.py` — alle anderen (Yahoo Finance, ohne API-Key); Währung = Quote-Währung (SAP.DE → EUR, NOVO-B.CO → DKK)
- `base.py` — Auswahl: `providers.force` (Config) > Ticker-Suffix (`providers.suffix_map`) > US → FMP (falls Key) > `providers.default`

Historienfenster: 5 Jahre (`data.years`). Kriterien mit weniger Jahren → Flag **„Daten dünn"** (`data.thin_years`).

## Struktur

- `data/` — FMP-Loader, FX, Sanity-Check, Demo-Daten (`data/demo.py`), Provider (`data/providers/`), **TTM aus Quartalsdaten** (`data/ttm.py`, inkl. der 4 letzten Quartale einzeln mit Stichtag), **SEC-EDGAR-Abgleich** (`data/sec.py`, US-Ticker, `data.sec.gov/api/xbrl/companyfacts`)
- `scoring/` — Ausschlussfilter, Kriterien, Score, Pipeline
- `valuation/` — **DCF mit 3 Szenarien** (`valuation/dcf.py`: normalisierter FCF nach SBC Ø 3 J., Bear 0 % / Base min(CAGR, 6 %) / Bull min(CAGR×1,3, 10 %), Fade auf 2,5 % in J. 6–10, Diskontsatz 9 %, MoS Base, Kaufkandidat-Regel)
- `app.py` — Streamlit-UI
- `tests/` — pytest
- `config.yaml` — alle Schwellenwerte und Gewichte (keine Magic Numbers)

## Sektorregeln (Schritt 7, über das Feld Industry, nicht Sector)
- PYPL, Visa, Mastercard laufen als „Financial Services“ (Sector), sind aber **keine Banken** — die Regeln laufen daher über das GICS-**Industry**-Feld (`config.yaml` Block `sector_rules`).
- **Banken & Versicherer** (Banks*, Insurance*, Capital Markets, Asset Management, …): ROE, **P/B**, **Dividendenrendite** statt ROIC, FCF, ND/EBITDA (diese Kriterien werden n/a, die Finanz-Kriterien aktiviert).
- **Zykliker** (Rohstoffe, Chemie, Stahl, Auto, Energie, …): Gewinne über bis zu **7 Jahre normalisiert** (gleitender Ø, soweit Daten reichen); reicht die Historie nicht → Kriterium „Daten dünn“ + Flag `zyk:norm<7J`.
- **REITs** (Industry-Praefix `REIT - …`): **FFO-Hinweis** statt FCF-Yield (FFO je Aktie / Kurs; yfinance liefert i. d. R. kein FFO → Hinweis + n/a, nie Roh-FCF-Yield).

## ROIC / NOPAT (Steuersatz-Begrenzung)
- Effektiver Steuersatz = Steueraufwand / Vorsteuergewinn, **begrenzt auf 0–35 %** (`data.tax_rate_min/max`); außerhalb davon und bei **Vorsteuerverlust** gilt der **Normsteuersatz 21 %** (`data.tax_rate_norm`). Bei **EBIT ≤ 0 ist NOPAT = EBIT** (kein Steuervorteil im Verlustjahr) → immer NOPAT ≤ EBIT für EBIT > 0.
- Betrifft ROIC Ø, ROIC letztes GJ, ROIC-Chart und die Scorecard-Formelanzeige.

## DCF (Build-Schritt 6)

Unternehmenswert (EV) = SUMME FCF_t/(1+r)^t (t=1..10) + [FCF_10 x (1+g)/(r-g)]/(1+r)^10. **Innerer Wert = EV − Nettoverschuldung ohne Kundengelder** (Kundengelder, z. B. PayPal Deposit Liabilities, sitzen in Cash und werden hinzuaddiert); Wert je Aktie = Innerer Wert / verwässerte Aktien. Basis: **normalisierter FCF nach SBC** — umschaltbar: **Ø letzte 3 GJ / jüngstes GJ / TTM Ø / TTM rein** (TTM Ø = Ø TTM + 2 nicht überlappende GJ; TTM rein = reiner TTM-Start, Summe letzte 4 Quartale, ohne Ø; Config `dcf.fcf_mode`, Scorecard zeigt MoS Base für alle Modi nebeneinander). **Nettoverschuldung umschaltbar** (Config `dcf.net_debt_mode`): `reported` (gemeldet) oder `incl_sti` (Finanzschulden − (Cash + kurzfristige Anlagen)); beide Varianten werden gerechnet, die aktive per Config, die andere als `net_debt_alt` / `mos_base_alt` nebeneinander angezeigt. Wachstum: Bear 0 %, Base = min(Umsatz-CAGR, 6 %), Bull = min(CAGR×1,3, 10 %); Jahre 6–10 linear auf 2,5 %. **MoS (Base)** = 1 − Kurs / Wert je Aktie (Base) → Spalte in der Rangliste. **Kaufkandidat** (Flag `kauf`): Quality ≥ 60 UND MoS ≥ 30 % UND Bear-Szenario ≥ 80 % des Kurses — das verwendete MoS ist das **Minimum** der vier Startwert-MoS (Config `dcf.mos_min_mode`: `min` | `avg3` | `latest` | `ttm` | `ttm_only` | `auto`); beim Kandidat wird der entscheidende Modus angezeigt. **Beobachtung** (Flag `beobachten`): Minimum < 30 %, aber der **beste** Modus ≥ 30 % (`dcf.watch_margin_of_safety_min`) und Quality ≥ 60. **SEC-EDGAR-Abgleich** (US-Ticker, Config-Block `sec`): OCF/Capex/SBC je Jahr gegen `data.sec.gov/api/xbrl/companyfacts`, Abweichung > `sec.tolerance` (5 %) → Flag `sec:abweichend`. Alle Parameter in `config.yaml` (Block `dcf` bzw. `sec`).

## Einheiten-Konvention (wichtig)

FMP liefert Statements und `profile.mktCap` in **absoluten** Beträgen (z. B. AAPL
Umsatz = 391035000000 USD). Alle Kennzahlen bleiben absolut; Schwellen in
`config.yaml` mit `_usd` sind absolute USD (nicht Mio.). Ein früherer Bug
(Marktkap. fälschlich /1e6 → FCF-Yield ×1.000.000) ist durch
`tests/test_aapl_units.py` und den Sanity-Check (`data/sanity.py`) abgesichert.

## Build-Status

- [x] 1. Loader für einen Ticker; Kennzahlen von 3 Referenzunternehmen gegengeprüft
- [x] 2. SQLite-Cache (FX-Raten) — API-Cache folgt
- [x] 3. Ausschlussfilter und Scoring nach `config.yaml`
- [x] 4. Streamlit-Rangliste
- [x] 5. Scorecard-Detailseite (Block-Scores, ROIC-Rohwerte, Charts, Rohdaten, „Daten dünn")
- [x] Provider-Schnittstelle: FMP (US) + yfinance (alle anderen), 5-Jahres-Fenster, Quelle pro Ticker
- [x] Quality/Value getrennt, Renormalisierung bei n/a, Datenabdeckung, 1 Nachkommastelle
- [x] Matrix-Seite (Quality vs. Value, Ziel-Quadrant)
- [x] Formel-Anzeige ROIC 5J / FCF-Yield / ND/EBITDA mit Rohwerten (inkl. Referenz UBER/NVDA/KO)
- [x] FCF-Yield nach SBC (FCF − Aktienverguetung) als Value-Kriterium
- [x] 6. DCF-Modul mit 3 Szenarien (Bear/Base/Bull), normalisierter FCF nach SBC (Ø 3 J.), MoS Base in der Rangliste, Kaufkandidaten (Quality ≥ 60, MoS ≥ 30 %, Bear ≥ 80 % Kurs)
- [ ] 7. Sektor-Sonderregeln
- [ ] 8. Universum erweitern, Batch-Lauf

## Tests

```bash
python3 -m pytest tests/ -v
```
