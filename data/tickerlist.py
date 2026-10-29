"""Loader fuer Ticker-Listen (CSV-Datei oder Freitext).

CSV-Format: Eine Spalte `ticker` (oder `symbol`), eine Zeile pro Ticker.
Leerzeilen und Kommentarzeilen (#) werden ignoriert. Ticker werden getrimmt
und in Grossbuchstaben normalisiert. Duplikate werden entfernt (Reihenfolge
bleibt erhalten).
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd


def normalize_tickers(raw: list[str]) -> list[str]:
    """Normalisiert Roh-Ticker: trimmen, upper, leere/duplikate entfernen."""
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        t = str(t).strip().upper()
        if t and not t.startswith("#") and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def parse_ticker_csv(content: str | bytes) -> list[str]:
    """Parst CSV-Inhalt (Text oder Bytes) zu einer Tickerliste."""
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(content))
    col = next((c for c in df.columns if str(c).strip().lower() in ("ticker", "symbol")), None)
    if col is None:
        raise ValueError("CSV braucht eine Spalte 'ticker' (oder 'symbol').")
    return normalize_tickers(df[col].dropna().tolist())


def parse_ticker_text(text: str) -> list[str]:
    """Parst Freitext: komma-/zeilengetrennt Ticker."""
    parts: list[str] = []
    for line in text.replace(",", "\n").splitlines():
        parts.extend(line.split())
    return normalize_tickers(parts)


def load_ticker_file(path: str | Path = "tickers.csv") -> list[str]:
    """Laedt eine Ticker-CSV aus dem Projektverzeichnis; fehlend -> leere Liste."""
    p = Path(path)
    if not p.exists():
        return []
    return parse_ticker_csv(p.read_text(encoding="utf-8"))
