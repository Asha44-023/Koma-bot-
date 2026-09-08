import ccxt, requests, os, numpy as np, pandas as pd
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"TG Error: {e}")

def rsi_calc(closes, period=14):
    delta = np.diff(closes); gain = np.where(delta>0, delta, 0); loss = np.where(delta<0, -delta, 0)
    avg_gain = np.mean(gain[-period:]); avg_loss = np.mean(loss[-period:])
    if avg_loss == 0: return 70
    rs = avg_gain / avg_loss; return 100 - (100 / (1 + rs))

def ema_calc(closes, period): return pd.Series(closes).ewm(span=period).mean().iloc[-1]

symbols = ["HEI/USDT", "LAB/USDT", "SIREN/USDT", "GRASS/USDT", "KOMA/USDT", "VELVET/USDT"]
send_telegram("⚡ *BOSS 5-15-60-240 CLEAN SETUP STARTED*")

for sym in symbols:
    try:
        ex = ccxt.mexc()
        # === FETCH 4 TIMEFRAMES ===
        o5 = ex.fetch_ohlcv(sym, '5m', limit=100)
        o15 = ex.fetch_ohlcv(sym, '15m', limit=100)
        o1h = ex.fetch_ohlcv(sym, '1h', limit=100)
        o4h = ex.fetch_ohlcv(sym, '4h', limit=100)

        c5 = [x[4] for x in o5]; v5 = [x[5] for x in o5]
        c15 = [x[4] for x in o15]; v15 = [x[5] for x in o15]
        price = c15[-1]

        rsi5 = rsi_calc(np.array(c5)); rsi15 = rsi_calc(np.array(c15))
        ema9 = ema_calc(c15, 9); ema21 = ema_calc(c15, 21); ema50 = ema_calc(c15, 50)

        avg_vol = np.mean(v15[-20:]); vol_spike = v15[-1] / avg_vol if avg_vol>0 else 1
        vol_trend = "INCREASING" if np.mean(v15[-5:]) > np.mean(v15[-10:-5]) else "DECREASING"
        vol_loophole = vol_spike >= 1.0 and vol_trend == "INCREASING"

        high_20 = max(c15[-20:-1]); low_20 = min(c15[-20:-1])
        bos_up_real = price > high_20; bos_down_real = price < low_20
        bos_up_loophole = price > high_20 * 0.995; bos_down_loophole = price < low_20 * 1.005

        w_pat = c15[-1] > c15[-2] and c15[-2] < c15[-3]
        m_pat = c15[-1] < c15[-2] and c15[-2] > c15[-3]
        double_bottom_loophole = abs(c15[-2] - c15[-4]) / c15[-2] < 0.02 and c15[-2] < c15[-3]
        double_top_loophole = abs(c15[-2] - c15[-4]) / c15[-2] < 0.02 and c15[-2] > c15[-3]

        # === BOSS STRUCTURE ===
        t4h = "UP" if o4h[-1][4] > o4h[-20][4] else "DOWN"
        high_1h_20 = max([x[4] for x in o1h[-20:-1]]); low_1h_20 = min([x[4] for x in o1h[-20:-1]])
        if o1h[-1][4] > high_1h_20: s1h = "BOS UP"
        elif o1h[-1][4] < low_1h_20: s1h = "BOS DOWN"
        else: s1h = "RANGE"

        atr = np.mean([abs(o15[i][2]-o15[i][3]) for i in range(-14, 0)]); atr = atr if atr!=0 else price*0.01
        sl_l = price - atr*1.5; tp1_l, tp2_l, tp3_l = price + atr*1.2, price + atr*2.5, price
