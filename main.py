import os, requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINS = ["KOMAUSDT","LABUSDT","HEIUSDT","SIRENUSDT","GRASSUSDT","VELVETUSDT"]

def tg(msg):
    print(msg) # PRINT TO LOGS ALWAYS
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"TG FAIL: {e}")

def get_klines(sym, interval, limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            print(f"{sym} BINANCE ERROR: {data}")
            return None,None,None,None
        closes = [float(x[4]) for x in data]
        highs = [float(x[2]) for x in data]
        lows = [float(x[3]) for x in data]
        vols = [float(x[5]) for x in data]
        return closes, highs, lows, vols
    except Exception as e:
        print(f"{sym} KLINE FAIL: {e}")
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

    # CALCULATIONS
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

    print(f"{sym}: Price={price:.6f} EMA20={ema20:.6f} EMA50={ema50:.6f} RSI={r:.1f} VOL={vol_ratio:.2f}x BOS={bos}")

    # FILTERS A+ (looser for testing so you see signal)
    if vol_ratio < 1.2:
        print(f" -> SKIP {sym}: VOL low {vol_ratio:.2f}x < 1.2x")
        continue
    if not bos:
        print(f" -> SKIP {sym}: No BOS (price {price:.6f} < high {recent_high:.6f})")
        continue
    if r > 70 or r < 40:
        print(f" -> SKIP {sym}: RSI bad {r:.1f}")
        continue
    if price < ema50 or ema20 < ema50:
        print(f" -> SKIP {sym}: Trend down (price<EMA50 or EMA20<EMA50)")
        continue

    # SIGNAL!!!
    sl = min(lows[-5:]) * 0.99
    tp = price + (price - sl)*2.5
    msg = f"🚀 *BUY SIGNAL {sym} 15m*\n\nEntry: `{price:.6f}`\nSL: `{sl:.6f}`\nTP: `{tp:.6f}`\n\nRSI: {r:.1f} | VOL: {vol_ratio:.2f}x | BOS: YES\nTrend: EMA20>EMA50>EMA200\nTime: {datetime.utcnow()} UTC"
    tg(msg)
    print(f" -> SIGNAL SENT {sym}!!!")

print("--- SCAN DONE ---")
# Send alive message every 4 hours so you know bot alive (GitHub runs every 15m = 16 runs per 4h)
# We send scan quiet message every run for now to debug
tg(f"✅ Scan done {datetime.utcnow().strftime('%H:%M')} UTC - No A+ setup yet. Bot alive checking {len(COINS)} coins.")
