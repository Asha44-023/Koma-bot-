import time, json, os, requests, sys
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOLS = ["KOMAUSDT","GRASSUSDT","HEIUSDT","LABUSDT","SIRENUSDT","VELVETUSDT"]
SIGNAL_COOLDOWN_MIN = 120 # ANTI-SPAM 2 HOURS
VOL_OVERALL_MIN = 1.2
ACCUM_RANGE_PCT = 0.8
VOL_POOL_BREAK_PCT = 45
VOL_ABSOLUTE_MIN = 20

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or ""

COOLDOWN_FILE = "cooldown.json"
COOLDOWN = {"signals":{}, "last_side":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN = json.load(open(COOLDOWN_FILE))
    except: pass

def save_cooldown():
    with open(COOLDOWN_FILE,"w") as f: json.dump(COOLDOWN,f)

def send_telegram(msg):
    print(msg, flush=True)
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: return
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     params={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=10)
    except: pass

def get_data(sym):
    try:
        r = requests.get("https://api.mexc.com/api/v3/klines",
                         params={"symbol":sym,"interval":"5m","limit":100}, timeout=10).json()
        if not r or len(r)<50: return None
        closes = [float(x[4]) for x in r]; highs = [float(x[2]) for x in r]; lows = [float(x[3]) for x in r]; opens = [float(x[1]) for x in r]; vols = [float(x[5]) for x in r]
        price = closes[-1]; avg_50 = sum(vols)/len(vols) if vols else 1
        v1t = vols[-1]/avg_50 if avg_50 else 1
        body = abs(closes[-1]-opens[-1]) + 0.000001
        avg_body = sum([abs(closes[i]-opens[i]) for i in range(-20,-1)])/20 + 0.000001
        low_r = (min(opens[-1],closes[-1]) - lows[-1]) / body
        up_r = (highs[-1] - max(opens[-1],closes[-1])) / body
        swept_low = lows[-1] < min(lows[-10:-1]); swept_high = highs[-1] > max(highs[-10:-1])
        bullish = closes[-1] > opens[-1]; bearish = not bullish
        accum_hours = 0; accum_start_idx = len(r)-1
        for i in range(len(r)-1, 10, -1):
            window = r[max(0,i-24):i]
            wh = max([float(x[2]) for x in window]); wl = min([float(x[3]) for x in window])
            wp = float(window[-1][4])
            range_pct = (wh-wl)/wp*100 if wp else 100
            if range_pct > ACCUM_RANGE_PCT: break
            accum_hours += 5/60; accum_start_idx = i
        recent_vols = vols[max(0,accum_start_idx):] if accum_hours>=0.5 else vols[-36:]
        pool_vol = sum(recent_vols) if recent_vols else 1
        vol_pool_pct = (vols[-1]/pool_vol*100) if pool_vol else 0
        recent_range_pct = (max(highs[-36:])-min(lows[-36:]))/price*100 if len(highs)>=36 else 100
        accum_high = max(highs[accum_start_idx:]) if accum_hours>=0.5 else max(highs[-36:])
        accum_low = min(lows[accum_start_idx:]) if accum_hours>=0.5 else min(lows[-36:])
        try:
            rd = requests.get("https://api.mexc.com/api/v3/klines",
                              params={"symbol":sym,"interval":"1d","limit":3}, timeout=10).json()
            prev_high = float(rd[-2][2]) if len(rd)>=2 else max(highs[-20:])
            prev_low = float(rd[-2][3]) if len(rd)>=2 else min(lows[-20:])
        except:
            prev_high = max(highs[-20:]); prev_low = min(lows[-20:])
        return {"price":price,"low_r":low_r,"up_r":up_r,"v1t":v1t,"bullish":bullish,"bearish":bearish,"swept_low":swept_low,"swept_high":swept_high,"accum_hours":accum_hours,"vol_pool_pct":vol_pool_pct,"recent_range_pct":recent_range_pct,"accum_high":accum_high,"accum_low":accum_low,"prev_high":prev_high,"prev_low":prev_low,"avg_body":avg_body,"last_body":body,"vol_x_avg":v1t}
    except Exception as e:
        print(f"{sym} err {e}", flush=True); return None

def scan(sym):
    d = get_data(sym)
    if not d: return
    if d["accum_hours"] < 0.5: return
    if d["vol_pool_pct"] < VOL_ABSOLUTE_MIN: return
    if d["recent_range_pct"] < 0.3: return
    if d["last_body"] < d["avg_body"]*1.8 and d["vol_pool_pct"] < 60: return
    if d["vol_x_avg"] < VOL_OVERALL_MIN and d["vol_pool_pct"] < VOL_POOL_BREAK_PCT: return

    def can_send(side):
        now=time.time()
        last = COOLDOWN.get("signals",{}).get(sym)
        last_side = COOLDOWN.get("last_side",{}).get(sym)
        # ANTI-SPAM: same coin 2 hours, same side 2h, opposite side 30min
        if last and now-last < SIGNAL_COOLDOWN_MIN*60: return False
        if last_side == side and last and now-last < 7200: return False
        if last_side!= side and last and now-last < 1800: return False
        COOLDOWN["signals"][sym]=now; COOLDOWN["last_side"][sym]=side; save_cooldown(); return True

    price = d["price"]
    is_pin_long = (d["low_r"]>=1.5 and d["swept_low"]) or (d["v1t"]>=1.2 and d["low_r"]>=1.8 and d["bullish"])
    is_vol_break_long = d["accum_hours"]>=2.0 and d["vol_pool_pct"]>=VOL_POOL_BREAK_PCT and price > d["accum_high"]
    if is_pin_long or is_vol_break_long:
        if can_send("BUY"):
            sl = min(d["accum_low"], d["prev_low"]) * 0.998
            tp1 = d["accum_high"]; tp2 = d["prev_high"]
            if tp2 <= price: tp2 = price + (d["accum_high"]-d["accum_low"])*1.5
            nairobi = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
            typ = "VOL BREAK" if is_vol_break_long else "PIN BAR"
            send_telegram(f"🟢 {sym} BUY {typ}\nEntry: {price:.6f} NOW\nAccum: {d['accum_hours']:.1f}h Vol {d['vol_pool_pct']:.0f}% pool Range {d['recent_range_pct']:.2f}%\nSL: {sl:.6f}\nTP1: {tp1:.6f}\nTP2: {tp2:.6f} [{nairobi}]")

    is_pin_short = (d["up_r"]>=1.5 and d["swept_high"]) or (d["v1t"]>=1.2 and d["up_r"]>=1.8 and d["bearish"])
    is_vol_break_short = d["accum_hours"]>=2.0 and d["vol_pool_pct"]>=VOL_POOL_BREAK_PCT and price < d["accum_low"]
    if is_pin_short or is_vol_break_short:
        if can_send("SELL"):
            sl = max(d["accum_high"], d["prev_high"]) * 1.002
            tp1 = d["prev_low"]; tp2 = price - (d["accum_high"]-d["accum_low"])*1.5
            nairobi = datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
            typ = "VOL BREAK" if is_vol_break_short else "PIN BAR"
            send_telegram(f"🔴 {sym} SELL {typ}\nEntry: {price:.6f} NOW\nAccum: {d['accum_hours']:.1f}h Vol {d['vol_pool_pct']:.0f}% pool Range {d['recent_range_pct']:.2f}%\nSL: {sl:.6f}\nTP1: {tp1:.6f}\nTP2: {tp2:.6f} [{nairobi}]")

ONCE = "--once" in sys.argv
print(f"=== BOT V9.2 BEST - ANTI-SPAM 2H ===", flush=True)

if ONCE:
    for sym in SYMBOLS:
        try: scan(sym)
        except Exception as e: print(e, flush=True)
    print("Done scan.", flush=True)
else:
    while True:
        for sym in SYMBOLS:
            try: scan(sym)
            except Exception as e: print(e, flush=True)
        time.sleep(300)
