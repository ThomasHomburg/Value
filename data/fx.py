"""FX-Baustein: historische Waehrungskurse fuer waehrungskonsistente Kennzahlen.

Quelle: FMP-Endpunkt /historical-price-full/{BASE}^{QUOTE} (Tageskurse).
Der Kurs je Jahr wird als letzter Handelstag <= 31.12. des Jahres gewaehlt;
fehlt der Kurs -> NaN; niemals still 1.0 annehmen.

fx_rates.yaml (optional, im Projektverzeichnis) erlaubt manuelle Kurse:
  EURUSD: {"2024": 1.035, "2023": 1.104}
Manuelle Kurse haben Vorrang vor der API (z. B. wenn der FMP-Tarif keine
FX-Historie enthaelt).
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Any

from .fmp_client import FMPClient, FMPError


def _pair_key(base: str, quote: str) -> str:
    return f"{base.upper()}{quote.upper()}"


def _load_manual_rates(path: str = "fx_rates.yaml") -> dict[str, dict[str, float]]:
    """Optionale manuelle Kurse aus fx_rates.yaml (Vorrang vor API)."""
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return {
            pair.upper(): {str(year): float(rate) for year, rate in years.items()}
            for pair, years in raw.items()
            if isinstance(years, dict)
        }
    except Exception:
        return {}


class FXCache:
    """SQLite-Cache fuer Jahresendkurse und Jahr."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS fx_rates (
        pair TEXT NOT NULL,
        year INTEGER NOT NULL,
        rate REAL NOT NULL,
        source TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (pair, year)
    );
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(self.SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, pair: str, year: int) -> float | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rate FROM fx_rates WHERE pair = ? AND year = ?",
                (pair.upper(), year),
            ).fetchone()
            return row[0] if row else None

    def put(self, pair: str, year: int, rate: float, source: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fx_rates (pair, year, rate, source, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(pair, year) DO UPDATE SET
                    rate = excluded.rate,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (pair.upper(), year, rate, source),
            )


class FXConverter:
    """Konvertiert Betraege zwischen Waehrungen mit historischen Kursen."""

    def __init__(self, client: FMPClient, cache: FXCache | None = None,
                 manual_path: str = "fx_rates.yaml") -> None:
        self.client = client
        self.cache = cache
        self.manual = _load_manual_rates(manual_path)

    def rate(self, base: str, quote: str, year: int) -> float:
        """Kurs: 1 base = rate quote. NaN wenn nicht verfuegbar."""
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return 1.0
        pair = _pair_key(base, quote)

        man = self.manual.get(pair, {}).get(str(year))
        if man is not None:
            return man

        cached = self.cache.get(pair, year) if self.cache else None
        if cached is not None:
            return cached

        rate = self._fetch_from_fmp(pair, year)
        if not math.isnan(rate) and self.cache:
            self.cache.put(pair, year, rate, "fmp")
        return rate

    def _fetch_from_fmp(self, pair: str, year: int) -> float:
        """Jahresendkurs von FMP: letzter Kurs <= 31.12. des Jahres."""
        try:
            data = self.client._get("historical-price-full", {
                "from": f"{year}-01-01", "to": f"{year}-12-31", "symbol": pair,
            })
        except FMPError:
            return float("nan")
        if not isinstance(data, dict):
            return float("nan")
        history: list[dict[str, Any]] = data.get("historical", [])
        if not history:
            return float("nan")
        closes = sorted(
            (h.get("date", ""), h.get("close")) for h in history if h.get("close") is not None
        )
        if not closes:
            return float("nan")
        return float(closes[-1][1])

    def convert(self, value: float, from_cur: str, to_cur: str, year: int) -> float:
        """Betrag von from_cur nach to_cur zum Jahresendkurs; NaN bei Misserfolg."""
        if math.isnan(value):
            return float("nan")
        if from_cur.upper() == to_cur.upper():
            return value
        rate = self.rate(from_cur, to_cur, year)
        if math.isnan(rate):
            return float("nan")
        return value * rate
