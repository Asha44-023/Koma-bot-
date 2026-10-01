import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"wall":{}}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":m}, timeout=8)
    except: pass
    print(m)

def kl(symbol, interval):
    sec_map = {"Min5":300,"Min15":900,"Hour4":14400,"Day1":86400}
    sec = sec_map.get(interval, 300)
    end = int(time.time()); start = end - sec*300
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
        d = r.get("data", r)
        if isinstance(d, dict) and "data" in d: d = d["data"]
        if not isinstance(d, dict) or "open" not in d: return None
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]],"v":[float(x) for x in (d.get("vol") or [0]*200)[-200:]]}
    except: return None

def get_live_price(s):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}", timeout=5).json()
        return float((r.get("data", r))["lastPrice"])
    except: return None

def find_pool_zones(arr, cur_price, lookback=100, tol=0.015, is_floor=True):
    arr = arr[-lookback:]
    if is_floor:
        filt = [float(v) for v in arr if v < cur_price and 0.003 < (cur_price - v)/cur_price < 0.15]
    else:
        filt = [float(v) for v in arr if v > cur_price and 0.003 < (v - cur_price)/cur_price < 0.15]
    if not filt: return None, 0
    buckets = []
    for v in sorted(filt):
        placed=False
        for b in buckets:
            if abs(v-b[0])/b[0] < tol: b.append(v); placed=True; break
        if not placed: buckets.append([v])
    if not buckets: return None, 0
    best = max(buckets, key=len)
    if len(best) >= 2: return float(sum(best)/len(best)), len(best)
    nearest = min(filt, key=lambda x: abs(x-cur_price))
    return float(nearest), 1

def find_fractal(arr_h, arr_l, is_low=True, lookback=80):
    arr = arr_l if is_low else arr_h
    arr = arr[-lookback:]
    res=[]
    for i in range(2, len(arr)-2):
        if is_low:
            if arr[i] < arr[i-1] and arr[i] < arr[i-2] and arr[i] < arr[i+1] and arr[i] < arr[i+2]: res.append(float(arr[i]))
        else:
            if arr[i] > arr[i-1] and arr[i] > arr[i-2] and arr[i] > arr[i+1] and arr[i] > arr[i+2]: res.append(float(arr[i]))
    return res

def guard_15_5_prop(d15, d5, bias):
    c5,h5,l5,v5,o5 = d5["c"], d5["h"], d5["l"], d5["v"], d5["o"]
    if len(c5)<60: return None, None, "short", None, None, 0, 0
    cur = c5[-1]
    floor_15, cnt_l = find_pool_zones(d15["l"], cur, 96, 0.012, True)
    ceil_15, cnt_h = find_pool_zones(d15["h"], cur, 96, 0.012, False)
    if not floor_15:
        f = find_fractal(d15["h"], d15["l"], True, 80)
        f = [x for x in f if x < cur and 0.003 < (cur-x)/cur < 0.15]
        if f: floor_15 = min(f, key=lambda x: abs(x-cur)); cnt_l=1
    if not ceil_15:
        f = find_fractal(d15["h"], d15["l"], False, 80)
        f = [x for x in f if x > cur and 0.003 < (x-cur)/cur < 0.15]
        if f: ceil_15 = min(f, key=lambda x: abs(x-cur)); cnt_h=1
    if bias=="BUY" and not floor_15: return None, None, f"no floor BELOW {cur:.5f}", floor_15, ceil_15, cnt_l, cnt_h
    if bias=="SELL" and not ceil_15: return None, None, f"no ceil ABOVE {cur:.5f}", floor_15, ceil_15, cnt_l, cnt_h
    med_wick = sorted([h5[i]-l5[i] for i in range(-30,-2)])[14]
    med_vol = sorted(v5[-30:-2])[14] or 1
    if med_vol==0: med_vol=1
    for k in range(2,5):
        sw = {"h":h5[-k],"l":l5[-k],"v":v5[-k], "o": o5[-k], "c": c5[-k]}
        vol_ok = sw["v"] > med_vol*1.0
        wick_ok = (sw["h"]-sw["l"]) > med_wick*1.0
        if bias=="BUY" and floor_15 and sw["l"] < floor_15 and cur > floor_15 and cur > sw["o"]:
            if vol_ok and wick_ok:
                body = abs(sw["o"]-sw["c"])+1e-9
                wick_low = min(sw["o"],sw["c"]) - sw["l"]
                if wick_low > body*0.6:
                    return "BUY", floor_15, f"swept LOW {floor_15:.5f} x{cnt_l} k-{k} vol{sw['v']/med_vol:.1f}x", floor_15, ceil_15, cnt_l, cnt_h
        if bias=="SELL" and ceil_15 and sw["h"] > ceil_15 and cur < ceil_15 and cur < sw["o"]:
            if vol_ok and wick_ok:
                body = abs(sw["o"]-sw["c"])+1e-9
                wick_high = sw["h"] - max(sw["o"],sw["c"])
                if wick_high > body*0.6:
                    return "SELL", ceil_15, f"swept HIGH {ceil_15:.5f} x{cnt_h} k-{k} vol{sw['v']/med_vol:.1f}x", floor_15, ceil_15, cnt_l, cnt_h
    return None, floor_15 if bias=="BUY" else ceil_15, f"wait {bias} f:{floor_15:.5f}({cnt_l})/c:{ceil_15:.5f}({cnt_h}) cur:{cur:.5f}", floor_15, ceil_15, cnt_l, cnt_h

COOLDOWN_MAP = {"SIREN_USDT":900,"FARTCOIN_USDT":900,"KOMA_USDT":900,"GRASS_USDT":1200}
DEFAULT_CD = 3600

def scan():
    for s, data in list(ACTIVE.items()):
        p = get_live_price(s)
        if not p: continue
        entry, is_buy, sl = data["entry"], data["is_buy"], data["sl"]
        if (is_buy and p <= sl) or (not is_buy and p >= sl):
            tg(f"❌ STOP {s} {p:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p >= data["tp1"]) or (not is_buy and p <= data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"✅ TP1 {s} SL→BE {p:.5f}\n{get_time()}")
        if (is_buy and p >= data["tp2"]) or (not is_buy and p <= data["tp2"]):
            tg(f"✅✅ TP2 {s} {p:.5f}\n{get_time()}"); del ACTIVE[s]; save_a()
    if len(ACTIVE)>=3: return
    print(f"=== V93.3A BEST A-MODE {get_time()} ===")
    for s in SYMBOLS:
        d5 = kl(s,"Min5"); d15 = kl(s,"Min15"); d4 = kl(s,"Hour4"); d1 = kl(s,"Day1")
        if not d5 or not d15 or not d4 or not d1: continue
        daily_trend = "up" if d1["c"][-1] > d1["c"][-20] else "down"
        bias = "BUY" if daily_trend=="up" else "SELL"
        floor_d, cnt_dl = find_pool_zones(d1["l"], d5["c"][-1], 100, 0.02, True)
        ceil_d, cnt_dh = find_pool_zones(d1["h"], d5["c"][-1], 100, 0.02, False)
        floor_4, cnt_4l = find_pool_zones(d4["l"], d5["c"][-1], 80, 0.015, True)
        ceil_4, cnt_4h = find_pool_zones(d4["h"], d5["c"][-1], 80, 0.015, False)
        direction, pool_15, reason, f15, c15, cnt_l, cnt_h = guard_15_5_prop(d15, d5, bias)
        fd = f"{floor_d:.5f}" if floor_d else "None"
        cd = f"{ceil_d:.5f}" if ceil_d else "None"
        f4 = f"{floor_4:.5f}" if floor_4 else "None"
        c4 = f"{ceil_4:.5f}" if ceil_4 else "None"
        ff = f"{f15:.5f}" if f15 else "None"
        cc = f"{c15:.5f}" if c15 else "None"
        print(f"{s} BIAS:{bias} D:{fd}({cnt_dl})/{cd}({cnt_dh}) 4H:{f4}({cnt_4l})/{c4}({cnt_4h}) 15M:f:{ff}({cnt_l})/c:{cc}({cnt_h}) -> {direction} | {reason}")
        if not direction: continue
        cdsec = COOLDOWN_MAP.get(s, DEFAULT_CD)
        if time.time()-COOLDOWN["signals"].get(s,0)<cdsec: continue
        live = get_live_price(s) or d5["c"][-1]
        atr5 = sum([d5["h"][i]-d5["l"][i] for i in range(-20,0)])/20
        is_buy = direction=="BUY"
        sl = min(live-atr5*2.5, pool_15*0.997) if is_buy else max(live+atr5*2.5, pool_15*1.003)
        tp1 = live+atr5*3 if is_buy else live-atr5*3
        tp2 = live+atr5*6 if is_buy else live-atr5*6
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
        tg(f"{'🟢 BUY' if is_buy else '🔴 SELL'} {s} BIAS {bias}\n{reason}\nZONE 15M {pool_15:.5f} | 4H {floor_4 if is_buy else ceil_4} | D {floor_d if is_buy else ceil_d}\nENTRY {live:.5f} SL {sl:.5f} TP2 {tp2:.5f}\n{get_time()}")
        break

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
