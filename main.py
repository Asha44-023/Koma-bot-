import os, requests
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINS = ["KOMAUSDT","LABUSDT","HEIUSDT","SIRENUSDT","GRASSUSDT","VELVETUSDT"]

def tg(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        print(msg)

def get_klines(sym, interval, limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        data = requests.get(url, timeout=10).json()
        closes = [float(x[4]) for x in data]
        highs = [float(x[2]) for x in data]
        lows = [float(x[3]) for x in data]
        vols = [float(x[5]) for x in data]
        return closes, highs, lows, vols
    except:
        return None, None, None, None

def ema(arr, period):
    k = 2/(period+1)
    e = arr[0]
    for p in arr[1:]: e = p*k + e*(1-k)
    return e

def rsi(arr, period=14):
    if len(arr) < period+1: return 50
    gains = []; losses = []
    for i in range(1, period+1):
        diff = arr[-i] - arr[-i-1]
        gains.append(max(diff,0)); losses.append(max(-diff,0))
    avg_g = sum(gains)/period; avg_l = sum(losses)/period
    if avg_l == 0: return 70
    rs = avg_g/avg_l
    return 100 - (100/(1+rs))

def bos(closes, highs, lows):
    if len(closes) < 25: return None
    last_c = closes[-1]
    if last_c > max(highs[-21:-1]): return "BOS_BULL"
    if last_c < min(lows[-21:-1]): return "BOS_BEAR"
    return None

def double_pattern(highs, lows, closes):
    if len(highs) < 30: return None
    recent_h = highs[-15:]; top2 = sorted(recent_h, reverse=True)[:2]
    if abs(top2[0]-top2[1])/top2[0] < 0.015 and closes[-1] < closes[-5]:
        return "DOUBLE_TOP_BEARISH"
    recent_l = lows[-15:]; bot2 = sorted(recent_l)[:2]
    if abs(bot2[0]-bot2[1])/bot2[0] < 0.015 and closes[-1] > closes[-5]:
        return "DOUBLE_BOTTOM_BULLISH"
    return None

found = False
for sym in COINS:
    try:
        c5,h5,l5,v5 = get_klines(sym,"5m")
        c15,h15,l15,v15 = get_klines(sym,"15m")
        c1h,h1h,l1h,v1h = get_klines(sym,"1h")
        c4h,h4h,l4h,v4h = get_klines(sym,"4h")
        if not c5: continue

        price = c5[-1]
        # 4H TREND
        dir4h = "BULL" if ema(c4h,50) > ema(c4h,200) else "BEAR"
        # 1H BOS
        b1h = bos(c1h,h1h,l1h)
        st1h = b1h if b1h else ("BULL" if c1h[-1] > ema(c1h,50) else "BEAR")
        # 5m/15m EMA
        e9_5 = ema(c5,9); e21_5 = ema(c5,21)
        e9_15 = ema(c15,9); e21_15 = ema(c15,21)
        # RSI + VOL
        r5 = rsi(c5)
        vavg = sum(v5[-21:-1])/20; vnow = v5[-1]; vsp = vnow/vavg if vavg>0 else 1
        # PATTERN + BOS 5m
        pat = double_pattern(h15,l15,c15)
        b5 = bos(c5,h5,l5)

        # SCORING FOR BUY
        bull = 0; rsn = []
        if dir4h == "BULL": bull+=1; rsn.append("4H BULL")
        if "BULL" in st1h: bull+=1; rsn.append(f"1H {st1h}")
        if e9_5 > e21_5: bull+=1; rsn.append("5m EMA9>21")
        if e9_15 > e21_15: bull+=1; rsn.append("15m EMA9>21")
        if 45 < r5 < 68: bull+=1; rsn.append(f"RSI {r5:.1f}")
        if vsp > 1.5: bull+=2; rsn.append(f"VOL SPIKE x{vsp:.1f}")
        if b5 == "BOS_BULL": bull+=2; rsn.append("BOS 5m BULL")
        if pat and "BULLISH" in pat: bull+=2; rsn.append(pat)

        # SCORING FOR SELL
        bear = 0
        if dir4h == "BEAR": bear+=1
        if "BEAR" in st1h: bear+=1
        if e9_5 < e21_5: bear+=1
        if e9_15 < e21_15: bear+=1
        if vsp > 1.5: bear+=2
        if b5 == "BOS_BEAR": bear+=2
        if pat and "BEARISH" in pat: bear+=2

        sig = None
        if bull >= 6 and dir4h == "BULL": sig = "BUY"
        elif bear >= 6 and dir4h == "BEAR": sig = "SELL"

        if sig:
            found = True
            atr = sum([h15[-14+i]-l15[-14+i] for i in range(14)])/14
            if sig == "BUY":
                entry = price; sl = entry - atr*1.5; tp1 = entry + atr*2; tp2 = entry + atr*3.5; tp3 = entry + atr*5
            else:
                entry = price; sl = entry + atr*1.5; tp1 = entry - atr*2; tp2 = entry - atr*3.5; tp3 = entry - atr*5
            risk = abs(entry-sl)/entry*100; rew = abs(tp1-entry)/entry*100
            tg(f"*{sym} {sig} SIGNAL* | 5m/15m ENTRY\n\nBUY/SELL: {sig}\nEntry: `{entry:.6f}`\nSTOP LOSS: `{sl:.6f}` (-{risk:.2f}%)\nTAKE PROFIT 1: `{tp1:.6f}` (+{rew:.2f}%)\nTAKE PROFIT 2: `{tp2:.6f}`\nTAKE PROFIT 3: `{tp3:.6f}`\n\n4H Trend: {dir4h}\n1H: {st1h}\nBOS 5m: {b5}\nPattern: {pat}\nEMA: 5m {e9_5:.4f}/{e21_5:.4f} | 15m {e9_15:.4f}/{e21_15:.4f}\nRSI: {r5:.1f} | VOL: x{vsp:.2f}\nReasons: {', '.join(rsn)}\nTime: {datetime.utcnow().strftime('%H:%M UTC')}")

    except Exception as e:
        print(f"{sym} error {e}")
        pass

if not found:
    tg(f"SCAN {datetime.utcnow().strftime('%H:%M UTC')} | Checked {', '.join(COINS)} | No A+ setup (EMA+BOS+PATTERN+RSI+VOL) | Bot alive - Next 15m")
