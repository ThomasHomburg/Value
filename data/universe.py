"""Universumslader (v28, CLAUDE.md Schritt 8).

- S&P 500: Liste von der Wikipedia-Tabelle (pandas.read_html auf
  'List of S&P 500 companies'), Ergebnis wird als tickers_sp500.csv gespeichert.
- STOXX 600: Import per CSV (tickers_stoxx600.csv, Spalte 'ticker').
- Abruf in Batches (config `universe.batch_size`, Default 20 Ticker) mit
  Pause dazwischen (`batch_pause_seconds`), Fortschrittsanzeige (Log +
  Status-Callback), Wiederaufnahme nach Abbruch (`resume`, Cache-Datei
  `.universe_cache.json` mit Status je Ticker: ok/fehler).
- Fehlerlog je Ticker: yfinance wirft bei einzelnen Tickern Fehler --
  das darf den Lauf nicht stoppen (ProviderError/Exception wird geloggt
  und der Ticker als 'fehler' markiert).
"""

from __future__ import annotations

import io
import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Callable

from data.loader import TickerMetrics
from data.providers.base import ProviderError, build_providers, load_with_provider

logger = logging.getLogger("value_screener.universe")

ProgressCb = Callable[[int, int, str], None]  # (aktuell, gesamt, ticker)


def fetch_sp500_tickers(url: str, csv_path: str | Path) -> list[str]:
    """Laedt die S&P-500-Liste von Wikipedia (pandas.read_html) und speichert
    sie als tickers_sp500.csv (Spalte 'ticker'). Rueckgabe: Ticker-Liste."""
    import pandas as pd
    # Wikipedia blockiert den Default-pandas-User-Agent (HTTP 403) --
    # daher eigener User-Agent via urllib (wie bei der SEC-Schnittstelle
    # Pflicht) und read_html auf dem HTML-String.
    req = urllib.request.Request(url, headers={
        "User-Agent": "Value-Screener research@example.com (research; contact@example.com)",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    tables = pd.read_html(io.StringIO(html))  # StringIO -> kein Dateiname noetig
    df = None
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if "symbol" in cols:
            df = t
            break
    if df is None:
        raise ValueError("Wikipedia-Tabelle ohne Spalte 'Symbol' nicht gefunden")
    col = next(c for c in df.columns if str(c).strip().lower() == "symbol")
    tickers = [str(s).strip().upper().replace(".", "-").replace("/", "-")
               for s in df[col].tolist() if str(s).strip()]
    tickers = sorted(set(tickers))
    out = Path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("ticker\n")
        for t in tickers:
            fh.write(f"{t}\n")
    logger.info("S&P 500: %d Ticker von Wikipedia geladen -> %s", len(tickers), out)
    return tickers


def load_sp500_tickers(csv_path: str | Path,
                       url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                       refresh: bool = False) -> list[str]:
    """S&P-500-Ticker aus tickers_sp500.csv; legt die Datei bei Bedarf
    (refresh oder Datei fehlt) von Wikipedia neu an."""
    path = Path(csv_path)
    if refresh or not path.exists():
        return fetch_sp500_tickers(url, path)
    tickers = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.strip().lower().startswith("ticker")]
    logger.info("S&P 500: %d Ticker aus %s geladen", len(tickers), path)
    return tickers


def load_stoxx600_tickers(csv_path: str | Path) -> list[str]:
    """STOXX-600-Ticker per CSV-Import (Spalte 'ticker')."""
    import csv as _csv
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"STOXX-600-CSV nicht gefunden: {path}")
    with path.open(encoding="utf-8") as fh:
        rows = list(_csv.DictReader(fh))
    tickers = [r["ticker"].strip().upper() for r in rows if r.get("ticker")]
    logger.info("STOXX 600: %d Ticker aus %s geladen", len(tickers), path)
    return tickers


def _load_cache(cache_file: str | Path) -> dict:
    path = Path(cache_file)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache_file: str | Path, cache: dict) -> None:
    Path(cache_file).write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                                encoding="utf-8")


def load_universe(tickers: list[str], cfg: dict,
                  progress_cb: ProgressCb | None = None) -> tuple[list[TickerMetrics], list[dict]]:
    """Laedt ein Universum in Batches mit Fortschritt, Wiederaufnahme und
    Fehlerlog je Ticker.

    Rueckgabe: (companies, errors) -- errors: [{"ticker", "error"}]
    (ein Fehler stoppt den Lauf nicht).
    """
    ucfg = cfg.get("universe", {})
    batch_size = int(ucfg.get("batch_size", 20))
    pause = float(ucfg.get("batch_pause_seconds", 2.0))
    resume = bool(ucfg.get("resume", True))
    cache_file = ucfg.get("cache_file", ".universe_cache.json")

    providers = build_providers("")  # yfinance (kein Key noetig)
    years = int(cfg.get("data", {}).get("years", 5))

    cache = _load_cache(cache_file) if resume else {}
    todo = [t for t in tickers if cache.get(t, {}).get("status") != "ok"]
    companies: list[TickerMetrics] = []
    errors: list[dict] = []
    total = len(tickers)
    logger.info("Universum: %d Ticker gesamt, %d offen (Batch %d, Pause %.1fs)",
                total, len(todo), batch_size, pause)

    done = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        for ticker in batch:
            done += 1
            try:
                m = load_with_provider(ticker, cfg, providers, years=years)
                companies.append(m)
                cache[ticker] = {"status": "ok", "name": m.name}
                logger.info("[%d/%d] %s OK (%s)", done, len(todo), ticker, m.name)
            except Exception as exc:  # ProviderError + yfinance-Fehler je Ticker
                errors.append({"ticker": ticker, "error": str(exc)})
                cache[ticker] = {"status": "fehler", "error": str(exc)}
                logger.error("[%d/%d] %s FEHLER: %s", done, len(todo), ticker, exc)
            if progress_cb is not None:
                progress_cb(done, len(todo), ticker)
        _save_cache(cache_file, cache)
        if start + batch_size < len(todo):
            time.sleep(pause)  # Pause zwischen Batches (Rate-Limit)

    logger.info("Universum fertig: %d geladen, %d Fehler", len(companies), len(errors))
    return companies, errors
