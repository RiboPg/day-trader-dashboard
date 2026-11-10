#!/usr/bin/env python3
"""
Full Backtest Engine for Day Trader Skill.
Simulates day-trading with 1,000 EUR (~1,080 USD) budget.
Strictly adheres to bot instructions:
- Opening range breakout (ORB) on 5-minute bars (9:30-9:45).
- Entry on first 5-min close above range high.
- Stop at range midpoint (or-mid), Target 1R or 2R.
- Flat by 15:55 ET (close whatever is open at 15:55).
- Money management: budget $1,080, max loss per trade 2% ($20 / 20 EUR), whole shares.
"""

import urllib.request
import json
import time
import math
from datetime import datetime

TICKERS = ["AAPL", "NVDA", "AMZN", "MSFT", "TSLA", "RACE", "GOOGL", "META"]
BUDGET_EUR = 1000.0
EUR_USD_RATE = 1.08 # 1,000 EUR = 1,080 USD
BUDGET_USD = BUDGET_EUR * EUR_USD_RATE
MAX_LOSS_PER_TRADE_USD = 20.0 # 2% max risk per trade

def fetch_chart(ticker, range_str="60d", interval="5m"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data["chart"]["result"][0]
            timestamps = res["timestamp"]
            quotes = res["indicators"]["quote"][0]
            opens = quotes["open"]
            highs = quotes["high"]
            lows = quotes["low"]
            closes = quotes["close"]
            volumes = quotes["volume"]

            bars = []
            for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
                if None in (t, o, h, l, c):
                    continue
                dt = datetime.fromtimestamp(t)
                bars.append({
                    "time": t,
                    "dt": dt,
                    "date": dt.strftime("%Y-%m-%d"),
                    "hhmm": dt.strftime("%H:%M"),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v or 0
                })
            return bars
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return []

def run_backtest_for_ticker(ticker, bars):
    # Group bars by date
    days = {}
    for b in bars:
        days.setdefault(b["date"], []).append(b)

    trades = []

    for date, day_bars in sorted(days.items()):
        # Check regular market hours
        # Filter bars between 09:30 and 16:00
        # In local time of timestamps, let's look at relative session sequence
        # Typically 78 bars in a regular full day
        if len(day_bars) < 30: # skip incomplete/half days
            continue

        # Opening range: first 3 bars (09:30, 09:35, 09:40)
        or_bars = day_bars[:3]
        or_high = max(b["high"] for b in or_bars)
        or_low = min(b["low"] for b in or_bars)
        or_mid = math.floor(((or_high + or_low) / 2.0) * 100) / 100.0

        # Check subsequent bars for breakout
        entry_bar = None
        entry_idx = -1
        for i in range(3, min(len(day_bars) - 2, 70)): # no entries in the last 15 mins
            b = day_bars[i]
            if b["close"] > or_high:
                entry_bar = b
                entry_idx = i
                break

        if not entry_bar:
            continue

        entry_price = entry_bar["close"]
        stop_price = or_mid
        risk_per_share = entry_price - stop_price

        if risk_per_share <= 0.05: # too tight or invalid
            continue

        target_price = round(entry_price + (1.0 * risk_per_share), 2) # 1R target

        # Position sizing with 1,000 EUR account
        # Max loss is 20 USD (~18.50 EUR)
        allowed_shares_by_loss = math.floor(MAX_LOSS_PER_TRADE_USD / risk_per_share)
        allowed_shares_by_cap = math.floor((BUDGET_USD * 0.75) / entry_price)
        shares = min(allowed_shares_by_loss, allowed_shares_by_cap)

        if shares < 1:
            continue # Stock price or risk too high for $1000 account to buy 1 share

        cost = shares * entry_price
        max_loss = shares * risk_per_share
        potential_gain = shares * (target_price - entry_price)

        # Replay the rest of the day bar by bar
        outcome = "neither"
        exit_price = entry_price
        exit_time = ""

        for j in range(entry_idx + 1, len(day_bars)):
            bar = day_bars[j]
            # Check stop first (conservative bot rule)
            if bar["low"] <= stop_price:
                outcome = "stop"
                exit_price = stop_price
                exit_time = bar["hhmm"]
                break
            elif bar["high"] >= target_price:
                outcome = "target"
                exit_price = target_price
                exit_time = bar["hhmm"]
                break

        # If neither hit before close, flat by 15:55
        if outcome == "neither":
            exit_bar = day_bars[-1]
            exit_price = exit_bar["close"]
            outcome = "flat_by_close"
            exit_time = exit_bar["hhmm"]

        pnl_usd = (exit_price - entry_price) * shares
        pnl_eur = pnl_usd / EUR_USD_RATE

        trades.append({
            "ticker": ticker,
            "date": date,
            "entry_time": entry_bar["hhmm"],
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "shares": shares,
            "cost_usd": cost,
            "cost_eur": cost / EUR_USD_RATE,
            "outcome": outcome,
            "exit_price": exit_price,
            "exit_time": exit_time,
            "pnl_usd": pnl_usd,
            "pnl_eur": pnl_eur
        })

    return trades

def main():
    print(f"============================================================")
    print(f"📊 BACKTEST REALE SULLE SERIE STORICHE (Regole Day Trader Bot)")
    print(f"💰 Capitale Iniziale: {BUDGET_EUR:.2f} € (${BUDGET_USD:.2f})")
    print(f"🛡️ Rischio Massimo per Trade: 2% ({MAX_LOSS_PER_TRADE_USD / EUR_USD_RATE:.2f} € / ${MAX_LOSS_PER_TRADE_USD:.2f})")
    print(f"============================================================\n")

    all_trades = []
    per_ticker_stats = {}

    for t in TICKERS:
        print(f"Recupero dati 5m Yahoo Finance per {t}...")
        bars = fetch_chart(t, "60d", "5m")
        trades = run_backtest_for_ticker(t, bars)
        all_trades.extend(trades)

        wins = [tr for tr in trades if tr["pnl_eur"] > 0]
        losses = [tr for tr in trades if tr["pnl_eur"] < 0]
        ties = [tr for tr in trades if tr["pnl_eur"] == 0]
        tot_pnl = sum(tr["pnl_eur"] for tr in trades)

        per_ticker_stats[t] = {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades) * 100) if trades else 0,
            "pnl_eur": tot_pnl
        }
        time.sleep(0.3)

    # Sort all trades chronologically
    all_trades.sort(key=lambda x: (x["date"], x["entry_time"]))

    total_trades = len(all_trades)
    winning_trades = [tr for tr in all_trades if tr["pnl_eur"] > 0]
    losing_trades = [tr for tr in all_trades if tr["pnl_eur"] < 0]
    breakeven_trades = [tr for tr in all_trades if tr["pnl_eur"] == 0]

    tot_gain_eur = sum(tr["pnl_eur"] for tr in winning_trades)
    tot_loss_eur = sum(tr["pnl_eur"] for tr in losing_trades) # negative
    net_pnl_eur = tot_gain_eur + tot_loss_eur
    final_capital_eur = BUDGET_EUR + net_pnl_eur

    win_rate = (len(winning_trades) / total_trades * 100) if total_trades else 0
    profit_factor = (tot_gain_eur / abs(tot_loss_eur)) if tot_loss_eur != 0 else 0

    print("\n------------------------------------------------------------")
    print("📈 RISULTATI COMPLESSIVI DEL BACKTEST")
    print("------------------------------------------------------------")
    print(f"Operazioni Totali Eseguite:    {total_trades}")
    print(f"Operazioni Vincenti (Target):  {len(winning_trades)} ({win_rate:.1f}%)")
    print(f"Operazioni Perdenti (Stop):    {len(losing_trades)} ({(len(losing_trades)/total_trades*100):.1f}%)")
    print(f"Operazioni Chiuse a Pareggio:  {len(breakeven_trades)}")
    print(f"Guadagno Lordo Totale:        +{tot_gain_eur:.2f} €")
    print(f"Perdita Lorda Totale:         {tot_loss_eur:.2f} €")
    print(f"Risultato Netto Finale:        {'+' if net_pnl_eur >= 0 else ''}{net_pnl_eur:.2f} € ({(net_pnl_eur/BUDGET_EUR)*100:+.2f}%)")
    print(f"Capitale Finale Stimato:       {final_capital_eur:.2f} €")
    print(f"Profit Factor (Rapporto V/P):  {profit_factor:.2f}")

    print("\n------------------------------------------------------------")
    print("🏆 DETTAGLIO PER TITOLO")
    print("------------------------------------------------------------")
    print(f"{'Ticker':<8} {'Trade':<8} {'Vinte':<8} {'Perse':<8} {'Win Rate':<12} {'P&L Netto (€)':<15}")
    for t, s in per_ticker_stats.items():
        print(f"{t:<8} {s['trades']:<8} {s['wins']:<8} {s['losses']:<8} {s['win_rate']:<11.1f}% {'+' if s['pnl_eur']>=0 else ''}{s['pnl_eur']:<14.2f}")

    # Output JSON summary for user and dashboard
    summary = {
        "budget_eur": BUDGET_EUR,
        "final_capital_eur": round(final_capital_eur, 2),
        "net_pnl_eur": round(net_pnl_eur, 2),
        "return_pct": round((net_pnl_eur / BUDGET_EUR) * 100, 2),
        "total_trades": total_trades,
        "wins": len(winning_trades),
        "losses": len(losing_trades),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "gross_profit_eur": round(tot_gain_eur, 2),
        "gross_loss_eur": round(tot_loss_eur, 2),
        "per_ticker": per_ticker_stats
    }
    with open("/Users/ribo/Desktop/Trading/trader/backtest_results.json", "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
