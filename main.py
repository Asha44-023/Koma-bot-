import ccxt
import requests
import os
import numpy as np
import pandas as pd

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

def tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id": CHAT, "text": m}, timeout=10)
    except:
        pass

def rsi(c, p=14):
    d = np.diff(c)
    g = np.where(d>0, d, 0)
    l = np.where(d<0, -d, 0)
    ag = np.mean(g[-p:])
    al = np.mean(l[-p:])
    if al == 0:
        return 70
    rs = ag / al
    return 100 - (100 / (1 + rs))

def ema(c, p):
    return pd.Series(c).ewm(span=p).mean().iloc[-1]

ex = ccxt.mexc()
syms = ["HEI/USDT","LAB/USDT","SIREN/USDT","GRASS/USDT","KOMA/USDT"]

tg("🚀 MEXC SCAN STARTED - Fixed Version")

for sym in syms:
    try:
        o15 = ex.fetch_ohlcv(sym, '15m', limit=100)
        o1h = ex.fetch_ohlcv(sym, '1h', limit=100)
        o4h = ex.fetch_ohlcv(sym, '4h', limit=100)

        c15 = [x[4] for x in o15]
        v15 = [x[5] for x in o15]
        price = c15[-1]

        r = rsi(np.array(c15))
        e9 = ema(c15, 9)
        e21 = ema(c15, 21)
        vol = v15[-1] / np.mean(v15[-20:])

        trend = "UP" if o4h[-1][4] > o4h[-20][4] else "DOWN"
        h1 = max([x[4] for x in o1h[-20:-1]])
        l1 = min([x[4] for x in o1h[-20:-1]])

        if o1h[-1][4] > h1:
            bos = "BOS UP"
        elif o1h[-1][4] < l1:
            bos = "BOS DOWN"
        else:
            bos = "RANGE"

        buy = 0
        sell = 0

        if e9 > e21:
            buy += 30
        else:
            sell += 30

        if 45 < r < 68:
            buy += 20
        if 32 < r < 55:
            sell += 20

        if vol >= 1.2:
            buy += 15
            sell += 15

        if bos == "BOS UP":
            buy += 20
        if bos == "BOS DOWN":
            sell += 20

        if trend == "UP":
            buy += 15
        if trend == "DOWN":
            sell += 15

        if buy >= 65:
            tg(f"🟢 BUY {sym} {buy}/100 Price ${price:.6f} RSI {r:.0f} {bos} 4H {trend} VOL x{vol:.1f}")
        elif sell >= 65:
            tg(f"🔴 SELL {sym} {sell}/100 Price ${price:.6f} RSI {r:.0f} {bos} 4H {trend} VOL x{vol:.1f}")
        else:
            tg(f"⚪ SKIP {sym} BUY {buy} SELL {sell} RSI {r:.0f}")

    except Exception as e:
        print(f"Error {sym}: {e}")
        continue

tg("✅ SCAN DONE")
