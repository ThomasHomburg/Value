"""Tests fuer den Tickerlisten-Loader (CSV/Freitext, Normalisierung)."""

import pytest

from data.tickerlist import load_ticker_file, normalize_tickers, parse_ticker_csv, parse_ticker_text


def test_normalize_tickers():
    assert normalize_tickers([" aapl ", "MSFT", "aapl", "", "# kommentar", "sap.de"]) == [
        "AAPL", "MSFT", "SAP.DE",
    ]


def test_parse_ticker_csv_basic():
    content = "ticker\nAAPL\nMSFT\n\n# kommentar\nsap.de\n"
    assert parse_ticker_csv(content) == ["AAPL", "MSFT", "SAP.DE"]


def test_parse_ticker_csv_symbol_column():
    content = "symbol,branche\nAAPL,Tech\nMSFT,Tech\n"
    assert parse_ticker_csv(content) == ["AAPL", "MSFT"]


def test_parse_ticker_csv_bytes_with_bom():
    content = "﻿ticker\r\nAAPL\r\n".encode("utf-8")
    assert parse_ticker_csv(content) == ["AAPL"]


def test_parse_ticker_csv_missing_column_raises():
    with pytest.raises(ValueError):
        parse_ticker_csv("name,price\nApple,100\n")


def test_parse_ticker_text_commas_and_lines():
    assert parse_ticker_text("AAPL, MSFT\nGOOGL NVDA") == ["AAPL", "MSFT", "GOOGL", "NVDA"]


def test_parse_ticker_text_empty():
    assert parse_ticker_text("  \n   ") == []


def test_load_ticker_file_missing(tmp_path):
    assert load_ticker_file(tmp_path / "nicht-da.csv") == []


def test_load_ticker_file(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("ticker\nAAPL\nSAP.DE\n", encoding="utf-8")
    assert load_ticker_file(p) == ["AAPL", "SAP.DE"]
