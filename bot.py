import time, requests, json, os, sys
from datetime import datetime
import pytz

EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]

TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8500000000:XXXX"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT_ID"

COOLDOWN_FILE = "cooldown.json"
ACTIVE_FILE = "active.json"
EARLY_FILE = "early.json"
LAST_FILE = "last_id.json"

ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
EARLY = json.load(open(EARLY_FILE)) if os.path.exists(EARLY_FILE) else {}
LAST_DATA = json.load(open(LAST_FILE)) if os.path.exists(LAST_FILE) else {"id":0}
if "signals" not in COOLDOWN: COOLDOWN={"signals":{}}
if "dir" not in COOLDOWN: COOLDOWN["dir"]={}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
LAST_ID = LAST_DATA.get("id",0)

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def save_e(): json.dump(EARLY, open(EARLY_FILE,"w"))
def save_last(): json.dump({"id":LAST_ID}, open(LAST_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=8)
    except: pass
    print(msg)

def kl(symbol, interval):
    try:
        mexc_interval = interval
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={mexc_interval}"
        r = requests.get(url, timeout=10).json()
        d = r["data"] if "data" in r else r
        vols = d.get("vol", d.get("volume", d.get("amount", [0]*300)))
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]],"v":[float(x) for x in vols[-200:]]}
    except Exception as e:
        print(f"kl err {symbol} {e}")
        return None

def get_live_price(s):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}"
        r = requests.get(url, timeout=5).json()
        return float((r["data"] if "data" in r else r)["lastPrice"])
    except: return None

# --- INSTITUTIONAL GUARD - NO FIXED FIGURES + 5M + WALL EARLY ---
def institutional_guard(symbol, d):
    c,h,l,v = d["c"], d["h"], d["l"], d["v"]
    if len(c) < 60: return None, None, "short data", None

    recent_lows = l[-50:]
    recent_highs = h[-50:]
    try:
        floor = sorted(recent_lows)[len(recent_lows)//4]
        ceiling = sorted(recent_highs)[-len(recent_highs)//4]
    except:
        floor = min(l[-21:-2]); ceiling = max(h[-21:-2])

    typical_wicks = [h[i]-l[i] for i in range(-30,-2)]
    typical_vol = v[-30:-2]
    median_wick = sorted(typical_wicks)[len(typical_wicks)//2]
    median_vol = sorted(typical_vol)[len(typical_vol)//2] if sorted(typical_vol)[len(typical_vol)//2]!=0 else 1

    sweep = {"h":h[-2], "l":l[-2], "c":c[-2], "o":d["o"][-2], "v":v[-2]}
    now = {"c":c[-1], "h":h[-1], "l":l[-1]}

    wick_size = sweep["h"] - sweep["l"]
    absorbed = wick_size > median_wick * 1.2 and sweep["v"] > median_vol * 1.2

    dist_floor = abs(now["c"] - floor) / now["c"]
    dist_ceil = abs(ceiling - now["c"]) / now["c"]
    bias_long = dist_floor < dist_ceil
    nearest_pool = floor if bias_long else ceiling

    # WALL CLOSE early check - 5m ahead
    wall_signal = None
    if min(dist_floor, dist_ceil) < 0.008: # 0.8% from wall
        if time.time() - COOLDOWN["wall"].get(symbol,0) > 1800:
            wall_signal = f"⚠️ WALL CLOSE {symbol} price {now['c']:.5f} pool {nearest_pool:.5f} {min(dist_floor,dist_ceil):.2%} - if in profit CLOSE & flip ready"

    if bias_long:
        swept = sweep["l"] < floor
        reclaimed = now["c"] > floor and now["c"] > (sweep["h"]+sweep["l"])/2
        if swept and absorbed and reclaimed:
            return "BUY", floor, f"SL POOL swept {floor:.5f} wick {wick_size/median_wick:.1f}x vol {sweep['v']/median_vol:.1f}x", wall_signal
    else:
        swept = sweep["h"] > ceiling
        reclaimed = now["c"] < ceiling and now["c"] < (sweep["h"]+sweep["l"])/2
        if swept and absorbed and reclaimed:
            return "SELL", ceiling, f"BUY POOL swept {ceiling:.5f} wick {wick_size/median_wick:.1f}x vol {sweep['v']/median_vol:.1f}x", wall_signal

    return None, None, f"waiting floor {floor:.5f} ceil {ceiling:.5f} bias {'LONG' if bias_long else 'SHORT'}", wall_signal

def get_tps_sl(entry, is_buy, d):
    atr = sum([d["h"][i]-d["l"][i] for i in range(-14,0)])/14
    if is_buy:
        sl = entry - (atr * 1.5); tp2 = entry + (atr * 3); tp1 = entry + (atr * 1.5)
    else:
        sl = entry + (atr * 1.5); tp2 = entry - (atr * 3); tp1 = entry - (atr * 1.5)
    return tp1, tp2, sl

def manage():
    for s,data in list(ACTIVE.items()):
        price=get_live_price(s)
        if not price: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        tp1,tp2=data.get("tp1"),data.get("tp2")
        if is_buy and price<=sl or not is_buy and price>=sl:
            tg(f"❌ STOP {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit"):
            if is_buy and price>=tp1 or not is_buy and price<=tp1:
                data["tp1_hit"]=True; data["sl"]=entry; save_a()
                tg(f"✅ TP1 {s} {price:.5f} SL→BE\n{get_time()}")
        if is_buy and price>=tp2 or not is_buy and price<=tp2:
            tg(f"✅✅ TP2 {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a()

def scan():
    manage()
    if len(ACTIVE)>=3: return
    print(f"=== SCAN V88 5M INSTITUTIONAL {get_time()} ===")
    for s in SYMBOLS:
        d5m=kl(s,"Min5") # 5m for clean + early
        d4h=kl(s,"Min240")
        if not d5m: continue
        direction, pool, reason, wall = institutional_guard(s, d5m)

        # send wall early first
        if wall:
            tg(f"{wall}\n{get_time()}")
            COOLDOWN["wall"][s]=time.time(); save_c()

        print(f"{s} {reason} -> {direction}")
        if not direction: continue
        if time.time() - COOLDOWN["signals"].get(s,0) < 3600: continue

        live=get_live_price(s) or d5m["c"][-1]
        is_buy = direction=="BUY"
        tp1,tp2,sl = get_tps_sl(live, is_buy, d4h or d5m)
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); COOLDOWN["dir"][s]=direction; save_c()
        tg(f"{'🟢 BUY READY' if is_buy else '🔴 SELL READY'} {s} V88 5M\nPOOL: {pool:.5f}\n{reason}\nENTRY {live:.5f}\nSL {sl:.5f}\nTP2 {tp2:.5f}\n{get_time()}")
        break

if "--once" in sys.argv:
    scan()
else:
    print(f"🚀 V88 5M INSTITUTIONAL {get_time()}")
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
