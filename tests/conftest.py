import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_config
from data.demo import AAPL_BALANCE, AAPL_CASHFLOW, AAPL_INCOME, AAPL_PROFILE
from data.loader import extract_metrics


@pytest.fixture
def aapl_metrics():
    return extract_metrics("AAPL", AAPL_INCOME, AAPL_BALANCE, AAPL_CASHFLOW, AAPL_PROFILE)


@pytest.fixture
def cfg():
    cfg = load_config()
    # SEC-EDGAR-Abgleich in Tests deaktiviert: keine echten HTTP-Calls
    # gegen data.sec.gov (langsam, Rate-Limit, im CI nicht deterministisch).
    # Tests in test_v26.py testen data.sec mit dem Fixture `cfg_sec`
    # (enabled=True) und gemonkeypatchten _cik_for_ticker/_fetch_companyfacts.
    sec = dict(cfg.get("sec", {}))
    sec["enabled"] = False
    cfg["sec"] = sec
    return cfg
