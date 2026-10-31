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
- Basis: normalisierter FCF nach SBC = O der letzten 3 Jahre (umschaltbar: jungstes GJ / TTM O / TTM rein; Config `dcf.fcf_mode`, TTM O = O TTM + 2 nicht uberlappende GJ, TTM rein = Summe letzte 4 Quartale ohne O)
- Wachstum Jahre 1-5 (v37): CAGR >= 0 -> Bear 0 %, Base = min(Umsatz-CAGR, 6 %), Bull = min(CAGR x 1,3; 10 %); CAGR < 0 -> Base = CAGR, Bear = CAGR - `dcf.bear_negative_spread` (3 pp), Bull = 0 %
- Wachstum Jahre 6-10: linear abnehmend auf 2,5 %
- Terminal Growth: 2,5 %; Diskontsatz: 9 % (Config, bei Zyklikern 10 %)
- Innerer Wert (Equity) = Unternehmenswert (Barwert FCFs + Barwert TV) - Nettoverschuldung OHNE Kundengelder (Kundengelder z. B. PYPL Deposit Liabilities sitzen in Cash -> werden hinzuaddiert)
- Ausgabe: innerer Wert je Aktie je Szenario (Bear/Base/Bull) JE STARTWERT-MODUS in der Scorecard-Modus-Tabelle, Margin of Safety = 1 - Kurs / innerer Wert (Base)
- **Nettoverschuldung umschaltbar** (Config `dcf.net_debt_mode`): `reported` (gemeldet) oder `incl_sti` (Finanzschulden - (Cash + kurzfristige Anlagen)); beide Varianten werden gerechnet, die aktive per Config, die andere als `net_debt_alt` / `mos_base_alt`
- **MoS je Startwert-Modus**: Rangliste zeigt MoS (Base) fur O3J / jungstes GJ / TTM O / TTM rein nebeneinander; Kandidatenregel nutzt das Minimum der vier (Config `dcf.mos_min_mode`)
- **Letzte 4 Quartale**: TtmResult.quarters (neuestes zuerst) mit OCF/Capex/SBC/FCF-SBC je Quartal + Stichtag (Scorecard-Anzeige)
- **SEC-EDGAR-Abgleich** (`data/sec.py`, US-Ticker): OCF/Capex/SBC je Jahr gegen data.sec.gov/api/xbrl/companyfacts; Abweichung > `sec.tolerance` (5 %) -> Flag `sec:abweichend`. User-Agent MIT E-Mail (Config `sec.user_agent`, Platzhalter)
- **ROIC/NOPAT**: Steuersatz = Steuer/Vorsteuergewinn, begrenzt 0-35 % (`data.tax_rate_min/max`);
  ausserhalb/Vorsteuerverlust -> Normsteuersatz 21 % (`data.tax_rate_norm`); EBIT <= 0 -> NOPAT = EBIT
- **v36 Datenluecken nur fuer gelieferte Jahre**: Datenqualitaet meldet ein Jahr nur, wenn der Provider eine Statement-Spalte liefert (`fiscal_ends` gepflegt UND mind. eine Kennzahl aus revenue/equity/ocf vorhanden); die leere 5. Spalte nicht.
- **v36 Capex-Definition** (`sec.capex_check`: tolerance 0.20, min_years 2): SEC-Abweichung des Capex in >= min_years Jahren > tolerance -> `pruefen_capex=True`, `dcf.is_buy=False`, Flag `capex:pruefen`, Status `"Pruefen (Capex-Definition)"` (alle 3 Status-Spalten; Auswertung NACH sec_check, Status-Ueberschreibung danach). Row: `status_pruefen_capex`, `capex_dev_years`. Live: CAT/DE/MA/BIIB (Yahoo capitalExpenditure vs. SEC PaymentsToAcquirePropertyPlantAndEquipment).
- **v36 Zykliker-Cap**: `zyk_unnorm` = cyclicals mit norm_years < normalize_years; Status Kandidat/Beobachtung -> `"Beobachtung (nicht normalisiert)"`, `is_buy=False`. Row `zyk_unnorm`.
- **v36 Robustheit**: `mos_robust` = MoS Base mit `dcf.robust_discount_rate` (0.10) im aktiven fcf_mode (compute_dcf mit angepasstem discount_rate); Row `mos_robust`/`mos_robust_rate`; app.py Spalte `MoS bei 10%` + Status-Zusatz `(robust)` wenn >= `dcf.buy_margin_of_safety_min` (und nicht special).
- **v36 Bilanz-Konsistenz** (`consistency.net_debt_mcap_share` 0.05): neuestes Jahr mit net_debt/_total_debt/_cash; |ND - (Debt-Cash)| > 5 % Marktkap. -> `nd_inconsistent`, Flag `ND != Schulden - Cash`, dq-Eintrag. Row `nd_inconsistent`. Test mit ADBE 2025.
- **v36 Batch-Runner**: `testlauf_run.py` laedt in Batches (universe.batch_size=20, Pause batch_pause_seconds, Fortschritt im Log, Fehlerlog je Ticker); 28 Ticker (25 Seed 42 + PYPL, V, MA). `run_ranking.py --tickers` nutzt denselben Mechanismus seit v32.
- **v37 Szenario-Wachstum bei CAGR < 0** (`dcf.bear_negative_spread` 0.03): CAGR >= 0 unveraendert (Bear 0 %, Base min(CAGR, cap), Bull min(CAGR*mult, bull_cap)); CAGR < 0 -> Base = CAGR, Bear = CAGR - 3 pp, Bull = 0 %. `DcfResult.scenario_growth` = {bear, base, bull} mit den tatsaechlichen Raten; app.py Erklaertext zeigt sie. Test: Wert/Aktie Bear <= Base <= Bull fuer CAGR -10/0/4/12 %.
- **v37 Quality-Abdeckung** (`score_groups.min_coverage_quality` gilt NUR fuer Quality-Bloecke): `score_ticker` berechnet `quality_coverage` = Anteil bewerteter Gewichte an den Quality-Bloecken (profitability/stability/cashflow/moat); Quality n/a nur wenn `quality_coverage` < 0.70 -- Value-Luecken beeinflussen Quality NICHT. Row `quality_coverage`; app.py Quality-Spalte nutzt sie; testlauf_25.csv Spalte `Quality-Abdeckung`. DOW liefert damit wieder einen Quality-Score (Test, DOW-aehnlich ohne Marktkap.).
- **v37 Capex-Regel als OCF-Anteil** (`sec.capex_check`: `ocf_share` 0.10, `min_years` 2; `tolerance` entfaellt): Pruefstatus nur wenn |Yahoo-Capex - SEC-Capex| in >= min_years Jahren > 10 % des OCF. Pipeline baut `ocf_by_fy`, setzt `diff_ocf_share` je Abweichung. `format_sec_detail(deviations, ocf_by_fy=...)`: Capex-Detail mit Yahoo/SEC in Mrd. USD + Diff in Mrd. und % des OCF je Jahr. Tests: MA ohne, CAT + DE mit Pruefstatus (Mock), live Zahlen MA/CAT/DE.
- **v37 Testlauf 28 Ticker** (25 Seed 42 + PYPL, V, MA): 28 bewertet / 0 ausgeschlossen / 0 Fehler; testlauf_25.csv + testlauf_fehler.txt neu (v37: + Quality-Abdeckung). CAT und DE mit `Pruefen (Capex-Definition)`, MA ohne (Diff 4-6 % des OCF). `run_ranking.py --help`: Batch-Runner fertig (Batches, Pause, Resume via Cache, Fehlerlog, CSV). Kein Volllauf.
- **v38 (1) Negatives Eigenkapital**: `filters.exclusion.negative_equity: false` (Default) -- EK < 0 schliesst NICHT mehr aus; Ticker wird normal bewertet mit Flag `ek_negativ` (pipeline, neuestes Jahr). `true` stellt den alten Ausschluss wieder her. `data/metrics.py`: `roe()` NaN bei EK <= 0 (Jahr n/a, nicht 0 Punkte; calc_roe_avg5 zaehlt nur EK>0-Jahre); `roic()` nutzt bei EK <= 0 `invested_capital_ek_le0()` = Schulden + EK als Nenner (auch <= 0 -> NaN) -- gilt fuer roic_avg5 UND roic_latest (Row). Kandidatenregel/Abdeckung unveraendert. Tests: synthetisches EK-negativ + Schalter true; live MCD/PM/SBUX/ORLY/LOW bewertet mit ek_negativ, ROE n/a in allen EK<0-Jahren, ROIC mit Schulden+EK.
- **v38 (2) Diagnose Szenario-Reihenfolge**: `python rohwerte_check.py RDDT STT` (CLI-Argumente ab v38) -- bei RDDT (CAGR +48.9 %, Base/Bull gecappt 6 %/10 %) ist Bear <= Base <= Bull in ALLEN Modi erfuellt (Test um CAGR 30/60/120 % + kleiner positiver Start-FCF erweitert, gruen). Ursache bei RDDT/STT liegt NICHT in der Szenario-Logik, sondern im Start-FCF je Modus (RDDT avg3/ttm negativ -> fcf_le0 -> n/a; STT ist Asset Management -> Sonderregel).
- **v38 (3) Asset Management -> Sonderregel**: `sector_rules.groups.special.industry_patterns` ergaenzt um `"Asset Management"` (NTRS, STT, AMP, BLK, BX, KKR -> special, Status `Sonderregel noetig`). `Financial Data & Stock Exchanges` (CME, ICE, SPGI, MCO, ...) bleibt Normalmodell (financials). Tests parametrisiert.
- **v38 (4) Mini-CSV Testlauf**: `python run_ranking.py --tickers ticker_test_v38.csv --out ranking_test_v38.csv` (18 Ticker: MCD, PM, SBUX, ORLY, LOW, RDDT, STT, NTRS, AMP, BLK, CME, DECK, PYPL, XOM, DOW, MA, CAT, DE) -> 18 bewertet / 0 ausgeschlossen / 0 Fehler; Kandidaten DECK, PYPL; STT/NTRS/AMP/BLK `Sonderregel noetig`; CME Normalmodell; CAT/DE `Pruefen (Capex-Definition)`; MA ohne. Kein Volllauf.
- **v38 --tickers-Datei fehlt/leer**: `run_ranking.py --tickers X` mit nicht existierender Datei -> `Fehler: Ticker-Datei nicht gefunden: X` + Exit 1; 0 Ticker gelesen (fehlende Spalte 'ticker' oder leer) -> `Fehler: 0 Ticker gelesen aus X; Spalte 'ticker' pruefen` + Exit 1; in beiden Faellen wird KEINE leere Ergebnis-CSV geschrieben (Abbruch vor _write_ranking_csv). Tests in tests/test_v38_tickers.py (4, inkl. Gegenprobe mit gueltiger Datei).
- **v35 Sektor-Sonderregel**: `sector_rules.groups.special.industry_patterns` (fnmatch, case-insensitive: `Banks - *`, `Capital Markets`, `Insurance - *`, `REIT - *`, `Utilities - *`) -> Gruppe `special` (Vorrang vor reits/financials). Pipeline: DCF/FCF-Yield NICHT berechnet (DcfResult mit NaN, `fcf_mode='n/a (Sonderregel)'`), MoS NaN -> app.py `"n/a (Sonderregel)"`, Status `"Sonderregel noetig"` (alle 3 Status-Spalten), `is_buy=False`, Row `sector_special=True`. criteria.py: `_special()` -> roic_avg5/net_debt_ebitda/fcf_positive_years/fcf_margin_avg5/fcf_yield_sbc_avg3/mos_base n/a; `active_criteria` special -> nur Standard-Kriterien. PYPL/V/MA (Credit Services) bleiben `standard` (Test). Quality n/a bei Coverage < `score_groups.min_coverage_quality` (0.70, score.py).
- **v35 Pruefstatus-Bedingung**: `pruefen_sbc` nur wenn `sbc_missing_all` UND Quality >= `dcf.buy_quality_min` UND `mos_rule` >= `dcf.buy_margin_of_safety_min` (sonst normaler Status); `status_pruefen_sbc` = pruefen_sbc (nicht mehr sbc_missing_all).
- **v35 SBC-Fallback SEC**: `data/sec.py::sec_sbc_fallback_all(m, cfg)` laedt companyfacts einmal, ergaenzt `stock_based_compensation` + `fcf_sbc` = fcf - SEC-SBC fuer Jahre ohne Yahoo-SBC (nur US-Ticker, sec.enabled); Pipeline speichert Quellen in `sbc_sec_sources`, Flag mit Quelle; passiert VOR compute_criteria.
- **v35 SEC-Detail**: `format_sec_detail(deviations)` -> `"OCF FY2024 +8.0%; Capex FY2023 -10.0%"`; Pipeline filtert deviations > `sec.tolerance` -> Row `sec_detail`; app.py SEC-Spalte zeigt Detail in der Zelle; run_ranking.py CSV-Spalte `sec_detail` (+ `sector_group`). Tests: CAT (OCF FY2024) und DE (Capex FY2023), monkeypatchtes `_cik_for_ticker`/`_fetch_companyfacts`.
- **v35 Datenqualitaet**: `out["data_quality"]` je Ticker (Datenluecken je FY, Abdeckung < 70 %, SEC-Abweichung, Sektor-Sonderregel, Pruefstatus, EBITDA/TTM unplausibel); testlauf_fehler.txt enthaelt Fehler + Datenqualitaet je Ticker.
- **v35 Testlauf**: `testlauf_run.py` (25 Ticker Seed 42, live) schreibt `testlauf_25.csv` (Spalten inkl. Industry-Gruppe + SEC-Detail) und `testlauf_fehler.txt`.
- **v34 SBC-Regel**: `sbc_missing_all` = kein `fcf_sbc` in ALLEN Jahren UND kein TTM-fcf_sbc -> Status `Prüfen (SBC fehlt)` (alle drei Status-Spalten), `is_buy=False` (nie Kandidat), Flag `SBC n/a (ohne SBC)`; Row `status_pruefen_sbc`. DCF/FCF laufen trotzdem (Roh-FCF-Fallback v33), aber `fcf_yield_sbc_avg3` bleibt n/a (Roh-FCF-Yield fliesst NICHT in Value-Score).
- **v34 Kandidaten-Labels**: app.py "Status (alle Modi)" -> `Kandidat (streng)`, "Status (juengste 2)" -> `Kandidat (aktuell)`; aktive Spalte je `dcf.candidate_mode`.
- **v34 MoS < -100 %**: app.py `_fmt_mos` -> `"< −100 %"`.
- **v33 SBC-Fallback**: `valuation/dcf.py` `_avg_fcf_start`/`_ttm_fcf_start`/`_ttm_only_fcf_start` fallbacken auf Roh-FCF (`fcf`), wenn `fcf_sbc` fehlt; `DcfResult.sbc_missing=True` -> Pipeline-Flag `SBC n/a (ohne SBC)` + Row `dcf_sbc_missing`.
- **v33 Value-n/a**: `scoring/score.py::score_ticker` setzt `value=NaN`, wenn `coverage < score_groups.min_coverage_value` (0.70); app.py Value-Spalte (TextColumn) zeigt "n/a"; Row traegt `value_na_below_coverage`.
- **v33 Start-FCF <= 0**: `DcfResult.fcf_le0`; app.py `_fmt_mos` + Modus-Tabelle + ND-Tabelle zeigen "Start-FCF ≤ 0" statt n/a; Row `dcf_fcf_le0`.
- **v33 Quality-Rang**: `rank_rows` -> int (Gleichstand gleicher Rang, NaN None); app.py `str(q_rank[t])`.
- **v32 Volllauf-CLI**: `run_ranking.py --tickers CSV [--out/--batch/--pause/--cache/--no-resume]` — Batches, Pause, Fortschritt, Resume (Cache `.ranking_cache.json`), Fehlerlog, Ergebnis-CSV. SEC-Rate-Limit: `data/sec.py::_rate_limit` (Default `sec.max_requests_per_second`=5/s), UA aus `sec.user_agent`.
- **v30 candidate_mode**: `dcf.candidate_mode` = `min_all` (Default, alle 4 Modi) | `min_recent2` (juengstes GJ + TTM). Pipeline berechnet beide Status (`status_all`, `status_recent2` + Details, `mos_recent2`); aktive Regel = `status` (candidate_mode). Rangliste: Spalten "Status (alle Modi)" / "Status (juengste 2)".
- **v30 Quartale**: `TtmResult.quarters` jetzt bis zu 8 Quartale (neuestes zuerst) mit `yoy` (FCF-SBC vs. Vorjahresquartal i+4; NaN fuer die Vorjahresquartale). app.py: Tabelle "Letzte 8 Quartale" + YoY-Spalte; Summenzeile nur ueber `quarters[:4]` (= TTM).
- **v31 Matrix (page_matrix)**: Farbe nach Status (Kandidat gruen #2e7d32, Beobachtung blau #1565c0, sonst grau), x=Quality, y=MoS min der Modi (`mos_rule`, begrenzt auf -100 %), Hilfslinien bei `dcf.buy_quality_min`/`dcf.buy_margin_of_safety_min`, Ziel-Quadrant rechts oben, Tabelle mit Ticker/Status/Quality/MoS je Modus darunter.
- **v29 Historie-Filter**: `scoring/filters.py::count_value_years` zaehlt Jahre mit tatsaechlichen Werten (Kernkennzahlen ungleich NaN), nicht Spalten; Schwelle `filters.min_history_years` (4). Ausschlusstabelle traegt `history_years` je Ticker.
- **v29 EBITDA = EBIT + D&A** aus dem Cashflow-Statement (`depreciationAndAmortization` FMP / `Depreciation And Amortization` yfinance), NICHT das gemeldete EBITDA-Feld; Fallback gemeldetes EBITDA wenn kein D&A. EBITDA < EBIT -> `TickerMetrics.ebitda_unplausible=True` -> Flag `ebitda:unplausibel`, ND/EBITDA n/a (criteria.calc_net_debt_ebitda).
- **v29 Quartalstabelle**: app.py Summenzeile ueber `TtmResult.quarters` (= TTM).
- **Sektorregeln (Schritt 7, ueber INDUSTRY nicht Sector)**: Banken/Versicherer (Banks*, Insurance*, Capital Markets, Asset Management) -> ROE, P/B, Dividendenrendite statt ROIC/FCF/ND/EBITDA; Zykliker (Rohstoffe/Chemie/Stahl/Auto/Energie) -> Gewinne ueber bis zu 7 Jahre normalisiert (sonst Flag `zyk:norm<7J`); REITs (Industry-Praefix 'REIT -') -> FFO-Hinweis statt FCF-Yield. Config: `sector_rules`. PYPL/V/MA (Credit Services) sind KEINE Banken.
- **Universumslader (Schritt 8)**: S&P 500 (Wikipedia -> tickers_sp500.csv, im Repo), STOXX 600 (CSV-Import). Batches (`universe.batch_size`), Pause, Fortschritt, Wiederaufnahme (`.universe_cache.json`), Fehlerlog je Ticker (Fehler stoppt Lauf nicht). CLI: `run_universe.py sp500|stoxx600`; UI: Seite 3.
- **Kaufkandidat**: Quality-Score >= 60 (config `buy_quality_min`) UND Margin of Safety >= 30 % (Minimum der Startwert-MoS, `dcf.mos_min_mode`) UND Bear-Szenario >= Kurs x 0,8; Kandidat nennt den entscheidenden Modus
- **Beobachtung** (Flag `beobachten`): min der MoS < 30 %, aber bester Modus >= `dcf.watch_margin_of_safety_min` (30 %) und Quality >= 60

## UI (Streamlit)
- **Seite 1 Rangliste**: sortierbare Tabelle (Ticker, Name, Sektor, Score, FCF-Yield, Margin of Safety, MoS je Startwert-Modus, Status, SEC-Abgleich, Flags); ausgeschlossene Ticker als Tabelle MIT GRUND direkt unter der Rangliste; Filter nach Sektor/Land/Score
- **Seite 2 Scorecard**: Block-Scores als Balken, 10-J.-Charts (Umsatz, FCF-Marge, ROIC, Verschuldung), DCF-Tabelle mit 3 Szenarien (beide Nettoverschuldungs-Varianten + MoS nebeneinander, MoS Base je Startwert-Modus), letzte 4 Quartale mit Stichtag, SEC-Abgleich-Hinweis, Liste der Rohdaten mit Quelle und Datum
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
