import time, json, os, requests
from datetime import datetime
import pytz

# --- CONFIG ---
SYMBOLS = ["KOMAUSDT","VINEUSDT","BANKUSDT","NCTUSDT","AITECHUSDT","ALCHUSDT"]
SIGNAL_COOLDOWN_MIN = 30
NO_REENTRY_CANDLES = 4
WHALE_WICK = 2.0
VOL_OVERALL_MIN = 1.2

COOLDOWN_FILE = "cooldown.json"
COOLDOWN = {"signals":{}, "exits":{}, "last_side":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN = json.load(open(COOLDOWN_FILE))
    except: pass

def save_cooldown():
    json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))

def send_telegram(msg):
    # your telegram code here
    print(msg)
    # requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT}&text={msg}")

def get_data(sym):
    # your mexc fetch - return dict with price, volumes list, wicks etc
    # Mock structure you already have:
    # return {price, low_r, up_r, v1t, v5t, vol_x_avg, volumes, avg_50, bullish, bearish, swept_low, swept_high, near_floor, near_ceiling, FLOOR, CEIL, LOCAL_FLOOR, LOCAL_CEIL, session, is_pick}
    pass

def scan(sym):
    d = get_data(sym)
    if not d: return
    price = d["price"]
    low_r = d["low_r"]
    up_r = d["up_r"]
    v1t = d["v1t"]
    v5t = d["v5t"]
    vol_x_avg = d["vol_x_avg"]
    volumes = d["volumes"]
    avg_50 = d["avg_50"]

    # --- NEW: 1 min vs 15 min for your 5-15 entries ---
    v15t = sum(volumes[-15:]) / 15 / avg_50 if len(volumes)>=15 else v5t
    short_increase = v1t > v15t * 1.3
    short_decrease = v1t < v15t * 0.8

    overall_increase = vol_x_avg >= 1.5
    overall_decrease = vol_x_avg < 1.0

    is_whale = low_r >= WHALE_WICK or up_r >= WHALE_WICK
    is_middle = d["is_middle"]

    # --- FILTERS ---
    if is_middle and vol_x_avg < 2.0: return
    if not d["is_pick"]: return
    if vol_x_avg < VOL_OVERALL_MIN: return

    def can_send(side):
        now=time.time()
        last = COOLDOWN.get("signals",{}).get(sym)
        last_side = COOLDOWN.get("last_side",{}).get(sym)

        # REVERSAL LOGIC
        if last and last_side!= side:
            # Real reversal = whale + overall UP + short UP
            if is_whale and overall_increase and short_increase:
                COOLDOWN["signals"][sym]=now
                COOLDOWN["last_side"][sym]=side
                save_cooldown()
                return True
            else:
                # Fake = volume decreasing = manipulation
                return False

        # Normal cooldown
        if now - COOLDOWN.get("exits",{}).get(sym,0) < NO_REENTRY_CANDLES*5*60:
            return False
        if last is None or now-last > SIGNAL_COOLDOWN_MIN*60:
            COOLDOWN["signals"][sym]=now
            COOLDOWN["last_side"][sym]=side
            save_cooldown()
            return True
        return False

    # --- SIGNALS ---
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

# --- MAIN LOOP ---
while True:
    nairobi = datetime.now(pytz.timezone("Africa/Nairobi"))
    # Dead zone sleep 12am-8:59am Kenya
    if 0 <= nairobi.hour < 9:
        time.sleep(60)
        continue
    for sym in SYMBOLS:
        try: scan(sym)
        except Exception as e: print(e)
    time.sleep(30)
