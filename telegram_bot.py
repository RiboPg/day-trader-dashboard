#!/usr/bin/env python3
"""
Telegram Bot for Day Trader Dashboard.
Standalone, standard library (urllib.request) - ZERO pip dependencies needed!
Features:
- Long polling for Telegram commands: /start, /help, /scan, /consigliati, /status, /portfolio, /pelosi, /pilot, /test
- Interactive Inline Keyboards (Pulsanti cliccabili: "Simula", "Acquista", "Chiudi Posizione")
- Proactive Background Scanner: Invia segnali automatici su Telegram appena individua breakout/opportunità!
- Notifica immediata di avvio (Startup Ping) su Telegram per confermare che il Raspberry Pi è online.
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import time
import os
import base64
import threading
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def load_env():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    dash_user = os.environ.get("DASHBOARD_USER")
    dash_pwd = os.environ.get("DASHBOARD_PASSWORD")
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
                    elif k == "DASHBOARD_USER": dash_user = v
                    elif k == "DASHBOARD_PASSWORD": dash_pwd = v
    return token, chat_id, dash_user, dash_pwd

def save_chat_id_to_env(new_chat_id):
    """Salva automaticamente il chat_id scoperto nel file .env."""
    env_file = BASE_DIR / ".env"
    lines = []
    found = False
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("TELEGRAM_CHAT_ID="):
                    lines.append(f"TELEGRAM_CHAT_ID={new_chat_id}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"\nTELEGRAM_CHAT_ID={new_chat_id}\n")
    try:
        with open(env_file, "w") as f:
            f.writelines(lines)
    except Exception as e:
        print(f"[Bot] Impossibile salvare chat_id in .env: {e}")

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
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"[Telegram Error] {method}: HTTP Error {e.code}: {err_body}")
        return None
    except Exception as e:
        print(f"[Telegram Error] {method}: {e}")
        return None

def send_message(token, chat_id, text, reply_markup=None):
    if not chat_id:
        return None
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
    _, _, dash_user, dash_pwd = load_env()
    headers = {"Content-Type": "application/json"}
    if dash_user and dash_pwd:
        creds = base64.b64encode(f"{dash_user}:{dash_pwd}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {creds}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"error": f"HTTP {e.code}: {err_msg or e.reason}"}
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

    text = f"📊 <b>DAY TRADER STATUS (Raspberry Pi)</b>\n\n"
    text += f"💰 <b>Cassa Libera:</b> ${cash:,.2f}\n"
    text += f"📈 <b>P&L Totale:</b> {pnl_icon} {pnl_sign}${pnl:.2f}\n"
    text += f"💼 <b>Posizioni Aperte:</b> {pos_count}\n"
    text += f"🤖 <b>Pilota Proattivo:</b> {auto}\n"
    text += f"⏰ <i>Aggiornato: {datetime.now().strftime('%H:%M:%S')}</i>"
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

recent_alerts_sent = {}
active_chat_id = None

def proactive_scanner_worker(token):
    """
    Thread autonomo che esegue scansioni continue e SPARA NOTIFICHE PUSH
    su Telegram all'apertura del mercato e ogni volta che individua un setup ad alta confidenza.
    """
    global active_chat_id, recent_alerts_sent
    print("[Proactive Scanner] Avviato thread di monitoraggio autonomo.")
    
    time.sleep(10)
    last_market_open_alert_day = None

    while True:
        try:
            _, env_chat_id, _, _ = load_env()
            target_chat = active_chat_id or env_chat_id
            
            if target_chat and target_chat != "TUO_CHAT_ID":
                now = datetime.now()
                current_day = now.strftime("%Y-%m-%d")
                weekday = now.weekday() # 0 = Lunedì, 4 = Venerdì

                # Notifica di apertura Wall Street (15:30 CET nei giorni feriali)
                if weekday < 5 and now.hour == 15 and 28 <= now.minute <= 35:
                    if last_market_open_alert_day != current_day:
                        last_market_open_alert_day = current_day
                        send_message(token, target_chat, 
                            "🔔 <b>WALL STREET APERTA! (15:30 CET)</b>\n"
                            "Avvio scanner automatico alla ricerca di breakout e pattern 1R.\n"
                            "Se trovo occasioni favorevoli, riceverai subito la notifica qui!"
                        )

                # Esegui scansione di mercato
                api_call("/api/scan", method="POST", payload={
                    "mode": "daily",
                    "symbols": "AAPL,NVDA,MSFT,AMZN,TSLA,RACE,AZN,GOOGL,META"
                })

                # Controlla raccomandazioni
                recs = api_call("/api/recommendations")
                if isinstance(recs, list) and len(recs) > 0:
                    for r in recs:
                        sym = r.get("symbol")
                        conf = r.get("ai_confidence", 0)
                        price = r.get("price", 0.0)
                        
                        last_sent = recent_alerts_sent.get(sym, 0)
                        if conf >= 70 and (time.time() - last_sent > 7200):
                            recent_alerts_sent[sym] = time.time()
                            
                            reasons_text = "\n".join([f"• {x}" for x in r.get("reasons", [])])
                            alert_msg = (
                                f"🚨 <b>NUOVA OPPORTUNITÀ RILEVATA DALL'AI!</b>\n\n"
                                f"🎯 <b>Titolo:</b> {sym}\n"
                                f"💵 <b>Prezzo:</b> ${price:.2f}\n"
                                f"🔥 <b>Affidabilità Algoritmo:</b> {conf}%\n\n"
                                f"<b>Analisi Tecnica:</b>\n{reasons_text}\n\n"
                                f"Vuoi acquistare questo titolo con stop automatico e target 1R?"
                            )
                            markup = {
                                "inline_keyboard": [
                                    [{"text": f"🛒 Conferma Acquisto {sym}", "callback_data": f"buy_{sym}"}],
                                    [{"text": f"🔍 Simula Scenari {sym}", "callback_data": f"sim_{sym}"}]
                                ]
                            }
                            send_message(token, target_chat, alert_msg, markup)
                            print(f"[Proactive Scanner] Notifica inviata per {sym} a chat {target_chat}!")

        except Exception as e:
            print(f"[Proactive Scanner Error] {e}")

        time.sleep(300)

def telegram_bot_worker():
    global active_chat_id
    token, default_chat_id, _, _ = load_env()
    if not token or token == "TUO_TOKEN_TELEGRAM":
        print("[Telegram Bot] Token non configurato nel file .env. Bot in attesa di configurazione.")
        return

    active_chat_id = default_chat_id
    print(f"[Telegram Bot] Avviato con successo per il token: {token[:6]}...!")
    
    if active_chat_id and active_chat_id != "TUO_CHAT_ID":
        send_message(token, active_chat_id, 
            "🟢 <b>DAY TRADER BOT ONLINE SUL RASPBERRY PI</b>\n\n"
            "📍 <b>Host:</b> Raspberry Pi (192.168.1.130:8080)\n"
            "🤖 <b>Scanner Proattivo:</b> ATTIVO (controlla il mercato ogni 5 min)\n"
            "🔔 Ti invierò una notifica automatica appena un titolo supera il 70% di affidabilità!\n\n"
            "Digita /help per la lista comandi o /scan per testare adesso."
        )

    scanner_thread = threading.Thread(target=proactive_scanner_worker, args=(token,), daemon=True)
    scanner_thread.start()

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

                    # Click sui pulsanti inline
                    if "callback_query" in u:
                        cb = u["callback_query"]
                        cb_data = cb.get("data", "")
                        cb_chat = cb["message"]["chat"]["id"]

                        if cb_data.startswith("sim_"):
                            ticker = cb_data.split("_")[1]
                            send_message(token, cb_chat, f"⏳ Calcolo Time Machine per <b>{ticker}</b> (10.000 scenari)...")
                            res = api_call("/api/simulate", method="POST", payload={"ticker": ticker})
                            
                            if res.get("error"):
                                send_message(token, cb_chat, f"⚠️ <b>Errore simulazione {ticker}:</b>\n<code>{res.get('error')}</code>")
                                continue

                            tm = res.get("timemachine") or {}
                            mc = tm.get("mc") or {}
                            plan = res.get("plan") or {}
                            orders = (res.get("orders") or {}).get("orders", [])
                            shares = orders[0].get("qty", 1) if orders else 1

                            if not plan:
                                send_message(token, cb_chat, f"⚠️ Nessun dato di sessione trovato per <b>{ticker}</b>.")
                                continue

                            pt = (mc.get("p_target") or 0) * 100
                            ps = (mc.get("p_stop") or 0) * 100
                            verdict = tm.get("verdict", "Analisi completata")

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

                    # Messaggi di testo
                    if "message" in u and "text" in u["message"]:
                        msg = u["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg["text"].strip()

                        if active_chat_id != chat_id:
                            active_chat_id = chat_id
                            save_chat_id_to_env(chat_id)

                        if text in ["/start", "/help"]:
                            welcome = (
                                "🤖 <b>DAY TRADER BOT AI (Raspberry Pi)</b>\n\n"
                                "Il bot monitora automaticamente il mercato azionario ogni 5 minuti e ti invia notifiche push non appena un titolo soddisfa i criteri di ingresso.\n\n"
                                "Comandi manuali disponibili:\n"
                                "⚡ /scan — Avvia scansione immediata su Wall Street\n"
                                "🎯 /consigliati — I 3 titoli più promettenti in questo momento\n"
                                "📊 /status — Saldo cassa, P&L e stato del bot\n"
                                "💼 /portfolio — Posizioni azionarie aperte\n"
                                "🧪 /test — Simula una notifica di segnale di acquisto\n"
                                "🏛️ /pelosi — Ultimi trade depositati alla Camera USA\n"
                                "🤖 /pilot — Attiva/Disattiva pilota automatico web\n\n"
                                "💡 <i>Puoi anche digitare direttamente il ticker (es. AAPL, NVDA, TSLA) per fare una simulazione rapida!</i>"
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

                        elif text == "/test":
                            sample_text = (
                                "🧪 <b>TEST SEGNALE AUTOMATICO</b>\n\n"
                                "Questo è un test di notifica push autonoma dal Raspberry Pi:\n"
                                "🎯 <b>Titolo:</b> AAPL (Apple Inc.)\n"
                                "💵 <b>Prezzo:</b> $353.68\n"
                                "🔥 <b>Affidabilità:</b> 85% (Setup ORB Breakout confermato)\n"
                                "🪂 <b>Stop Loss:</b> $351.38 | 🎯 <b>Target 1R:</b> $355.98\n\n"
                                "Il canale di comunicazione Telegram è perfettamente funzionante!"
                            )
                            markup = {
                                "inline_keyboard": [
                                    [{"text": "🛒 Simula Acquisto AAPL", "callback_data": "sim_AAPL"}]
                                ]
                            }
                            send_message(token, chat_id, sample_text, markup)

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
                            res = api_call("/api/simulate", method="POST", payload={"ticker": ticker})
                            
                            if res.get("error"):
                                send_message(token, chat_id, f"⚠️ <b>Errore simulazione {ticker}:</b>\n<code>{res.get('error')}</code>")
                                continue

                            tm = res.get("timemachine") or {}
                            mc = tm.get("mc") or {}
                            plan = res.get("plan") or {}
                            orders = (res.get("orders") or {}).get("orders", [])
                            shares = orders[0].get("qty", 1) if orders else 1

                            if not plan:
                                send_message(token, chat_id, f"⚠️ Nessun dato di sessione trovato per <b>{ticker}</b>.")
                                continue

                            pt = (mc.get("p_target") or 0) * 100
                            ps = (mc.get("p_stop") or 0) * 100
                            verdict = tm.get("verdict", "Analisi completata")

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
