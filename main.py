import ccxt
import requests
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

# =========== SOLID SETTINGS - 3-5 MSGS/DAY ===========
SCAN_INTERVAL = 15 * 60 # 15 min scan
MIN_SCORE = 68 # Only SOLID 68+ (was 65)
COOLDOWN_HOURS = 2 # No repeat same coin for 2h
LAST_ALERT = {} # Cooldown memory
# ===================================================

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

def get_btc_dump():
    """Check if BTC is dumping - don't buy if it is"""
    try:
        btc = ex.fetch_ohlcv("BTC/USDT", '1h', limit=2)
        change = ((btc[-1][4] - btc[-2][4]) / btc[-2][4]) * 100
        return change
    except:
        return 0

def can_alert(sym):
    """2h Cooldown per coin"""
    now = datetime.now()
    if sym in LAST_ALERT:
        if now - LAST_ALERT[sym] < timedelta(hours=COOLDOWN_HOURS):
            return False
    LAST_ALERT[sym] = now
    return True

# ==================== MAIN LOOP ====================
tg("🚀 SOLID PRO STARTED - 3-5 Msgs/Day - Trend Lock ON")

while True:
    btc_change = get_btc_dump()
    btc_status = f"BTC {btc_change:+.1f}%"
    if btc_change < -1.5:
        print(f"BTC dumping {btc_change}%, skipping buys this scan")

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
            e50_1h = ema([x[4] for x in o1h], 50)

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

            # Check real dump - need 2 candles below EMA, not wick
            last_2_below = o1h[-1][4] < e50_1h and o1h[-2][4] < e50_1h

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

            sl_buy = price * 0.93
            tp1_buy = price * 1.08
            tp2_buy = price * 1.15
            sl_sell = price * 1.07
            tp1_sell = price * 0.92
            tp2_sell = price * 0.85

            # =========== SOLID FILTER - CORRECT PATTERNS ===========
            if buy >= MIN_SCORE:
                # TREND LOCK for BUY
                if price < e50_1
