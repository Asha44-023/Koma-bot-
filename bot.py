import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8500000000:XXXX"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT_ID"
COOLDOWN_FILE, ACTIVE_FILE = "cooldown.json", "active.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {})
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
    end = int(time.time())
    start = end - sec*250
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
    d = r.get("data", r)
    if isinstance(d, dict) and "data" in d: d = d["data"]
    if not isinstance(d, dict) or "open" not in d:
        print(f"kl fail {symbol} {interval}"); return None
    return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]],"v":[float(x) for x in (d.get("vol") or [0]*200)[-200:]]}

def get_live_price(s):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}", timeout=5).json()
        return float((r.get("data", r))["lastPrice"])
    except: return None

def find_pool(arr, cur_price, lookback=80):
    arr = arr[-lookback:]
    cands = {}
    for v in arr:
        if abs(v-cur_price)/cur_price < 0.003: continue
        if abs(v-cur_price)/cur_price > 0.12: continue
        cnt = sum(1 for x in arr if abs(x-v)/v < 0.006)
        if cnt >= 2: cands[v]=cnt
    if not cands: return None
    return max(cands, key=lambda k: cands[k])

def guard_15_5_prop(d15, d5, bias):
    c5,h5,l5,v5 = d5["c"], d5["h"], d5["l"], d5["v"]
    if len(c5)<60: return None, None, "short"
    floor_15 = find_pool(d15["l"], c5[-1], 96)
    ceil_15 = find_pool(d15["h"], c5[-1], 96)
    if bias=="BUY" and not floor_15: return None, None, f"BUY bias but no 15M floor"
    if bias=="SELL" and not ceil_15: return None, None, f"SELL bias but no 15M ceil"
    med_wick = sorted([h5[i]-l5[i] for i in range(-30,-2)])[14]
    med_vol = sorted(v5[-30:-2])[14] or 1
    sw = {"h":h5[-2],"l":l5[-2],"v":v5[-2]}
    now = c5[-1]
    absorbed = (sw["h"]-sw["l"]) > med_wick*1.2 and sw["v"] > med_vol*1.2
    if bias=="BUY" and floor_15 and sw["l"] < floor_15 and now > floor_15 and now > (sw["h"]+sw["l"])/2 and absorbed:
        return "BUY", floor_15, f"swept 15M {floor_15:.5f} {sw['v']/med_vol:.1f}x"
    if bias=="SELL" and ceil_15 and sw["h"] > ceil_15 and now < ceil_15 and now < (sw["h"]+sw["l"])/2 and absorbed:
        return "SELL", ceil_15, f"swept 15M {ceil_15:.5f} {sw['v']/med_vol:.1f}x"
    return None, None, f"wait {bias} f:{floor_15} c:{ceil_15}"

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
    print(f"=== V91 PROP {get_time()} ===")
    for s in SYMBOLS:
        d5 = kl(s,"Min5"); d15 = kl(s,"Min15"); d4 = kl(s,"Hour4"); d1 = kl(s,"Day1")
        if not d5 or not d15 or not d4 or not d1: continue

        # PROP: Daily decides direction
        daily_trend = "up" if d1["c"][-1] > d1["c"][-20] else "down"
        bias = "BUY" if daily_trend=="up" else "SELL"

        floor_d = find_pool(d1["l"], d5["c"][-1], 100)
        ceil_d = find_pool(d1["h"], d5["c"][-1], 100)
        floor_4 = find_pool(d4["l"], d5["c"][-1], 80)
        ceil_4 = find_pool(d4["h"], d5["c"][-1], 80)

        # BLOCK if no daily structure to sell/buy into
        if bias=="BUY" and not floor_d:
            print(f"{s} SKIP BUY bias but no Daily floor")
            continue
        if bias=="SELL" and not ceil_d:
            print(f"{s} SKIP SELL bias but no Daily ceiling")
            continue

        direction, pool_15, reason = guard_15_5_prop(d15, d5, bias)
        print(f"{s} BIAS:{bias} D:{floor_d}/{ceil_d} 4H:{floor_4}/{ceil_4} 15M:{pool_15} 5M:{reason} -> {direction}")
        if not direction: continue

        cd = COOLDOWN_MAP.get(s, DEFAULT_CD)
        if time.time()-COOLDOWN["signals"].get(s,0)<cd: continue
        live = get_live_price(s) or d5["c"][-1]
        atr5 = sum([d5["h"][i]-d5["l"][i] for i in range(-20,0)])/20
        is_buy = direction=="BUY"
        sl = min(live-atr5*3, pool_15*0.997) if is_buy else max(live+atr5*3, pool_15*1.003)
        tp1 = live+atr5*3 if is_buy else live-atr5*3
        tp2 = live+atr5*6 if is_buy else live-atr5*6
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
        tg(f"{'🟢 BUY' if is_buy else '🔴 SELL'} {s} BIAS {bias}\n{reason}\n15M pool {pool_15:.5f} | 4H wall {floor_4 if is_buy else ceil_4}\nDaily {floor_d}/{ceil_d} trend {daily_trend}\nENTRY {live:.5f} SL {sl:.5f} TP2 {tp2:.5f}\n{get_time()}")
        break

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
