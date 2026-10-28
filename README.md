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

1. **Rangliste** — sortierbar nach jeder Spalte; **Standard-Sortierung: Kaufkandidat zuerst, dann MoS (Base) absteigend**. Spalten mit Quality / **Quality-Rang** / Value / Datenabdeckung; eindeutige Spalten mit Tooltip: FCF-Yield, **FCF-Yield nach SBC**, **FCF-Yield nach SBC 🥺**, **ROIC Ø** (Ø über verfügbare Jahre, aktuell 4), **ROIC letztes GJ**, ND/EBITDA (2 Stellen), EV/EBIT rel., **MoS (Base)**, **MoS Bear**, **MoS Bull**, **Kandidat** (ja/nein + Begründung, welche der drei Bedingungen fehlt), Flags; Land als Kürzel (US, DE); alle Scores/Prozente auf 1 Nachkommastelle (Berechnung ungerundet); Banner einzeilig „LIVE · yfinance · 20 Ticker“; Filter nach Sektor / Land / Mindest-Score (Default: alle); Anzeige „x bewertet, y ausgeschlossen“ + Liste der durch Filter ausgeblendeten Ticker + Kaufkandidaten (Flag `kauf`)
2. **Scorecard** — Gesamtscore, Quality, Value, **ROIC letztes GJ (mit Geschäftsjahr)**, Datenabdeckung; Block-Scores als horizontale Balken (jeder Balken mit deutschem Blocknamen und Wert beschriftet, Achse vollständig sichtbar, Blöcke ohne Daten als „n/a“ statt Lücke); Kriterien-Details (inkl. „Daten dünn (x J.)“); **ROIC mit Formel und Rohwerten**; **FCF-Yield roh + nach SBC**; ND/EBITDA; **DCF-Tabelle mit 3 Szenarien** (Bear/Base/Bull: Annahmen je Szenario, Jahre 1–10 mit FCF/Abzinsungsfaktor/Barwert, Terminal Value, **TV-Anteil am Unternehmenswert**, Nettoverschuldung, Aktien, innerer Wert je Aktie, Kurs + MoS je Szenario, Kaufkandidat, **Basis „TTM bis YYYY-MM“ (Stichtag letztes Quartal) oder Geschäftsjahre**); **Sensitivität** (MoS Base über Diskontsatz 8/9/10/11 % × Terminal Growth 2/2,5/3 % + „Innerer Wert je Aktie“-Tabelle); Referenz-Check UBER/NVDA/KO; **Expander ADBE & PYPL: Rohwerte FCF je Jahr, SBC je Jahr, Marktkapitalisierung**; **Expander PYPL: Cash, Finanzschulden, Nettoverschuldung, OCF, Capex (4 J.) + Kundengelder-Markierung**; 5-Jahres-Charts; Rohdaten mit Quelle; Sanity-Verstösse
3. **Matrix** — Streudiagramm Quality (x) vs. Value (y), Punkte mit Ticker beschriftet, Ziel-Quadrant oben rechts (beide ≥ Median) grün hervorgehoben, Tabelle der Kandidaten
4. **Import** — CSV-Upload (Spalte `ticker`) oder manuelle Ticker-Eingabe

**Datenquelle (Banner oben auf Seite 1) — Provider-Schnittstelle `data/providers/`:**
- **LIVE** — Standard: lädt automatisch `tickers.csv` (20 Ticker). Auswahl pro Ticker: US (ohne Suffix) → **FMP** (falls `FMP_API_KEY` gesetzt), alle anderen (`.DE`, `.AS`, `.PA`, `.CO`, `.L` …) → **yfinance** (kein API-Key nötig). Die Rangliste zeigt eine **Quelle**-Spalte; pro Ticker wird die Quelle im Log ausgegeben.
- **Import** — eigene Liste über Seite 3 (gleiches Provider-Routing)
- **DEMO** — nur Fallback, wenn kein Live-Ticker geladen werden kann (AAPL aus echten öffentlichen Daten + synthetische Firmen)

**Scoring:** Quality- und Value-Score getrennt (`score_groups` in config.yaml); Gesamtscore = 0,75×Quality + 0,25×Value. n/a-Kriterien werden ausgeschlossen und die übrigen Gewichte renormalisiert; **Datenabdeckung** zeigt den Anteil bewerteter Gewichte. Alle Scores und Prozentwerte werden in der Anzeige auf 1 Nachkommastelle gerundet (Berechnung ungerundet). Der Value-Score nutzt **FCF-Yield nach SBC** (FCF − Aktienverguetung, Ø3J) 30 %, **MoS (Base)** aus dem DCF 40 % (voll ab 40 %, null bei ≤ 0 %) und **EV/EBIT rel.** 30 %. Quality-Schwellen verschaerft: ROIC voll ab 35 %, Umsatz-CAGR voll ab 15 %, FCF-Marge voll ab 30 %. Marktkapitalisierung mit Stichtag (Abrufdatum, ISO).

**Flags** (entdoppelt): Blöcke mit >30 % fehlenden Daten (`blk:duenn`); ROIC > 100 % → `kl.Kapital` (kleine/negative Kapitalbasis, z. B. Net Cash); Kriterien mit < 5 Jahren Daten → `duenn` (konfigurierbar: `data.thin_years`); **Kaufkandidat → `kauf`** (Score ≥ 70, MoS Base ≥ 30 %, Bear ≥ 80 % Kurs).

## CLI (ohne Browser)

```bash
python3 run_ranking.py                     # tickers.csv über Provider (FMP/yfinance)
python3 run_ranking.py AAPL SAP.DE NOVO-B.CO
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

- `data/` — FMP-Loader, FX, Sanity-Check, Demo-Daten (`data/demo.py`), Provider (`data/providers/`), **TTM aus Quartalsdaten** (`data/ttm.py`)
- `scoring/` — Ausschlussfilter, Kriterien, Score, Pipeline
- `valuation/` — **DCF mit 3 Szenarien** (`valuation/dcf.py`: normalisierter FCF nach SBC Ø 3 J., Bear 0 % / Base min(CAGR, 6 %) / Bull min(CAGR×1,3, 10 %), Fade auf 2,5 % in J. 6–10, Diskontsatz 9 %, MoS Base, Kaufkandidat-Regel)
- `app.py` — Streamlit-UI
- `tests/` — pytest
- `config.yaml` — alle Schwellenwerte und Gewichte (keine Magic Numbers)

## DCF (Build-Schritt 6)

Innerer Wert je Aktie = SUMME FCF_t/(1+r)^t (t=1..10) + [FCF_10 x (1+g)/(r-g)]/(1+r)^10, dividiert durch verwässerte Aktien. Basis: **normalisierter FCF nach SBC** (Ø letzte 3 Jahre). Wachstum: Bear 0 %, Base = min(Umsatz-CAGR, 6 %), Bull = min(CAGR×1,3, 10 %); Jahre 6–10 linear auf 2,5 %. **MoS (Base)** = 1 − Kurs / Wert je Aktie (Base) → Spalte in der Rangliste. **Kaufkandidat** (Flag `kauf`): Score ≥ 70 UND MoS Base ≥ 30 % UND Bear-Szenario ≥ 80 % des Kurses. Alle Parameter in `config.yaml` (Block `dcf`).

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
- [x] 6. DCF-Modul mit 3 Szenarien (Bear/Base/Bull), normalisierter FCF nach SBC (Ø 3 J.), MoS Base in der Rangliste, Kaufkandidaten (Score ≥ 70, MoS ≥ 30 %, Bear ≥ 80 % Kurs)
- [ ] 7. Sektor-Sonderregeln
- [ ] 8. Universum erweitern, Batch-Lauf

## Tests

```bash
python3 -m pytest tests/ -v
```
