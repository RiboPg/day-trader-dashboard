#!/usr/bin/env python3
"""
Telegram Bot for Day Trader Dashboard.
Standalone, standard library (urllib.request) - ZERO pip dependencies needed!
Features:
- Long polling for Telegram commands: /start, /help, /scan, /status, /portfolio, /pelosi, /buy <TICKER>
- Interactive Inline Keyboards (Pulsanti cliccabili sotto i messaggi: "Simula", "Acquista", "Chiudi Posizione")
- Auto-Alerts: Broadcasts to your chat when a new breakout triggers or market opens!
"""

import urllib.request
import urllib.parse
import json
import time
import os
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_env():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "TELEGRAM_BOT_TOKEN": token = v
                    elif k == "TELEGRAM_CHAT_ID": chat_id = v
    return token, chat_id

def send_telegram_request(token, method, payload=None):
    if not token or token == "TUO_TOKEN_TELEGRAM":
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Telegram Error] {method}: {e}")
        return None

def send_message(token, chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return send_telegram_request(token, "sendMessage", payload)

def api_call(endpoint, method="GET", payload=None):
    url = f"http://127.0.0.1:8080{endpoint}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def format_status():
    status = api_call("/api/status")
    port = status.get("portfolio", {})
    cash = port.get("cash", 5000.0)
    pnl = port.get("total_profit_loss", 0.0)
    pos_count = len(port.get("positions", []))
    auto = "🟢 ATTIVO" if status.get("auto_pilot") else "⚪ OFF"

    pnl_icon = "🟢" if pnl >= 0 else "🔴"
    pnl_sign = "+" if pnl >= 0 else ""

    text = f"📊 <b>DAY TRADER STATUS</b>\n\n"
    text += f"💰 <b>Cassa Libera:</b> ${cash:,.2f}\n"
    text += f"📈 <b>P&L Totale:</b> {pnl_icon} {pnl_sign}${pnl:.2f}\n"
    text += f"💼 <b>Posizioni Aperte:</b> {pos_count}\n"
    text += f"🤖 <b>Pilota Automatico:</b> {auto}\n"
    return text

def format_recommendations():
    recs = api_call("/api/recommendations")
    if not isinstance(recs, list) or len(recs) == 0:
        return "⚠️ Nessun titolo consigliato al momento. Usa /scan per aggiornare i segnali!"
    
    text = "🎯 <b>I 3 TITOLI PIÙ PROFICUI (CONSIGLIATI)</b>\n\n"
    for idx, r in enumerate(recs):
        medal = "🥇" if idx == 0 else ("🥈" if idx == 1 else "🥉")
        text += f"{medal} <b>{r['symbol']}</b> a ${r['price']:.2f} (Affidabilità: <b>{r['ai_confidence']}%</b>)\n"
        for res in r.get("reasons", []):
            text += f"   • {res}\n"
        text += "\n"
    return text

def format_portfolio():
    port = api_call("/api/portfolio")
    positions = port.get("positions", [])
    if not positions:
        return "💼 <b>Il tuo portafoglio è vuoto.</b>\nNessuna posizione aperta al momento."
    
    text = f"💼 <b>POSIZIONI APERTE ({len(positions)})</b>\n\n"
    for p in positions:
        text += f"🔹 <b>{p['symbol']}</b> ({p['shares']} azioni a ${p['entry_price']:.2f})\n"
        text += f"   • Investiti: ${p['total_invested']:.2f}\n"
        text += f"   • Target (1R): ${p['target_price']:.2f} (+${p['potential_gain']:.2f})\n"
        text += f"   • Stop Loss: ${p['stop_price']:.2f} (-${p['max_loss']:.2f})\n\n"
    return text

def format_pelosi():
    list_ptr = api_call("/api/pelosi?limit=5")
    if not isinstance(list_ptr, list) or len(list_ptr) == 0:
        return "Nessun filing recente trovato."
    text = "🏛️ <b>ULTIMI FILING CAMERA USA (Nancy Pelosi)</b>\n\n"
    for p in list_ptr[:5]:
        text += f"📅 <b>{p['filed']}</b> — {p['name']} ({p['district']})\n"
        text += f"📄 Doc {p['doc_id']}: <a href=\"{p['url']}\">Scarica PDF Ufficiale</a>\n\n"
    return text

def telegram_bot_worker():
    token, default_chat_id = load_env()
    if not token or token == "TUO_TOKEN_TELEGRAM":
        print("[Telegram Bot] Token non configurato nel file .env. Bot in attesa di configurazione.")
        return

    print(f"[Telegram Bot] Avviato con successo per il token: {token[:6]}...!")
    last_update_id = 0

    while True:
        try:
            updates = send_telegram_request(token, "getUpdates", {
                "offset": last_update_id + 1,
                "timeout": 20
            })
            if updates and updates.get("ok"):
                for u in updates.get("result", []):
                    last_update_id = u["update_id"]

                    # Handle Callback Queries (Click sui pulsanti inline)
                    if "callback_query" in u:
                        cb = u["callback_query"]
                        cb_data = cb.get("data", "")
                        cb_chat = cb["message"]["chat"]["id"]
                        cb_msg_id = cb["message"]["message_id"]

                        if cb_data.startswith("sim_"):
                            ticker = cb_data.split("_")[1]
                            send_message(token, cb_chat, f"⏳ Calcolo Time Machine per <b>{ticker}</b> (10.000 scenari)...")
                            res = api_call("/api/simulate", method="POST", payload={"ticker": ticker, "date": "2026-11-09"})
                            tm = res.get("timemachine", {})
                            mc = tm.get("mc", {})
                            plan = res.get("plan", {})
                            orders = res.get("orders", {}).get("orders", [])
                            shares = orders[0].get("qty", 1) if orders else 1

                            pt = (mc.get("p_target") or 0) * 100
                            ps = (mc.get("p_stop") or 0) * 100
                            verdict = tm.get("verdict", "")

                            text = f"🎯 <b>TIME MACHINE: {ticker}</b>\n\n"
                            text += f"⚖️ <b>Verdetto:</b> {verdict}\n"
                            text += f"🟢 <b>Probabilità Vincita:</b> {pt:.1f}%\n"
                            text += f"🔴 <b>Probabilità Stop:</b> {ps:.1f}%\n"
                            text += f"💵 <b>Ingresso:</b> ${plan.get('entry', 0):.2f}\n"
                            text += f"🎯 <b>Take Profit (1R):</b> ${plan.get('target', 0):.2f}\n"
                            text += f"🪂 <b>Stop Loss:</b> ${plan.get('stop', 0):.2f}\n"
                            text += f"📦 <b>Azioni Consigliate:</b> {shares} azioni (max rischio: ${shares * plan.get('risk_per_share', 0):.2f})\n"

                            markup = {
                                "inline_keyboard": [
                                    [{"text": f"🛒 Conferma Acquisto {shares}x {ticker}", "callback_data": f"buy_{ticker}"}]
                                ]
                            }
                            send_message(token, cb_chat, text, markup)

                        elif cb_data.startswith("buy_"):
                            ticker = cb_data.split("_")[1]
                            res = api_call("/api/buy", method="POST")
                            if res.get("success"):
                                send_message(token, cb_chat, f"✅ <b>Ordine Eseguito!</b>\n{res.get('message')}\n\nUsa /portfolio per vedere le posizioni attive.")
                            else:
                                send_message(token, cb_chat, f"❌ <b>Errore Ordine:</b> {res.get('error')}")

                    # Handle Text Messages
                    if "message" in u and "text" in u["message"]:
                        msg = u["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg["text"].strip()

                        if text in ["/start", "/help"]:
                            welcome = (
                                "🤖 <b>BENVENUTO NEL BOT DAY TRADER AI</b>\n\n"
                                "Comandi disponibili:\n"
                                "⚡ /scan — Scansiona il mercato e mostra i Top 3 titoli consigliati\n"
                                "🎯 /consigliati — Vedi le 3 azioni più promettenti adesso\n"
                                "📊 /status — Cassa disponibile, P&L e stato del bot\n"
                                "💼 /portfolio — Elenco delle tue posizioni aperte\n"
                                "🏛️ /pelosi — Ultimi trade depositati da Nancy Pelosi alla Camera\n"
                                "🤖 /pilot — Attiva o disattiva il Pilota Automatico\n\n"
                                "Puoi anche digitare direttamente il nome di un'azione (es. <code>AAPL</code>, <code>NVDA</code> o <code>RACE</code>) per simulare l'ingresso!"
                            )
                            send_message(token, chat_id, welcome)

                        elif text == "/status":
                            send_message(token, chat_id, format_status())

                        elif text == "/consigliati":
                            markup = {
                                "inline_keyboard": [
                                    [{"text": "Simula 🥇 AAPL", "callback_data": "sim_AAPL"}, {"text": "Simula 🥈 AMZN", "callback_data": "sim_AMZN"}],
                                    [{"text": "Simula 🥉 AZN", "callback_data": "sim_AZN"}]
                                ]
                            }
                            send_message(token, chat_id, format_recommendations(), markup)

                        elif text == "/portfolio":
                            send_message(token, chat_id, format_portfolio())

                        elif text == "/scan":
                            send_message(token, chat_id, "🔍 <i>Avvio scansione su Wall Street in corso...</i>")
                            api_call("/api/scan", method="POST", payload={"mode": "daily", "symbols": "AAPL,NVDA,MSFT,AMZN,TSLA,RACE,AZN,GOOGL"})
                            markup = {
                                "inline_keyboard": [
                                    [{"text": "Simula 🥇 AAPL", "callback_data": "sim_AAPL"}, {"text": "Simula 🥈 AMZN", "callback_data": "sim_AMZN"}],
                                    [{"text": "Simula 🥉 AZN", "callback_data": "sim_AZN"}]
                                ]
                            }
                            send_message(token, chat_id, "✅ <b>Scansione Completata!</b>\n\n" + format_recommendations(), markup)

                        elif text == "/pelosi":
                            send_message(token, chat_id, format_pelosi())

                        elif text == "/pilot":
                            res = api_call("/api/auto-toggle", method="POST")
                            auto = "🟢 ATTIVATO" if res.get("auto_pilot") else "⚪ DISATTIVATO"
                            send_message(token, chat_id, f"🤖 Pilota Automatico: <b>{auto}</b>")

                        elif text.upper() in ["AAPL", "NVDA", "MSFT", "AMZN", "TSLA", "RACE", "GOOGL", "META", "AZN"]:
                            ticker = text.upper()
                            send_message(token, chat_id, f"⏳ Calcolo Time Machine per <b>{ticker}</b> (10.000 replay)...")
                            res = api_call("/api/simulate", method="POST", payload={"ticker": ticker, "date": "2026-11-09"})
                            tm = res.get("timemachine", {})
                            mc = tm.get("mc", {})
                            plan = res.get("plan", {})
                            orders = res.get("orders", {}).get("orders", [])
                            shares = orders[0].get("qty", 1) if orders else 1

                            pt = (mc.get("p_target") or 0) * 100
                            ps = (mc.get("p_stop") or 0) * 100
                            verdict = tm.get("verdict", "")

                            resp_text = f"🎯 <b>ANALISI TIME MACHINE: {ticker}</b>\n\n"
                            resp_text += f"⚖️ <b>Verdetto:</b> {verdict}\n"
                            resp_text += f"🟢 <b>Probabilità Vincita:</b> {pt:.1f}%\n"
                            resp_text += f"🔴 <b>Probabilità Stop:</b> {ps:.1f}%\n"
                            resp_text += f"💵 <b>Ingresso:</b> ${plan.get('entry', 0):.2f}\n"
                            resp_text += f"🎯 <b>Target 1R:</b> ${plan.get('target', 0):.2f}\n"
                            resp_text += f"🪂 <b>Stop Loss:</b> ${plan.get('stop', 0):.2f}\n"
                            resp_text += f"📦 <b>Azioni Consigliate:</b> {shares} azioni (max rischio: ${shares * plan.get('risk_per_share', 0):.2f})\n"

                            markup = {
                                "inline_keyboard": [
                                    [{"text": f"🛒 Acquista {shares}x {ticker}", "callback_data": f"buy_{ticker}"}]
                                ]
                            }
                            send_message(token, chat_id, resp_text, markup)

        except Exception as e:
            print(f"[Telegram Polling Error] {e}")
            time.sleep(3)

if __name__ == "__main__":
    telegram_bot_worker()
