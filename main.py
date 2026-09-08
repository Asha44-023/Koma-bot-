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
    try:
        d = np.diff(c)
        g = np.where(d>0, d, 0)
        l = np.where(d<0, -d, 0)
        ag = np.mean(g[-p:])
        al = np.mean(l[-p:])
        if al == 0:
            return 50
        rs = ag / al
        return 100 - (100 / (1 + rs))
    except:
        return 50

def ema(c, p):
    try:
        return pd.Series(c).ewm(span=p).mean().iloc[-1]
    except:
        return c[-1]

ex = ccxt.mexc()
syms = ["HEI/USDT","LAB/USDT","SIREN/USDT","GRASS/USDT","KOMA/USDT"]

tg("🚀 SCAN PRO STARTED - TP/SL Edition")

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

        avg_vol = np.mean(v15[-20:]) if len(v15)>=20 else 1
        vol = v15[-1] / avg_vol if avg_vol>0 else 1.0

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

        if vol >= 1.1:
            buy += 10
            sell += 10

        if bos == "BOS UP":
            buy += 25
        if bos == "BOS DOWN":
            sell += 25

        if trend == "UP":
            buy += 15
        if trend == "DOWN":
            sell += 15

        # TP SL
        sl_buy = price * 0.93
        tp1_buy = price * 1.08
        tp2_buy = price * 1.15

        sl_sell = price * 1.07
        tp1_sell = price * 0.92
        tp2_sell = price * 0.85

        if buy >= 65:
            tg(f"🟢 BUY {sym} {buy}/100\nPrice ${price:.6f} RSI {r:.0f}\n{bos} 4H {trend} VOL x{vol:.1f}\nSL ${sl_buy:.6f} TP1 ${tp1_buy:.6f} TP2 ${tp2_buy:.6f}")
        elif sell >= 65:
            tg(f"🔴 SELL {sym} {sell}/100\nPrice ${price:.6f} RSI {r:.0f}\n{bos} 4H {trend} VOL x{vol:.1f}\nSL ${sl_sell:.6f} TP1 ${tp1_sell:.6f} TP2 ${tp2_sell:.6f}")
        else:
            tg(f"⚪ SKIP {sym} B{buy} S{sell} RSI {r:.0f} VOL x{vol:.1f}")

    except Exception as e:
        print(f"Error {sym}: {e}")
        continue

tg("✅ PRO SCAN DONE")
