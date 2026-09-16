import time, json, os, requests, sys
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOLS = ["KOMAUSDT","GRASSUSDT","HEIUSDT","LABUSDT","SIRENUSDT","VELVETUSDT"]
SYMBOLS_PERP = [s.replace("USDT","_USDT") for s in SYMBOLS]
SIGNAL_COOLDOWN_MIN = 30  # FIXED V9.9: 10 -> 30 to avoid flip-flop
VOL_ABSOLUTE_MIN = 5
VOL_POOL_BREAK_PCT = 12
ACCUM_RANGE_PCT = 1.8

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or ""
COOLDOWN_FILE = "cooldown.json"
COOLDOWN = {"signals":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN = json.load(open(COOLDOWN_FILE))
    except: pass

def save_cooldown():
    with open(COOLDOWN_FILE,"w") as f: json.dump(COOLDOWN,f)

def send_telegram(msg):
    print(msg, flush=True)
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: return
    try: requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", params={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=10)
    except: pass

def get_data(sym_spot, sym_perp):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/kline/{sym_perp}"
        r = requests.get(url, params={"interval":"Min5"}, timeout=10).json()
        if not r.get("success"): return None
        data = r.get("data",{})
        closes = [float(x) for x in data.get("close",[])]; highs = [float(x) for x in data.get("high",[])]
        lows = [float(x) for x in data.get("low",[])]; opens = [float(x) for x in data.get("open",[])]
        vols = [float(x) for x in data.get("vol",[])]
        if len(closes)<50: return None
        closes=closes[-100:]; highs=highs[-100:]; lows=lows[-100:]; opens=opens[-100:]; vols=vols[-100:]
        price = closes[-1]
        avg_vol = sum(vols[-36:])/36 if len(vols)>=36 else sum(vols)/len(vols)
        v1t = vols[-1]/avg_vol if avg_vol else 1
        vol_pool_pct = v1t*10
        body = abs(closes[-1]-opens[-1]) + 0.000001
        low_r = (min(opens[-1],closes[-1]) - lows[-1]) / body
        up_r = (highs[-1] - max(opens[-1],closes[-1])) / body
        swept_low = lows[-1] < min(lows[-10:-1]); swept_high = highs[-1] > max(highs[-10:-1])
        bullish = closes[-1] > opens[-1]; bearish = not bullish
        accum_hours = 0; accum_start_idx = len(closes)-1
        for i in range(len(closes)-1, 10, -1):
            wh = max(highs[max(0,i-12):i]); wl = min(lows[max(0,i-12):i])
            wp = closes[i-1]
            range_pct = (wh-wl)/wp*100 if wp else 100
            if range_pct > ACCUM_RANGE_PCT: break
            accum_hours += 5/60; accum_start_idx = i
        recent_range_pct = (max(highs[-36:])-min(lows[-36:]))/price*100 if len(highs)>=36 else 100
        accum_high = max(highs[accum_start_idx:]) if accum_hours>=0.1 else max(highs[-36:])
        accum_low = min(lows[accum_start_idx:]) if accum_hours>=0.1 else min(lows[-36:])
        trend_1h = (closes[-1]/closes[-12]-1)*100 if len(closes)>=12 else 0
        try:
            rd = requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym_perp}", params={"interval":"Day1"}, timeout=10).json()
            ddata = rd.get("data",{})
            dh = [float(x) for x in ddata.get("high",[])]; dl = [float(x) for x in ddata.get("low",[])]
            prev_high = dh[-2] if len(dh)>=2 else max(highs[-20:]); prev_low = dl[-2] if len(dl)>=2 else min(lows[-20:])
        except:
            prev_high = max(highs[-20:]); prev_low = min(lows[-20:])
        return {"price":price,"low_r":low_r,"up_r":up_r,"v1t":v1t,"bullish":bullish,"bearish":bearish,"swept_low":swept_low,"swept_high":swept_high,"accum_hours":accum_hours,"vol_pool_pct":vol_pool_pct,"recent_range_pct":recent_range_pct,"accum_high":accum_high,"accum_low":accum_low,"prev_high":prev_high,"prev_low":prev_low,"trend_1h":trend_1h}
    except Exception as e:
        print(f"{sym_spot} err {e}", flush=True); return None

def scan(sym_spot, sym_perp):
    d = get_data(sym_spot, sym_perp)
    if not d: print(f"{sym_spot} NO PERP DATA", flush=True); return
    print(f"{sym_spot} flat {d['accum_hours']:.1f}h vol {d['vol_pool_pct']:.0f}% range {d['recent_range_pct']:.2f}% trend {d['trend_1h']:+.2f}% v1t {d['v1t']:.1f}x", flush=True)
    if d["vol_pool_pct"] < VOL_ABSOLUTE_MIN: return

    def can_send():
        now=time.time()
        last = COOLDOWN.get("signals",{}).get(sym_spot)
        if last and now-last < SIGNAL_COOLDOWN_MIN*60: return False
        COOLDOWN["signals"][sym_spot]=now; save_cooldown(); return True

    price = d["price"]
    # FIXED V9.9: Pin bar respects trend - no short in strong uptrend
    is_pin_long = ((d["low_r"]>=1.0 and d["swept_low"]) or (d["v1t"]>=1.0 and d["low_r"]>=1.2 and d["bullish"])) and d["trend_1h"] > -2.0
    is_vol_break_long = d["accum_hours"]>=0.3 and d["vol_pool_pct"]>=VOL_POOL_BREAK_PCT and price > d["accum_high"]
    is_momentum_long = d["trend_1h"] > 0.8 and d["v1t"] > 1.0 and d["bullish"] and d["vol_pool_pct"] > 8
    if is_pin_long or is_vol_break_long or is_momentum_long:
        if can_send():
            sl = min(d["accum_low"], d["prev_low"]) * 0.998; tp1 = d["accum_high"]; tp2 = d["prev_high"]
            if tp2 <= price: tp2 = price + (d["accum_high"]-d["accum_low"])*1.5
            nairobi = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
            typ = "MOMENTUM PUMP" if is_momentum_long else "VOL BREAK" if is_vol_break_long else "PIN BAR"
            send_telegram(f"🟢 {sym_spot} BUY {typ} [PERP]\nEntry: {price:.6f} NOW\nTrend: {d['trend_1h']:+.1f}% Vol {d['vol_pool_pct']:.0f}% Flat {d['accum_hours']:.1f}h\nSL: {sl:.6f}\nTP1: {tp1:.6f}\nTP2: {tp2:.6f} [{nairobi}]")
            return
    is_pin_short = ((d["up_r"]>=1.0 and d["swept_high"]) or (d["v1t"]>=1.0 and d["up_r"]>=1.2 and d["bearish"])) and d["trend_1h"] < 2.0
    is_vol_break_short = d["accum_hours"]>=0.3 and d["vol_pool_pct"]>=VOL_POOL_BREAK_PCT and price < d["accum_low"]
    is_momentum_short = d["trend_1h"] < -0.8 and d["v1t"] > 1.0 and d["bearish"] and d["vol_pool_pct"] > 8
    if is_pin_short or is_vol_break_short or is_momentum_short:
        if can_send():
            sl = max(d["accum_high"], d["prev_high"]) * 1.002; tp1 = d["prev_low"]; tp2 = price - (d["accum_high"]-d["accum_low"])*1.5
            nairobi = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
            typ = "MOMENTUM DUMP" if is_momentum_short else "VOL BREAK" if is_vol_break_short else "PIN BAR"
            send_telegram(f"🔴 {sym_spot} SELL {typ} [PERP]\nEntry: {price:.6f} NOW\nTrend: {d['trend_1h']:+.1f}% Vol {d['vol_pool_pct']:.0f}% Flat {d['accum_hours']:.1f}h\nSL: {sl:.6f}\nTP1: {tp1:.6f}\nTP2: {tp2:.6f} [{nairobi}]")

ONCE = "--once" in sys.argv
print(f"=== BOT V9.9 ANTI-FLIP ===", flush=True)
if ONCE:
    for s,p in zip(SYMBOLS, SYMBOLS_PERP):
        try: scan(s,p)
        except Exception as e: print(e, flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS, SYMBOLS_PERP):
            try: scan(s,p)
            except Exception as e: print(e, flush=True)
        time.sleep(300)
