import os, requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINS = ["KOMAUSDT","LABUSDT","HEIUSDT","SIRENUSDT","GRASSUSDT","VELVETUSDT"]

def tg(msg):
    print(msg)
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"TG FAIL: {e}")

def get_klines(sym, interval, limit=200):
    # 1. BYBIT - BEST, NEVER BLOCKED
    try:
        by_interval = interval.replace("m","")
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval={by_interval}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        data = r.get("result",{}).get("list",[])
        if data and len(data)>50:
            data = data[::-1]
            closes = [float(x[4]) for x in data]
            highs = [float(x[2]) for x in data]
            lows = [float(x[3]) for x in data]
            vols = [float(x[5]) for x in data]
            print(f"{sym}: OK Bybit {len(closes)} candles")
            return closes, highs, lows, vols
    except Exception as e:
        print(f"{sym} Bybit fail: {e}")

    # 2. OKX - 2nd BEST
    try:
        okx_sym = sym.replace("USDT","-USDT")
        url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={interval}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        data = r.get("data",[])
        if data and len(data)>50:
            data = data[::-1]
            closes = [float(x[4]) for x in data]
            highs = [float(x[2]) for x in data]
            lows = [float(x[3]) for x in data]
            vols = [float(x[5]) for x in data]
            print(f"{sym}: OK OKX {len(closes)} candles")
            return closes, highs, lows, vols
    except Exception as e:
        print(f"{sym} OKX fail: {e}")

    # 3. BINANCE VISION - Unblocked binance
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        if isinstance(data, list) and len(data)>50:
            closes = [float(x[4]) for x in data]
            highs = [float(x[2]) for x in data]
            lows = [float(x[3]) for x in data]
            vols = [float(x[5]) for x in data]
            print(f"{sym}: OK BinanceVision {len(closes)} candles")
            return closes, highs, lows, vols
    except Exception as e:
        print(f"{sym} Vision fail: {e}")

    print(f"{sym}: ALL FAILED")
    return None,None,None,None

def ema(arr, period):
    k = 2/(period+1)
    e = arr[0]
    for p in arr[1:]: e = p*k + e*(1-k)
    return e

def rsi(arr, period=14):
    if len(arr) < period+1: return 50
    gains=[]; losses=[]
    for i in range(1, period+1):
        diff = arr[-i] - arr[-i-1]
        gains.append(max(diff,0)); losses.append(max(-diff,0))
    avg_g = sum(gains)/period; avg_l = sum(losses)/period
    if avg_l == 0: return 75
    rs = avg_g/avg_l
    return 100 - (100/(1+rs))

print(f"--- BOT START {datetime.utcnow()} UTC ---")
print(f"TOKEN SET? {bool(TOKEN)} CHAT_ID SET? {bool(CHAT_ID)}")

for sym in COINS:
    closes, highs, lows, vols = get_klines(sym, "15m", 200)
    if closes is None:
        print(f"{sym}: SKIP - No data")
        continue

    price = closes[-1]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    r = rsi(closes, 14)
    avg_vol = sum(vols[-20:-1])/19 if len(vols)>20 else 1
    cur_vol = vols[-1]
    vol_ratio = cur_vol / avg_vol if avg_vol>0 else 0
    recent_high = max(highs[-20:-1])
    bos = price > recent_high

    print(f"{sym}: P={price:.6f} EMA20={ema20:.6f} EMA50={ema50:.6f} RSI={r:.1f} VOL={vol_ratio:.2f}x BOS={bos}")

    if vol_ratio < 1.2:
        print(f" -> SKIP VOL {vol_ratio:.2f}x")
        continue
    if not bos:
        print(f" -> SKIP No BOS")
        continue
    if r > 70 or r < 38:
        print(f" -> SKIP RSI {r:.1f}")
        continue
    if price < ema50 or ema20 < ema50:
        print(f" -> SKIP Trend Down")
        continue

    sl = min(lows[-5:]) * 0.99
    tp = price + (price - sl)*2.5
    msg = f"🚀 *BUY {sym} 15m*\n\nEntry: `{price:.6f}`\nSL: `{sl:.6f}`\nTP: `{tp:.6f}`\n\nRSI: {r:.1f} | VOL: {vol_ratio:.2f}x | BOS: YES\nTime: {datetime.utcnow()} UTC"
    tg(msg)
    print(f" -> SIGNAL SENT {sym}!!!")

print("--- SCAN DONE ---")
tg(f"✅ Scan done {datetime.utcnow().strftime('%H:%M')} UTC - Checked {len(COINS)} coins (Bybit/OKX). No A+ yet.")
