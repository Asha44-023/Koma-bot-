import time, json, os, requests
from datetime import datetime
from zoneinfo import ZoneInfo

# GRASS etc list
SYMBOLS = ["KOMAUSDT","GRASSUSDT","HEIUSDT","LABUSDT","SIRENUSDT","VELVETUSDT"]
SIGNAL_COOLDOWN_MIN = 30
NO_REENTRY_CANDLES = 4
WHALE_WICK = 2.0
VOL_OVERALL_MIN = 1.2

# Telegram - supports both names
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or ""
COOLDOWN_FILE = "cooldown.json"
COOLDOWN = {"signals":{}, "exits":{}, "last_side":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN = json.load(open(COOLDOWN_FILE))
    except: pass

def save_cooldown():
    with open(COOLDOWN_FILE,"w") as f: json.dump(COOLDOWN,f)

def send_telegram(msg):
    print(msg, flush=True)
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print(f"Telegram env missing - token:{bool(TELEGRAM_TOKEN)} chat:{bool(TELEGRAM_CHAT)}", flush=True)
        return
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     params={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=10)
    except Exception as e:
        print(f"Telegram err {e}", flush=True)

def get_data(sym):
    try:
        r = requests.get("https://api.mexc.com/api/v3/klines",
                         params={"symbol":sym,"interval":"5m","limit":50}, timeout=10).json()
        if not r or len(r)<20: return None
        closes = [float(x[4]) for x in r]
        highs = [float(x[2]) for x in r]
        lows = [float(x[3]) for x in r]
        opens = [float(x[1]) for x in r]
        vols = [float(x[5]) for x in r]

        price = closes[-1]
        avg_50 = sum(vols)/len(vols) if vols else 1
        v1t = vols[-1]/avg_50 if avg_50 else 1
        v5t = sum(vols[-5:])/5/avg_50 if avg_50 else 1
        vol_x_avg = v1t

        body = abs(closes[-1]-opens[-1]) + 0.000001
        low_r = (min(opens[-1],closes[-1]) - lows[-1]) / body
        up_r = (highs[-1] - max(opens[-1],closes[-1])) / body

        FLOOR = min(lows[-20:])
        CEIL = max(highs[-20:])
        LOCAL_FLOOR = min(lows[-5:])
        LOCAL_CEIL = max(highs[-5:])

        near_floor = price < FLOOR*1.02
        near_ceiling = price > CEIL*0.98
        swept_low = lows[-1] < min(lows[-10:-1])
        swept_high = highs[-1] > max(highs[-10:-1])

        bullish = closes[-1] > opens[-1]
        bearish = not bullish
        mid = (FLOOR+CEIL)/2
        is_middle = abs(price-mid)/mid < 0.02

        nairobi_h = datetime.now(ZoneInfo("Africa/Nairobi")).hour
        is_pick = 10 <= nairobi_h <= 22
        session = "PICK" if is_pick else "OFF"

        return {
            "price":price,"low_r":low_r,"up_r":up_r,"v1t":v1t,"v5t":v5t,
            "vol_x_avg":vol_x_avg,"volumes":vols,"avg_50":avg_50,
            "bullish":bullish,"bearish":bearish,"swept_low":swept_low,
            "swept_high":swept_high,"near_floor":near_floor,"near_ceiling":near_ceiling,
            "FLOOR":FLOOR,"CEIL":CEIL,"LOCAL_FLOOR":LOCAL_FLOOR,"LOCAL_CEIL":LOCAL_CEIL,
            "session":session,"is_pick":is_pick,"is_middle":is_middle
        }
    except Exception as e:
        print(f"{sym} err {e}", flush=True)
        return None

def scan(sym):
    d = get_data(sym)
    if not d:
        print(f"{sym} no data", flush=True)
        return
    price = d["price"]; low_r=d["low_r"]; up_r=d["up_r"]; v1t=d["v1t"]; vol_x_avg=d["vol_x_avg"]; volumes=d["volumes"]; avg_50=d["avg_50"]

    v15t = sum(volumes[-15:])/15/avg_50 if len(volumes)>=15 and avg_50 else d["v5t"]
    short_increase = v1t > v15t * 1.3
    overall_increase = vol_x_avg >= 1.5
    is_whale = low_r >= WHALE_WICK or up_r >= WHALE_WICK

    # DEBUG LINE - instant on page
    print(f"{sym} price {price:.5f} vol {vol_x_avg:.2f}x wick L{low_r:.1f} U{up_r:.1f} sweep L{d['swept_low']} H{d['swept_high']} whale {is_whale}", flush=True)

    if vol_x_avg < VOL_OVERALL_MIN:
        return

    def can_send(side):
        now=time.time()
        last = COOLDOWN.get("signals",{}).get(sym)
        last_side = COOLDOWN.get("last_side",{}).get(sym)
        if last and last_side!= side:
            if is_whale and overall_increase and short_increase:
                COOLDOWN["signals"][sym]=now; COOLDOWN["last_side"][sym]=side; save_cooldown(); return True
            else: return False
        if now - COOLDOWN.get("exits",{}).get(sym,0) < NO_REENTRY_CANDLES*5*60: return False
        if last is None or now-last > SIGNAL_COOLDOWN_MIN*60:
            COOLDOWN["signals"][sym]=now; COOLDOWN["last_side"][sym]=side; save_cooldown(); return True
        return False

    whale_flash_buy = v1t>=2.0 and low_r>=1.8 and d["bullish"]
    buy_wick = low_r>=1.5 and d["swept_low"]
    whale_flash_sell = v1t>=2.0 and up_r>=1.8 and d["bearish"]
    sell_wick = up_r>=1.5 and d["swept_high"]

    if (whale_flash_buy or buy_wick) and can_send("BUY"):
        sl = d["FLOOR"]*0.988 if d["near_floor"] else d["LOCAL_FLOOR"]*0.988
        tp = price + (price-sl)*2.0
        send_telegram(f"🟢 {sym} BUY {low_r:.1f}x vol{vol_x_avg:.1f}x 1m{v1t:.1f} 15m{v15t:.1f} [{d['session']}] SL {sl:.5f} TP {tp:.5f}")

    if (whale_flash_sell or sell_wick) and can_send("SELL"):
        sl = d["CEIL"]*1.012 if d["near_ceiling"] else d["LOCAL_CEIL"]*1.012
        tp = price - (sl-price)*2.0
        send_telegram(f"🔴 {sym} SELL {up_r:.1f}x vol{vol_x_avg:.1f}x 1m{v1t:.1f} 15m{v15t:.1f} [{d['session']}] SL {sl:.5f} TP {tp:.5f}")

# FIXED LOOP - 24/7 INSTANT
print(f"=== BOT STARTED GRASS LIST 24/7 INSTANT ===", flush=True)
print(f"Nairobi: {datetime.now(ZoneInfo('Africa/Nairobi'))}", flush=True)
print(f"Symbols: {SYMBOLS}", flush=True)
print(f"Telegram token set: {bool(TELEGRAM_TOKEN)} chat set: {bool(TELEGRAM_CHAT)}", flush=True)

while True:
    nairobi = datetime.now(ZoneInfo("Africa/Nairobi"))
    print(f"--- [{nairobi.strftime('%H:%M:%S')}] Scanning ---", flush=True)
    for sym in SYMBOLS:
        try: scan(sym)
        except Exception as e: print(e, flush=True)
    
    # wait until next 5 minute mark
    now = datetime.now(ZoneInfo("Africa/Nairobi"))
    wait = 300 - (now.minute % 5 * 60 + now.second)
    if wait < 10: wait += 300
    print(f"Next scan in {wait//60}m {wait%60}s", flush=True)
    time.sleep(wait)
