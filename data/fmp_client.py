"""FMP-API-Client fuer einen Ticker."""
from __future__ import annotations
import os
from typing import Any

import requests

BASE_URL = "https://financialmodelingprep.com/stable"
TIMEOUT = 15


class FMPError(RuntimeError):
    """Fehler bei der Kommunikation mmt der FMP-API."""


class FMPClient:
    def __init__(self, api_key: str | None = None, timeout: int = TIMEOUT) -> None:
        self.api_key = api_key or os.environ.get("FMP_API_KEY", "")
        self.timeout = timeout
        self._session = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            raise FMPError("Kein FMP_API_KEY gesetzt.")
        params = dict(params or {})
        params["apikey"] = self.api_key
        url = f"{BASE_URL}/{path}"
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FMPError(f"Netzwerkfehler bei {path}: {exc}") from exc
        if resp.status_code != 200 or "Error Message" in resp.text[:200]:
            raise FMPError(f"API-Fehler bei {path} (HTTP {resp.status_code}): {resp.text[:200]}")
        return resp.json()

    def income_statements(self, ticker: str, years: int = 5) -> list[dict[str, Any]]:
        data = self._get("income-statement", {"symbol": ticker, "limit": years, "period": "annual"})
        return data if isinstance(data, list) else []

    def balance_sheets(self, ticker: str, years: int = 5) -> list[dict[str, Any]]:
        data = self._get("balance-sheet-statement", {"symbol": ticker, "limit": years, "period": "annual"})
        return data if isinstance(data, list) else []

    def cash_flows(self, ticker: str, years: int = 5) -> list[dict[str, Any]]:
        data = self._get("cash-flow-statement", {"symbol": ticker, "limit": years, "period": "annual"})
        return data if isinstance(data, list) else []

    def profile(self, ticker: str) -> dict[str, Any] | None:
        data = self._get("profile", {"symbol": ticker})
        if isinstance(data, list) and data:
            return data[0]
        return None
