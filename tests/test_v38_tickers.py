"""Tests fuer v38: run_ranking.py --tickers mit fehlender/0-Ticker-Datei.

--tickers-Datei existiert nicht -> Abbruch mit "Ticker-Datei nicht gefunden"
+ SystemExit code 1, KEINE Ergebnis-CSV.
--tickers-Datei existiert, liefert aber 0 Ticker (keine Spalte 'ticker' oder
leer) -> Abbruch mit "0 Ticker gelesen ... Spalte 'ticker' pruefen"
+ SystemExit code 1, KEINE Ergebnis-CSV.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_ranking


def _run_main(monkeypatch, argv, capsys):
    """main() mit gepatchtem sys.argv aufrufen; gibt (exit_code, stderr) zurueck."""
    monkeypatch.setattr(sys, "argv", ["run_ranking.py"] + argv)
    with pytest.raises(SystemExit) as exc:
        run_ranking.main()
    err = capsys.readouterr().err
    return exc.value.code, err


def test_tickers_datei_fehlt_abbruch_code1_keine_csv(tmp_path, monkeypatch, capsys):
    """--tickers auf nicht existierende Datei -> 'Ticker-Datei nicht gefunden',
    Exit-Code 1, keine Ergebnis-CSV wird geschrieben."""
    missing = tmp_path / "gibts_nicht.csv"
    out = tmp_path / "ranking_sollte_nicht_entstehen.csv"
    code, err = _run_main(monkeypatch,
                          ["--tickers", str(missing), "--out", str(out)], capsys)
    assert code == 1
    assert "Ticker-Datei nicht gefunden" in err
    assert str(missing) in err
    assert not out.exists(), "keine leere Ergebnis-CSV darf geschrieben werden"


def test_tickers_datei_0_ticker_abbruch_code1_keine_csv(tmp_path, monkeypatch, capsys):
    """--tickers-Datei ohne Spalte 'ticker' (oder leer) -> '0 Ticker gelesen ...
    Spalte ticker pruefen', Exit-Code 1, keine CSV."""
    f = tmp_path / "leer.csv"
    f.write_text("name,wert\nfoo,1\n", encoding="utf-8")  # keine ticker-Spalte
    out = tmp_path / "ranking_out.csv"
    code, err = _run_main(monkeypatch,
                          ["--tickers", str(f), "--out", str(out)], capsys)
    assert code == 1
    assert "0 Ticker gelesen" in err or "Spalte 'ticker'" in err
    assert not out.exists()


def test_tickers_datei_leer_0_ticker(tmp_path, monkeypatch, capsys):
    """--tickers-Datei mit Spalte 'ticker', aber nur Leerzeilen -> 0 Ticker."""
    f = tmp_path / "nur_header.csv"
    f.write_text("ticker\n\n# kommentar\n", encoding="utf-8")
    out = tmp_path / "ranking_out2.csv"
    code, err = _run_main(monkeypatch,
                          ["--tickers", str(f), "--out", str(out)], capsys)
    assert code == 1
    assert "0 Ticker gelesen" in err and "Spalte 'ticker' pruefen" in err
    assert not out.exists()


def test_tickers_datei_mit_ticker_laeuft_durch(tmp_path, monkeypatch, capsys):
    """Gegenprobe: gueltige --tickers-Datei -> KEIN SystemExit(1); Lauf startet
    (load wird gepatcht, damit keine echten HTTP-Calls)."""
    f = tmp_path / "ok.csv"
    f.write_text("ticker\nAAPL\n", encoding="utf-8")
    out = tmp_path / "ranking_ok.csv"
    monkeypatch.setattr(run_ranking, "load_with_provider",
                        lambda t, cfg, providers, years=5: __import__("data.demo", fromlist=["demo_companies"]).demo_companies()[0])
    monkeypatch.setattr(run_ranking.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv",
                        ["run_ranking.py", "--tickers", str(f), "--out", str(out), "--no-resume"])
    run_ranking.main()  # darf nicht SystemExit(1) werfen
    assert out.exists()  # Ergebnis-CSV wurde geschrieben
