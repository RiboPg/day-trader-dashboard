#!/usr/bin/env python3
"""
Day Trader Dashboard Backend (Enhanced with Recommendations & Paper Portfolio)
Zero external dependencies - standard library Python.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import base64
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TRADER_DIR = BASE_DIR / "trader"
# Self-contained local skills folder fallback to global
SKILLS_DIR = BASE_DIR / "skills" if (BASE_DIR / "skills").exists() else Path("/Users/ribo/.gemini/config/skills")
PORT = 8080

def load_auth_credentials():
    """Load DASHBOARD_USER and DASHBOARD_PASSWORD from .env file if present."""
    env_file = BASE_DIR / ".env"
    user = os.environ.get("DASHBOARD_USER")
    pwd = os.environ.get("DASHBOARD_PASSWORD")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k == "DASHBOARD_USER": user = v
                    elif k == "DASHBOARD_PASSWORD": pwd = v
    return user, pwd

auto_pilot_running = False
auto_pilot_logs = []

def run_skill_command(cmd_args):
    """Run a command with cwd set to BASE_DIR and return stdout, stderr, code."""
    try:
        proc = subprocess.run(
            cmd_args,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=120
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)

def get_config():
    cfg_file = TRADER_DIR / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"budget": 5000, "max_loss_per_trade_usd": 50, "paper": True}

def get_watchlist():
    wl_file = TRADER_DIR / "watchlist.json"
    if wl_file.exists():
        try:
            with open(wl_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"hits": [], "total_scanned": 0}

def get_plan():
    plan_file = TRADER_DIR / "plan.json"
    if plan_file.exists():
        try:
            with open(plan_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def get_timemachine():
    tm_file = TRADER_DIR / "timemachine.json"
    if tm_file.exists():
        try:
            with open(tm_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def get_orders():
    ord_file = TRADER_DIR / "orders.json"
    if ord_file.exists():
        try:
            with open(ord_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def get_portfolio():
    port_file = TRADER_DIR / "portfolio.json"
    if port_file.exists():
        try:
            with open(port_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "cash": get_config().get("budget", 5000),
        "positions": [],
        "closed": [],
        "total_profit_loss": 0.0
    }

def save_portfolio(port_data):
    port_file = TRADER_DIR / "portfolio.json"
    with open(port_file, "w") as f:
        json.dump(port_data, f, indent=2)

def compute_recommendations():
    """Analyze the watchlist and return the Top 3 algorithmic recommendations."""
    wl = get_watchlist()
    hits = wl.get("hits", [])
    if not hits:
        return []
    
    scored = []
    for h in hits:
        score = 0
        reasons = []
        setups = h.get("setups", [])
        rsi = h.get("rsi_14", 50)
        
        # High volume/market cap preference
        if h.get("symbol") in ["AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA"]:
            score += 40
            reasons.append("Big Tech super-liquido")

        # Double setup bonus
        if len(setups) >= 2:
            score += 30
            reasons.append("Confluenza di segnali multipli")
        elif len(setups) == 1:
            score += 15

        if any("breakout" in s for s in setups):
            score += 20
            reasons.append("Breakout massimi a 20 giorni")
        if any("reclaim" in s for s in setups):
            score += 15
            reasons.append("Recupero media mobile a 20gg")
        if any("bull_flag" in s for s in setups):
            score += 25
            reasons.append("Formazione Bull Flag esplosiva")
        if any("oversold" in s for s in setups) and rsi < 30:
            score += 15
            reasons.append(f"Rimbalzo da ipervenduto (RSI {rsi:.1f})")

        scored.append({
            "symbol": h.get("symbol"),
            "price": h.get("last_close") or h.get("price") or 0,
            "rsi": rsi,
            "setups": setups,
            "score": score,
            "reasons": reasons,
            "ai_confidence": min(95, max(60, 50 + score // 2))
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:3]

class TraderAPIHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR / "public"), **kwargs)

    def check_auth(self):
        # Consenti sempre le chiamate interne da localhost (es. telegram_bot.py)
        if self.client_address[0] in ("127.0.0.1", "::1", "localhost"):
            return True
        expected_user, expected_pwd = load_auth_credentials()
        # If no user or password set in .env or environment, allow freely
        if not expected_user or not expected_pwd:
            return True
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Basic "):
            return False
        try:
            encoded_creds = auth_header.split(" ", 1)[1]
            decoded = base64.b64decode(encoded_creds).decode("utf-8")
            u, p = decoded.split(":", 1)
            return (u == expected_user and p == expected_pwd)
        except Exception:
            return False

    def require_auth(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Day Trader Dashboard"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>401 Accesso Richiesto</h1><p>Inserisci Username e Password per visualizzare la Dashboard.</p>")

    def do_HEAD(self):
        if not self.check_auth():
            self.require_auth()
            return
        super().do_HEAD()

    def do_GET(self):
        if not self.check_auth():
            self.require_auth()
            return
        url = urllib.parse.urlparse(self.path)
        path = url.path
        query = urllib.parse.parse_qs(url.query)

        if path == "/api/status":
            self.send_json_response({
                "status": "online",
                "config": get_config(),
                "watchlist": get_watchlist(),
                "recommendations": compute_recommendations(),
                "plan": get_plan(),
                "timemachine": get_timemachine(),
                "orders": get_orders(),
                "portfolio": get_portfolio(),
                "auto_pilot": auto_pilot_running,
                "auto_pilot_logs": auto_pilot_logs[-10:]
            })
        elif path == "/api/watchlist":
            self.send_json_response(get_watchlist())
        elif path == "/api/recommendations":
            self.send_json_response(compute_recommendations())
        elif path == "/api/portfolio":
            self.send_json_response(get_portfolio())
        elif path == "/api/news":
            tickers = query.get("ticker", ["AAPL,NVDA,TSLA,AMZN,RACE"])[0]
            hours = query.get("hours", ["24"])[0]
            script = str(SKILLS_DIR / "trader-news" / "news.py")
            code, out, err = run_skill_command([
                sys.executable, script, "--tickers", *tickers.split(","), "--hours", hours, "--no-sec", "--json"
            ])
            try:
                data = json.loads(out)
                self.send_json_response(data)
            except Exception:
                self.send_json_response({"items": [], "raw_output": out, "error": err})
        elif path == "/api/pelosi":
            limit = query.get("limit", ["15"])[0]
            member = query.get("member", ["pelosi"])[0]
            script = str(SKILLS_DIR / "trader-pelosi" / "ptr.py")
            code, out, err = run_skill_command([
                sys.executable, script, "index", "--member", member, "--limit", limit, "--json"
            ])
            try:
                data = json.loads(out)
                self.send_json_response(data)
            except Exception:
                self.send_json_response({"error": err, "raw": out})
        elif path == "/api/config":
            self.send_json_response(get_config())
        else:
            super().do_GET()

    def do_POST(self):
        if not self.check_auth():
            self.require_auth()
            return
        url = urllib.parse.urlparse(self.path)
        path = url.path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/scan":
            mode = payload.get("mode", "daily")
            symbols = payload.get("symbols", "")
            script = str(SKILLS_DIR / "trader-scanner" / "scan.py")
            cmd = [sys.executable, script, mode]
            if symbols:
                cmd.extend(["--symbols", symbols])
            else:
                cmd.extend(["--pause", "0.05", "--show", "50"])
            code, out, err = run_skill_command(cmd)
            self.send_json_response({
                "success": code == 0,
                "output": out,
                "error": err,
                "watchlist": get_watchlist(),
                "recommendations": compute_recommendations()
            })
        elif path == "/api/simulate":
            ticker = payload.get("ticker", "AAPL").upper()
            date = payload.get("date", "")
            
            entry_script = str(SKILLS_DIR / "trader-entry" / "entry.py")
            entry_cmd = [sys.executable, entry_script, "check", ticker, "--write"]
            if date:
                entry_cmd.extend(["--now", f"{date} 15:30"])
            run_skill_command(entry_cmd)

            exit_script = str(SKILLS_DIR / "trader-exit" / "exit.py")
            exit_cmd = [sys.executable, exit_script, "plan", "--stop", "or-mid", "--target", "1R", "--write"]
            if date:
                exit_cmd.extend(["--now", f"{date} 15:30"])
            run_skill_command(exit_cmd)

            tm_script = str(SKILLS_DIR / "trader-timemachine" / "timemachine.py")
            tm_cmd = [sys.executable, tm_script, "run", "--until", "15:55", "--json", "--write"]
            run_skill_command(tm_cmd)

            size_script = str(SKILLS_DIR / "trader-budget" / "size.py")
            size_cmd = [sys.executable, size_script, "--write"]
            if date:
                size_cmd.extend(["--now", f"{date} 15:30"])
            run_skill_command(size_cmd)

            risk_script = str(SKILLS_DIR / "trader-risk" / "check.py")
            risk_cmd = [sys.executable, risk_script]
            if date:
                risk_cmd.extend(["--now", f"{date} 15:30"])
            code, rk_out, rk_err = run_skill_command(risk_cmd)

            self.send_json_response({
                "ticker": ticker,
                "plan": get_plan(),
                "timemachine": get_timemachine(),
                "orders": get_orders(),
                "risk_output": rk_out
            })
        elif path == "/api/buy":
            # Execute Paper Buy Order into Portfolio
            plan = get_plan()
            orders = get_orders()
            if not plan or not orders:
                self.send_json_response({"success": False, "error": "Nessun piano o ordine pronto per l'acquisto"}, 400)
                return

            order = orders[0]
            shares = order.get("qty", 10)
            entry_price = plan.get("entry", 350.0)
            cost = shares * entry_price

            port = get_portfolio()
            if port["cash"] < cost:
                self.send_json_response({"success": False, "error": f"Fondi insufficienti: servono ${cost:.2f}, disponibili ${port['cash']:.2f}"}, 400)
                return

            # Deduct cash & add position
            port["cash"] -= cost
            position = {
                "id": f"pos-{int(time.time())}",
                "symbol": plan.get("symbol", "AAPL"),
                "shares": shares,
                "entry_price": entry_price,
                "total_invested": cost,
                "target_price": plan.get("target"),
                "stop_price": plan.get("stop"),
                "max_loss": shares * plan.get("risk", 0),
                "potential_gain": shares * plan.get("risk", 0),
                "status": "OPEN",
                "opened_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            port["positions"].append(position)
            save_portfolio(port)

            self.send_json_response({
                "success": True,
                "message": f"Acquistate con successo {shares} azioni di {position['symbol']} a ${entry_price:.2f}!",
                "position": position,
                "portfolio": port
            })
        elif path == "/api/close-position":
            pos_id = payload.get("id")
            exit_type = payload.get("exit_type", "TARGET") # TARGET, STOP, or MANUAL
            port = get_portfolio()
            
            pos = next((p for p in port["positions"] if p["id"] == pos_id), None)
            if not pos:
                self.send_json_response({"success": False, "error": "Posizione non trovata"}, 404)
                return

            port["positions"] = [p for p in port["positions"] if p["id"] != pos_id]
            
            # Compute P&L
            if exit_type == "TARGET":
                pnl = pos["potential_gain"]
                payout = pos["total_invested"] + pnl
            elif exit_type == "STOP":
                pnl = -pos["max_loss"]
                payout = pos["total_invested"] + pnl
            else: # Manual exit
                pnl = pos["potential_gain"] * 0.5
                payout = pos["total_invested"] + pnl

            port["cash"] += payout
            port["total_profit_loss"] += pnl
            pos["status"] = "CLOSED"
            pos["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            pos["pnl"] = pnl
            pos["exit_type"] = exit_type
            port["closed"].append(pos)
            save_portfolio(port)

            self.send_json_response({
                "success": True,
                "pnl": pnl,
                "portfolio": port
            })
        elif path == "/api/config":
            cfg_file = TRADER_DIR / "config.json"
            cur_cfg = get_config()
            cur_cfg.update(payload)
            with open(cfg_file, "w") as f:
                json.dump(cur_cfg, f, indent=2)
            self.send_json_response({"success": True, "config": cur_cfg})
        elif path == "/api/auto-toggle":
            global auto_pilot_running
            auto_pilot_running = not auto_pilot_running
            status = "ATTIVATO" if auto_pilot_running else "DISATTIVATO"
            auto_pilot_logs.append(f"[{time.strftime('%H:%M:%S')}] Pilota Automatico {status}")
            self.send_json_response({"auto_pilot": auto_pilot_running, "logs": auto_pilot_logs})
        else:
            self.send_error(404, "Endpoint not found")

    def send_json_response(self, data, code=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def auto_pilot_worker():
    global auto_pilot_running
    while True:
        if auto_pilot_running:
            now_str = time.strftime('%H:%M:%S')
            auto_pilot_logs.append(f"[{now_str}] Ciclo pilota: verifica scanner e watchlist...")
            script = str(SKILLS_DIR / "trader-scanner" / "scan.py")
            run_skill_command([sys.executable, script, "daily", "--symbols", "AAPL,NVDA,MSFT,AMZN,TSLA,RACE"])
        time.sleep(300)

if __name__ == "__main__":
    t = threading.Thread(target=auto_pilot_worker, daemon=True)
    t.start()
    server_address = ("0.0.0.0", PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, TraderAPIHandler)
    print(f"=====================================================")
    print(f"🚀 Day Trader Dashboard in esecuzione su:")
    print(f"👉 http://localhost:{PORT}")
    print(f"=====================================================")
    httpd.serve_forever()
