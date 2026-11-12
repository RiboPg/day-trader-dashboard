#!/usr/bin/env python3
"""
Alpaca Markets Paper Trading Client.
Standard library only (urllib.request) - ZERO pip dependencies needed.
Official API v2: https://paper-api.alpaca.markets
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_alpaca_credentials():
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")

    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "ALPACA_API_KEY": api_key = v
                    elif k == "ALPACA_SECRET_KEY": secret_key = v
                    elif k == "ALPACA_PAPER": paper = v.lower() in ("true", "1", "yes")
    return api_key, secret_key, paper

class AlpacaClient:
    def __init__(self, api_key=None, secret_key=None, paper=None):
        env_key, env_secret, env_paper = load_alpaca_credentials()
        self.api_key = api_key or env_key
        self.secret_key = secret_key or env_secret
        self.paper = paper if paper is not None else env_paper
        self.base_url = "https://paper-api.alpaca.markets" if self.paper else "https://api.alpaca.markets"

    @property
    def is_configured(self):
        return bool(self.api_key and self.secret_key and not self.api_key.startswith("TUO_") and len(self.api_key) > 5)

    def _request(self, endpoint, method="GET", payload=None):
        if not self.is_configured:
            return {"error": "Alpaca API keys non configurate nel file .env"}
        url = f"{self.base_url}{endpoint}"
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
            "User-Agent": "DayTraderAI-RaspberryPi/1.0"
        }
        data = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err)
                return {"error": err_json.get("message", err), "code": e.code}
            except Exception:
                return {"error": f"HTTP {e.code}: {err or e.reason}", "code": e.code}
        except Exception as e:
            return {"error": str(e)}

    def get_account(self):
        """Restituisce cassa, equity e stato del conto Alpaca."""
        return self._request("/v2/account")

    def get_positions(self):
        """Restituisce tutte le posizioni attualmente aperte su Alpaca."""
        res = self._request("/v2/positions")
        if isinstance(res, list):
            return res
        return []

    def place_bracket_order(self, symbol, qty, side="buy", target_price=None, stop_price=None):
        """
        Piazza un ordine Bracket su Alpaca:
        1. Compra qty azioni di symbol a mercato.
        2. Inserisce contemporaneamente Take Profit (limit_price) e Stop Loss (stop_price) OCO.
        """
        payload = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day"
        }
        if target_price and stop_price:
            payload["order_class"] = "bracket"
            payload["take_profit"] = {"limit_price": f"{float(target_price):.2f}"}
            payload["stop_loss"] = {"stop_price": f"{float(stop_price):.2f}"}
        
        return self._request("/v2/orders", method="POST", payload=payload)

    def close_position(self, symbol):
        """Chiude a mercato la posizione per il titolo specificato."""
        return self._request(f"/v2/positions/{symbol.upper()}", method="DELETE")

    def close_all_positions(self):
        """Liquida tutte le posizioni aperte (per fine giornata 15:55 ET)."""
        return self._request("/v2/positions", method="DELETE")

    def get_open_orders(self):
        """Restituisce tutti gli ordini pendenti (es. stop e target ancora attivi)."""
        return self._request("/v2/orders?status=open&nested=true")
