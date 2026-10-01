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

ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
EARLY = json.load(open(EARLY_FILE)) if os.path.exists(EARLY_FILE) else {}
if "signals" not in COOLDOWN: COOLDOWN={"signals":{}}
if "dir" not in COOLDOWN: COOLDOWN["dir"]={}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=8)
    except: pass
    print(msg)

# MEXC PERP ONLY
def kl(symbol, interval):
    try:
        sec_map = {"Min1":60,"Min5":300,"Min15":900,"Min30":1800,"Min60":3600,"Hour4":14400,"Hour8":28800,"Day1":86400}
        sec = sec_map.get(interval, 300)
        end = int(time.time())
        start = end - sec*250 # 250 candles

        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}, timeout=10).json()

        # unwrap: {code:0, data:{open:[],high:[],...}}
        data = r.get("data") if isinstance(r, dict) else None
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, dict):
            print(f"kl fail {symbol} {r}")
            return None
        if "open" not in data:
            print(f"kl fail no open {symbol} keys {list(data.keys())}")
            return None

        return {
            "o":[float(x) for x in data["open"][-200:]],
            "h":[float(x) for x in data["high"][-200:]],
            "l":[float(x) for x in data["low"][-200:]],
            "c":[float(x) for x in data["close"][-200:]],
            "v":[float(x) for x in (data.get("vol") or data.get("volume") or data.get("amount") or [0]*200)[-200:]]
        }
    except Exception as e:
        print(f"kl err {symbol} {e}")
        return None

def get_live_price(s):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}"
        r = requests.get(url, timeout=5).json()
        d = r.get("data", r)
        return float(d["lastPrice"])
    except: return None

def find_real_pool(arr):
    arr = arr[-80:]
    cur = arr[-1]
    candidates = {}
    for val in arr:
        if abs(val-cur)/cur < 0.005: continue
        cnt = sum(1 for x in arr if abs(x-val)/val < 0.003)
        if cnt >= 3:
            candidates[val]=cnt
    if not candidates: return None
    return max(candidates, key=lambda k: candidates[k])

def institutional_guard(symbol, d):
    c,h,l,v = d["c"], d["h"], d["l"], d["v"]
    if len(c) < 60: return None, None, "short", None
    floor = find_real_pool(l)
    ceiling = find_real_pool(h)
    if not floor and not ceiling:
        return None, None, f"no real pool", None
    median_wick = sorted([h[i]-l[i] for i in range(-30,-2)])[14]
    median_vol = sorted(v[-30:-2])[14] or 1
    sweep = {"h":h[-2], "l":l[-2], "v":v[-2]}
    now_c = c[-1]
    wick_size = sweep["h"]-sweep["l"]
    absorbed = wick_size > median_wick*1.5 and sweep["v"] > median_vol*1.5
    wall_signal = None
    if symbol in ACTIVE:
        is_buy = ACTIVE[symbol]["is_buy"]
        entry = ACTIVE[symbol]["entry"]
        if is_buy and ceiling and now_c > entry:
            dist = abs(ceiling-now_c)/now_c
            if dist < 0.008 and time.time()-COOLDOWN["wall"].get(symbol,0)>1800:
                wall_signal = f"⚠️ WALL CLOSE {symbol} LONG profit {now_c:.5f} wall {ceiling:.5f}"
        if not is_buy and floor and now_c < entry:
            dist = abs(now_c-floor)/now_c
            if dist < 0.008 and time.time()-COOLDOWN["wall"].get(symbol,0)>1800:
                wall_signal = f"⚠️ WALL CLOSE {symbol} SHORT profit {now_c:.5f} wall {floor:.5f}"
    if floor:
        if sweep["l"] < floor and now_c > floor and now_c > (sweep["h"]+sweep["l"])/2 and absorbed:
            return "BUY", floor, f"SL POOL swept {floor:.5f} {wick_size/median_wick:.1f}x {sweep['v']/median_vol:.1f}x", wall_signal
    if ceiling:
        if sweep["h"] > ceiling and now_c < ceiling and now_c < (sweep["h"]+sweep["l"])/2 and absorbed:
            return "SELL", ceiling, f"BUY POOL swept {ceiling:.5f} {wick_size/median_wick:.1f}x {sweep['v']/median_vol:.1f}x", wall_signal
    return None, None, f"waiting floor {floor} ceil {ceiling}", wall_signal

def get_tps_sl(entry, is_buy, d):
    atr = sum([d["h"][i]-d["l"][i] for i in range(-14,0)])/14
    if is_buy: return entry+atr*1.5, entry+atr*3, entry-atr*1.5
    else: return entry-atr*1.5, entry-atr*3, entry+atr*1.5

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
    print(f"=== SCAN V88 5M PERP {get_time()} ===")
    for s in SYMBOLS:
        d5m=kl(s,"Min5"); d4h=kl(s,"Min60")
        if not d5m: continue
        direction, pool, reason, wall = institutional_guard(s, d5m)
        if wall:
            tg(f"{wall}\n{get_time()}"); COOLDOWN["wall"][s]=time.time(); save_c()
        print(f"{s} {reason} -> {direction}")
        if not direction: continue
        if time.time() - COOLDOWN["signals"].get(s,0) < 3600: continue
        live=get_live_price(s) or d5m["c"][-1]
        is_buy = direction=="BUY"
        tp1,tp2,sl = get_tps_sl(live, is_buy, d4h or d5m)
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); COOLDOWN["dir"][s]=direction; save_c()
        tg(f"{'🟢 BUY READY' if is_buy else '🔴 SELL READY'} {s} V88 5M PERP\nPOOL: {pool:.5f}\n{reason}\nENTRY {live:.5f}\nSL {sl:.5f}\nTP2 {tp2:.5f}\n{get_time()}")
        break

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
