import ccxt
import requests
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
MIN_SCORE = 68
COOLDOWN_HOURS = 2
COOLDOWN_FILE = "last_alerts.json"

def tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id": CHAT, "text": m}, timeout=10)
    except:
        pass

def load_cooldown():
    try:
        with open(COOLDOWN_FILE, "r") as f:
            data = json.load(f)
            return {k: datetime.fromisoformat(v) for k, v in data.items()}
    except:
        return {}

def save_cooldown(d):
    try:
        with open(COOLDOWN_FILE, "w") as f:
            json.dump({k: v.isoformat() for k, v in d.items()}, f)
    except:
        pass

def rsi(c, p=14):
    try:
        d = np.diff(c)
        g = np.where(d > 0, d, 0)
        l = np.where(d < 0, -d, 0)
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
syms = ["HEI/USDT", "LAB/USDT", "SIREN/USDT", "GRASS/USDT", "KOMA/USDT"]
LAST = load_cooldown()

def can_alert(s):
    now = datetime.now()
    if s in LAST:
        if now - LAST[s] < timedelta(hours=COOLDOWN_HOURS):
            return False
    LAST[s] = now
    return True

try:
    btc = ex.fetch_ohlcv("BTC/USDT", "1h", limit=2)
    btc_ch = ((btc[-1][4] - btc[-2][4]) / btc[-2][4]) * 100
except:
    btc_ch = 0

for sym in syms:
    try:
        o15 = ex.fetch_ohlcv(sym, "15m", limit=100)
        o1h = ex.fetch_ohlcv(sym, "1h", limit=100)
        o4h = ex.fetch_ohlcv(sym, "4h", limit=100)

        c15 = [x[4] for x in o15]
        v15 = [x[5] for x in o15]
        price = c15[-1]

        r = rsi(np.array(c15))
        e9 = ema(c15, 9)
        e21 = ema(c15, 21)
        e50_1h = ema([x[4] for x in o1h], 50)

        avg = np.mean(v15[-20:]) if len(v15) >= 20 else 1
        vol = v15[-1] / avg if avg > 0 else 1.0

        trend = "UP" if o4h[-1][4] > o4h[-20][4] else "DOWN"
        h1 = max([x[4] for x in o1h[-20:-1]])
        l1 = min([x[4] for x in o1h[-20:-1]])

        if o1h[-1][4] > h1:
            bos = "BOS UP"
        elif o1h[-1][4] < l1:
            bos = "BOS DOWN"
        else:
            bos = "RANGE"

        last2 = o1h[-1][4] < e50_1h and o1h[-2][4] < e50_1h

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

        slb = price * 0.93
        tp1b = price * 1.08
        tp2b = price * 1.15
        sls = price * 1.07
        tp1s = price * 0.92
        tp2s = price * 0.85

        if buy >= MIN_SCORE:
            if price < e50_1h:
                continue
            if btc_ch < -1.5:
                continue
            if r > 68:
                continue
            if not can_alert(sym):
                continue
            tg(f"🟢 BUY {sym} {buy}/100\nPrice ${price:.6f} RSI {r:.0f}\n{bos} 4H {trend} VOL x{vol:.1f} BTC {btc_ch:+.1f}%\nSL ${slb:.6f} TP1 ${tp1b:.6f} TP2 ${tp2b:.6f}\nSOLID ✅")

        elif sell >= MIN_SCORE:
            if not (last2 or r >= 72):
                continue
            if not can_alert(sym):
                continue
            tg(f"🔴 SELL {sym} {sell}/100\nPrice ${price:.6f} RSI {r:.0f}\n{bos} 4H {trend} VOL x{vol:.1f} BTC {btc_ch:+.1f}%\nSL ${sls:.6f} TP1 ${tp1s:.6f} TP2 ${tp2s:.6f}\nSOLID ✅")

    except Exception as e:
        print(f"Error {sym}: {e}")
        continue

save_cooldown(LAST)
print("Scan done")
