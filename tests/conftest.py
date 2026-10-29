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
    return load_config()
