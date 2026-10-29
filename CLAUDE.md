# Value-Screener (Buffett-Tracker, Ausbau)

## Ziel
Tool, das ein Aktienuniversum automatisch nach Qualitaet und Bewertung scort und unterbewertete Unternehmen als Rangliste mit Detail-Scorecard ausgibt.

## Stack
- Python 3.11+, pandas, requests, SQLite (Cache), Streamlit (UI), pytest
- Datenquelle primaer: Financial Modeling Prep (FMP) API, Key in `.env` (`FMP_API_KEY`), nie committen
- Fallback: CSV-Import (bestehendes Format des Trackers) und yfinance fuer Prototyping
- Struktur: `data/` (Loader, Cache), `scoring/` (Kriterien, Score), `valuation/` (DCF, Multiples), `app.py` (Streamlit), `tests/`

## Arbeitsregeln fuer Claude Code
- Immer nur einen Baustein pro Schritt umsetzen, danach Test und kurze Zusammenfassung
- Keine Magic Numbers: alle Schwellenwerte und Gewichte in `config.yaml`
- Jede Kennzahl mit Einheit, Waehrung und Berichtsjahr speichern
- Fehlende Daten als `NaN` behandeln, nie mit 0 fuellen; im Score als "n/a" ausweisen
- Alle API-Antworten in SQLite cachen (TTL 24 h), um Rate Limits zu schonen
- Bei Unsicherheit ueber Berechnung: Formel im Code-Kommentar dokumentieren
- Nach jeder Aenderung `python -m compileall .` und `pytest` ausfuehren und das Ergebnis zeigen, bevor du Schritt als erledigt meldest.
- **Keine Emojis im Code.** Icons nur als Material-Shortcodes (`:material/...:`), z. B. `:material/emoji_events:`, `:material/table_view:`, `:material/scatter_plot:`, `:material/upload_file:`, `:material/trending_up:`. Niemals Emojis als `icon=`/`page_icon=`-Wert und keine ASCII-Platzhalter-Tags wie `[RANK]`/`[CHART]` (verursachen StreamlitAPIException). In Fliestexten statt Emojis Text-Tags wie `[LIVE]`, `[DEMO]`, `[!]`, `[KAUF]` verwenden.
- **Dateien immer als UTF-8 lesen und schreiben** (`open(..., encoding="utf-8")`), nie implizites Encoding; vor dem Schreiben sicherstellen, dass der Inhalt UTF-8-kodierbar ist.
- **Dateien fuer Google-Drive-Upload immer ASCII-only** (keine Umlaute, keine Emojis, keine typografischen Anfuehrungszeichen). Vor dem Upload auf Nicht-ASCII-Zeichen pruefen; Umlaute als ae/oe/ue/ss, Durchschnitts-O als O, Multiplikationszeichen als x, Emojis als [OK]/[LIVE]/[NOTE]/[DEMO] ersetzen.
- **app.py wird fuer den Drive-Upload in zwei Dateien gesplittet**: `app_part1.py` (Imports, Laden, Seite 1 Rangliste, Seite 2 Scorecard bis `sbc_detail_section()`) und `app_part2.py` (ab `def _formula_block` bis Ende). Lokal zusammenfuegen mit `cat app_part1.py app_part2.py > app.py` (Linux/Mac) bzw. `copy app_part1.py+app_part2.py app.py` (Windows). Der Split muss byte-exakt sein: `cat part1 part2` == ASCII-Version von app.py, geprueft mit `python -m py_compile`.
- SyntaxError-Diagnose: bei "unterminated string/triple-quoted string" zuerst die gemeldeten Zeilen mit Zeilennummern zeigen, dann die genaue Ursache finden (ungeschlossenes Triple-Quote, vierfaches Anfuehrungszeichen, typografische Quotes), dann `python -m compileall .` und `pytest` ausfuehren und die Ausgabe zeigen.
- **Round-trip-Verifikation nach jedem Drive-Upload**: jede hochgeladene Datei sofort zurueckladen (Download) und gegen die lokale Datei pruefen (`py_compile` fuer .py-Dateien, Byte-/Hash-Vergleich). Erst wenn die zurueckgeladene Datei fehlerfrei kompiliert und byte-identisch ist, gilt der Upload als erledigt. Hintergrund: fruehere Uploads wurden auf dem Transportweg beschaedigt (einzelne Bit-Flips, z. B. `"` -> Leerzeichen, `(` -> `*`), was auf dem Zielrechner zu SyntaxError fuehrt.

## Kennzahlen (je Unternehmen, 10 Jahre, falls verfuegbar)
Umsatz, EBIT, Nettogewinn, Operating Cashflow, Capex, FCF (= OCF - Capex), Eigenkapital, Nettoverschuldung, EBITDA, Zinsaufwand, Aktienanzahl (verwaessert), investiertes Kapital, Marktkapitalisierung, Enterprise Value

## Scoring (0-100)

| Block | Gewicht | Kriterium | Volle Punkte | Null Punkte |
|---|---|---|---|---|
| Rentabilitaet | 25 % | ROIC (O 5 J.) | >= 15 % | <= 6 % |
| Rentabilitaet | 10 % | ROE (O 5 J.) | >= 18 % | <= 8 % |
| Stabilitaet | 10 % | Nettoverschuldung/EBITDA | <= 1,0 | >= 4,0 |
| Stabilitaet | 5 % | Zinsdeckung (EBIT/Zinsen) | >= 10 | <= 3 |
| Cashflow | 10 % | Jahre mit FCF > 0 (von 10) | 10 | <= 5 |
| Cashflow | 5 % | FCF-Marge (O 5 J.) | >= 12 % | <= 3 % |
| Moat | 5 % | Bruttomarge: Trend (Steigung 10 J.) | steigend | stark fallend |
| Moat | 5 % | Umsatz-CAGR 5 J. | >= 6 % | <= 0 % |
| Bewertung | 15 % | FCF-Yield (FCF O 3 J. / Marktkap.) | >= 8 % | <= 2 % |
| Bewertung | 10 % | EV/EBIT vs. eigener 10-J.-Median | <= 60 % davon | >= 120 % davon |

- Lineare Interpolation zwischen Null- und Volle-Punkte-Schwelle
- Gesamtscore = gewichtete Summe; Bloecke mit > 30 % fehlenden Daten werden markiert

## Harte Ausschlussfilter (vor dem Scoring)
- Marktkapitalisierung < 500 Mio. USD/EUR
- Weniger als 5 Jahre Datenhistorie
- Negativer O-FCF ueber 5 Jahre
- Eigenkapital negativ
- Umsatz-CAGR 5 J. < -3 % (Value-Trap-Filter)

## Sektor-Sonderregeln
- **Banken/Versicherer**: ROIC, EV/EBIT, FCF ersetzen durch ROE, P/B, Dividendenrendite, CET1 (falls verfuegbar)
- **Rohstoffe/Zykliker**: Gewinne ueber 7-Jahres-Durchschnitt normalisieren, KGV auf Basis dieses Durchschnitts
- **Immobilien/REITs**: FFO statt FCF
- Sektor ueber FMP-Feld `sector` bestimmen; Config-Block je Sektor in `config.yaml`

## Innerer Wert (DCF, 3 Szenarien)
- Basis: normalisierter FCF = O der letzten 3 Jahre
- Wachstum Jahre 1-5: Bear 0 %, Base = min(Umsatz-CAGR 5 J., 6 %), Bull = min(CAGR x 1,3; 10 %)
- Wachstum Jahre 6-10: linear abnehmend auf 2,5 %
- Terminal Growth: 2,5 %; Diskontsatz: 9 % (Config, bei Zyklikern 10 %)
- Ausgabe: innerer Wert je Aktie je Szenario, Margin of Safety = 1 - Kurs / innerer Wert (Base)
- **Kaufkandidat**: Gesamtscore >= 70 UND Margin of Safety (Base) >= 30 % UND Bear-Szenario >= Kurs x 0,8

## UI (Streamlit)
- **Seite 1 Rangliste**: sortierbare Tabelle (Ticker, Name, Sektor, Score, FCF-Yield, Margin of Safety, Flags), Filter nach Sektor/Land/Score
- **Seite 2 Scorecard**: Block-Scores als Balken, 10-J.-Charts (Umsatz, FCF-Marge, ROIC, Verschuldung), DCF-Tabelle mit 3 Szenarien, Liste der Rohdaten mit Quelle und Datum
- **Seite 3 Import**: CSV-Upload und manuelle Eingabe als Fallback

## Build-Reihenfolge (Definition of Done je Schritt)
1. Loader fuer einen Ticker; Test: Kennzahlen von 3 Referenzunternehmen manuell gegengeprueft
2. SQLite-Cache plus Loader fuer Ticker-Liste (CSV mit Tickern)
3. Ausschlussfilter und Scoring nach `config.yaml`; Unit-Tests je Kriterium
4. Streamlit-Rangliste
5. Scorecard-Detailseite
6. DCF-Modul mit Szenarien; Test mit handgerechnetem Beispiel
7. Sektor-Sonderregeln
8. Universum erweitern (STOXX 600, S&P 500), Batch-Lauf mit Fortschrittsanzeige

## Validierung
- Pro Release 3 Unternehmen von Hand nachrechnen (ROIC, FCF-Yield, DCF) und Abweichung < 2 % sicherstellen
- Logging: Datenluecken, API-Fehler, ausgeschlossene Ticker mit Grund
- Look-ahead-Hinweis: Historische Auswertungen nur mit zum Stichtag veroeffentlichten Daten
