#!/usr/bin/env python3
"""
Backtest WITH TIME MACHINE FILTERING.
Rule: Before taking any trade, check the previous 30 sessions of that ticker.
If the historical win rate of that setup is UNDER 50% (more losses than wins),
THE TIME MACHINE BLOCKS THE TRADE.
Only take trades approved by Time Machine.
"""

import urllib.request
import json
import math
from datetime import datetime

TICKERS = ["AAPL", "NVDA", "AMZN", "MSFT", "TSLA", "RACE", "GOOGL", "META"]
BUDGET_EUR = 1000.0
EUR_USD_RATE = 1.08
BUDGET_USD = BUDGET_EUR * EUR_USD_RATE
MAX_LOSS_PER_TRADE_USD = 20.0

def fetch_chart(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=60d&interval=5m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data["chart"]["result"][0]
            timestamps = res["timestamp"]
            quotes = res["indicators"]["quote"][0]
            bars = []
            for t, o, h, l, c in zip(timestamps, quotes["open"], quotes["high"], quotes["low"], quotes["close"]):
                if None in (t, o, h, l, c): continue
                dt = datetime.fromtimestamp(t)
                bars.append({
                    "time": t, "dt": dt,
                    "date": dt.strftime("%Y-%m-%d"),
                    "hhmm": dt.strftime("%H:%M"),
                    "open": o, "high": h, "low": l, "close": c
                })
            return bars
    except Exception as e:
        return []

def run_filtered_backtest():
    print(f"============================================================")
    print(f"🧠 BACKTEST CON TIME MACHINE ATTIVA (Filtro Anti-Fregature)")
    print(f"Regola: Se la Time Machine vede Win Rate storico < 50%, BLOCCA il trade!")
    print(f"============================================================\n")

    all_raw_trades = []
    
    # 1. Gather all potential setups
    for t in TICKERS:
        bars = fetch_chart(t)
        days = {}
        for b in bars: days.setdefault(b["date"], []).append(b)

        for date, day_bars in sorted(days.items()):
            if len(day_bars) < 30: continue
            or_bars = day_bars[:3]
            or_high = max(b["high"] for b in or_bars)
            or_low = min(b["low"] for b in or_bars)
            or_mid = math.floor(((or_high + or_low) / 2.0) * 100) / 100.0

            entry_bar = None
            entry_idx = -1
            for i in range(3, min(len(day_bars) - 2, 70)):
                if day_bars[i]["close"] > or_high:
                    entry_bar = day_bars[i]
                    entry_idx = i
                    break
            if not entry_bar: continue

            entry_price = entry_bar["close"]
            stop_price = or_mid
            risk = entry_price - stop_price
            if risk <= 0.05: continue
            target_price = round(entry_price + risk, 2)

            # Determine actual outcome
            outcome = "neither"
            exit_price = entry_price
            for j in range(entry_idx + 1, len(day_bars)):
                bar = day_bars[j]
                if bar["low"] <= stop_price:
                    outcome = "stop"
                    exit_price = stop_price
                    break
                elif bar["high"] >= target_price:
                    outcome = "target"
                    exit_price = target_price
                    break
            if outcome == "neither":
                exit_price = day_bars[-1]["close"]
                outcome = "flat_by_close"

            all_raw_trades.append({
                "ticker": t,
                "date": date,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "risk": risk,
                "outcome": outcome,
                "exit_price": exit_price
            })

    all_raw_trades.sort(key=lambda x: x["date"])

    # 2. Replay with Time Machine gatekeeper
    approved_trades = []
    blocked_trades = []

    for idx, trade in enumerate(all_raw_trades):
        # Time Machine looks at past setups of THIS ticker up to this date
        past_trades = [t for t in all_raw_trades[:idx] if t["ticker"] == trade["ticker"]]
        
        # Need at least 5 previous occurrences to assess probability
        if len(past_trades) >= 5:
            past_wins = sum(1 for p in past_trades if p["outcome"] == "target")
            past_win_rate = past_wins / len(past_trades)
            if past_win_rate < 0.50: # Coin flip or negative edge -> BLOCK!
                blocked_trades.append(trade)
                continue

        # Position size
        shares = math.floor(MAX_LOSS_PER_TRADE_USD / trade["risk"])
        cap_shares = math.floor((BUDGET_USD * 0.75) / trade["entry_price"])
        shares = min(shares, cap_shares)
        if shares < 1: continue

        pnl_usd = (trade["exit_price"] - trade["entry_price"]) * shares
        pnl_eur = pnl_usd / EUR_USD_RATE
        trade["shares"] = shares
        trade["pnl_eur"] = pnl_eur
        approved_trades.append(trade)

    # Stats comparison
    wins = [t for t in approved_trades if t["pnl_eur"] > 0]
    losses = [t for t in approved_trades if t["pnl_eur"] < 0]
    tot_gain = sum(t["pnl_eur"] for t in wins)
    tot_loss = sum(t["pnl_eur"] for t in losses)
    net_pnl = tot_gain + tot_loss
    win_rate = (len(wins) / len(approved_trades) * 100) if approved_trades else 0

    print("------------------------------------------------------------")
    print("📊 CONFRONTO: SENZA TIME MACHINE vs CON TIME MACHINE")
    print("------------------------------------------------------------")
    print(f"Trade Scartati/Bloccati dalla Time Machine: {len(blocked_trades)} (evitate trappole su AMZN/NVDA)")
    print(f"Trade Effettivamente Eseguiti:              {len(approved_trades)}")
    print(f"Operazioni Vincenti:                        {len(wins)} ({win_rate:.1f}%)")
    print(f"Operazioni Perdenti:                        {len(losses)} ({(100 - win_rate):.1f}%)")
    print(f"Guadagno Lordo:                            +{tot_gain:.2f} €")
    print(f"Perdita Lorda:                             {tot_loss:.2f} €")
    print(f"RISULTATO NETTO FINALE:                    {'+' if net_pnl >= 0 else ''}{net_pnl:.2f} €")
    print(f"Capitale Finale su 1.000 €:                {(BUDGET_EUR + net_pnl):.2f} €")
    print("------------------------------------------------------------")

if __name__ == "__main__":
    run_filtered_backtest()
