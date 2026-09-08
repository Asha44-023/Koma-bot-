import requests
import os
from datetime import datetime

# === CONFIG ===
COINS = ["KOMAUSDT", "LABUSDT", "HEIUSDT", "SIRENUSDT", "GRASSUSDT", "VELVETUSDT"]
INTERVAL = "15m"
LIMIT = 200

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if not TOKEN or not CHAT_ID:
        print("Telegram not set")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
        print("Telegram sent!")
    except Exception as e:
        print(f"Telegram fail: {e}")

def calc_ema(data, period):
    if len(data) < period: return sum(data)/len(data)
    k = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for price in data[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def calc_rsi(data, period=14):
    if len(data) < period+1: return 50
    gains = 0
    losses = 0
    for i in range(1, period+1):
        diff = data[-i] - data[-i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

# === WIDE 6 EXCHANGE SEARCH - NEVER BLOCKED ===
def get_klines(sym, interval, limit=200):
    headers = {"User-Agent": "Mozilla/5.0"}
    # 1. MEXC
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        r = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(r, list) and len(r)>50:
            print(f"{sym}: OK MEXC {len(r)}")
            return [float(x[4]) for x in r], [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[5]) for x in r]
    except: pass
    # 2. OKX
    try:
        okx_sym = sym.replace("USDT","-USDT")
        url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar={interval}&limit={limit}"
        r = requests.get(url, headers=headers, timeout=10).json()
        data = r.get("data",[])
        if data and len(data)>50:
            data = data[::-1]
            print(f"{sym}: OK OKX {len(data)}")
            return [float(x[4]) for x in data], [float(x[2]) for x in data], [float(x[3]) for x in data], [float(x[5]) for x in data]
    except: pass
    # 3. GATE.IO
    try:
        gate_sym = sym.replace("USDT","_USDT")
        url = f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={gate_sym}&interval={interval}&limit={limit}"
        r = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(r, list) and len(r)>50:
            r = r[::-1]
            print(f"{sym}: OK GATE {len(r)}")
            return [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[4]) for x in r], [float(x[5]) for x in r]
    except: pass
    # 4. KUCOIN
    try:
        ku_sym = sym.replace("USDT","-USDT")
        k_interval = "15min" if interval=="15m" else interval
        url = f"https://api.kucoin.com/api/v1/market/candles?type={k_interval}&symbol={ku_sym}&startAt=0"
        r = requests.get(url, headers=headers, timeout=10).json()
        data = r.get("data",[])
        if data and len(data)>50:
            data = data[::-1]
            print(f"{sym}: OK KUCOIN {len(data)}")
            return [float(x[2]) for x in data], [float(x[3]) for x in data], [float(x[4]) for x in data], [float(x[5]) for x in data]
    except: pass
    # 5. BINANCE VISION
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        r = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(r, list) and len(r)>50:
            print(f"{sym}: OK VISION {len(r)}")
            return [float(x[4]) for x in r], [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[5]) for x in r]
    except: pass
    # 6. BYBIT
    try:
        by_int = interval.replace("m","")
        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval={by_int}&limit={limit}"
        r = requests.get(url, headers=headers, timeout=10).json()
        data = r.get("result",{}).get("list",[])
        if data and len(data)>50:
            data = data[::-1]
            print(f"{sym}: OK BYBIT {len(data)}")
            return [float(x[4]) for x in data], [float(x[2]) for x in data], [float(x[3]) for x in data], [float(x[5]) for x in data]
    except: pass

    print(f"{sym}: ALL 6 FAILED")
    return None,None,None,None

# === MAIN SCAN ===
print(f"--- BOT START {datetime.utcnow()} UTC ---")
print(f"TOKEN SET? {bool(TOKEN)} CHAT_ID SET? {bool(CHAT_ID)}")

for sym in COINS:
    closes, highs, lows, vols = get_klines(sym, INTERVAL, LIMIT)
    if not closes:
        print(f"{sym}: SKIP - No data")
        continue

    price = closes[-1]
    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    rsi = calc_rsi(closes)
    avg_vol = sum(vols[-20:-1])/19 if len(vols)>20 else 1
    vol_ratio = vols[-1]/avg_vol if avg_vol>0 else 1
    bos_up = highs[-1] > max(highs[-20:-1]) if len(highs)>20 else False
    bos_down = lows[-1] < min(lows[-20:-1]) if len(lows)>20 else False

    print(f"{sym}: P={price:.6f} EMA20={ema20:.6f} EMA50={ema50:.6f} RSI={rsi:.1f} VOL={vol_ratio:.2f}x BOS_UP={bos_up} BOS_DOWN={bos_down}")

    signal = None
    sl = None
    tp = None

    # 🟢 BUY
    if price > ema50 and ema20 > ema50 and bos_up and vol_ratio >= 1.2 and 38 <= rsi <= 70:
        sl = min(lows[-5:]) * 0.99
        risk = price - sl
        tp = price + (risk * 2.5) if risk>0 else price*1.05
        signal = "BUY"

    # 🔴 SELL
    elif price < ema50 and ema20 < ema50 and bos_down and vol_ratio >= 1.2 and 30 <= rsi <= 62:
        sl = max(highs[-5:]) * 1.01
        risk = sl - price
        tp = price - (risk * 2.5) if risk>0 else price*0.95
        signal = "SELL"

    if signal:
        emoji = "🟢" if signal=="BUY" else "🔴"
        msg = f"{emoji} {signal} A+ {sym} {INTERVAL}\nPrice: {price}\nEMA20: {ema20:.6f} EMA50: {ema50:.6f}\nRSI: {rsi:.1f} VOL: {vol_ratio:.2f}x\nSL: {sl:.6f}\nTP: {tp:.6f}\nTime: {datetime.utcnow().strftime('%H:%M UTC')}"
        send_telegram(msg)
        print(f" -> {signal} SENT!")
    else:
        print(f" -> SKIP - No A+")

print("--- SCAN DONE ---")
send_telegram(f"✅ Scan done {datetime.utcnow().strftime('%H:%M UTC')} - Checked {len(COINS)} coins. No A+ yet." if True else "")
