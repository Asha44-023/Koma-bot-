import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8500000000:XXXX"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT_ID"
COOLDOWN_FILE, ACTIVE_FILE = "cooldown.json", "active.json"
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
    sec_map = {"Min5":300,"Hour4":14400,"Day1":86400}
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
        if abs(v-cur_price)/cur_price < 0.005: continue
        if abs(v-cur_price)/cur_price > 0.08: continue
        cnt = sum(1 for x in arr if abs(x-v)/v < 0.004)
        if cnt >= 3: cands[v]=cnt
    if not cands: return None
    return max(cands, key=lambda k: cands[k])

def guard_5m(d):
    c,h,l,v = d["c"], d["h"], d["l"], d["v"]
    if len(c)<60: return None, None, "short"
    floor = find_pool(l, c[-1], 60)
    ceil = find_pool(h, c[-1], 60)
    if not floor and not ceil: return None, None, "no pool"
    med_wick = sorted([h[i]-l[i] for i in range(-30,-2)])[14]
    med_vol = sorted(v[-30:-2])[14] or 1
    sw = {"h":h[-2],"l":l[-2],"v":v[-2]}
    now = c[-1]
    absorbed = (sw["h"]-sw["l"]) > med_wick*1.2 and sw["v"] > med_vol*1.2
    if floor and sw["l"] < floor and now > floor and now > (sw["h"]+sw["l"])/2 and absorbed:
        return "BUY", floor, f"swept {floor:.5f} {sw['v']/med_vol:.1f}x"
    if ceil and sw["h"] > ceil and now < ceil and now < (sw["h"]+sw["l"])/2 and absorbed:
        return "SELL", ceil, f"swept {ceil:.5f} {sw['v']/med_vol:.1f}x"
    return None, None, f"wait f:{floor} c:{ceil}"

def scan():
    # manage TP/SL
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
    print(f"=== V88 5M+4H+DAILY {get_time()} ===")
    for s in SYMBOLS:
        d5 = kl(s,"Min5"); d4 = kl(s,"Hour4"); d1 = kl(s,"Day1")
        if not d5 or not d4 or not d1: continue

        # DAILY FILTER
        daily_trend = "up" if d1["c"][-1] > d1["c"][-20] else "down"
        floor_d = find_pool(d1["l"], d5["c"][-1], 100)
        ceil_d = find_pool(d1["h"], d5["c"][-1], 100)
        floor_4 = find_pool(d4["l"], d5["c"][-1], 80)
        ceil_4 = find_pool(d4["h"], d5["c"][-1], 80)

        # 4H WALL ALERT
        if s in ACTIVE:
            now = d5["c"][-1]; entry = ACTIVE[s]["entry"]; is_buy = ACTIVE[s]["is_buy"]
            profit = (now-entry)/entry if is_buy else (entry-now)/entry
            if profit > 0.015 and time.time()-COOLDOWN["wall"].get(s,0)>3600:
                if is_buy and ceil_4 and abs(ceil_4-now)/now < 0.015:
                    tg(f"⚠️ 4H WALL CLOSE {s} LONG +{profit:.2%} wall {ceil_4:.5f}\n{get_time()}"); COOLDOWN["wall"][s]=time.time(); save_c()
                if not is_buy and floor_4 and abs(now-floor_4)/now < 0.015:
                    tg(f"⚠️ 4H WALL CLOSE {s} SHORT +{profit:.2%} wall {floor_4:.5f}\n{get_time()}"); COOLDOWN["wall"][s]=time.time(); save_c()

        direction, pool, reason = guard_5m(d5)
        # daily filter - no counter trend
        if direction=="BUY" and daily_trend=="down" and d5["c"][-1] < floor_d: direction=None
        if direction=="SELL" and daily_trend=="up" and d5["c"][-1] > ceil_d: direction=None

        print(f"{s} D:{floor_d}/{ceil_d} 4H:{floor_4}/{ceil_4} 5M:{reason} -> {direction}")
        if not direction: continue
        if time.time()-COOLDOWN["signals"].get(s,0)<3600: continue
        live = get_live_price(s) or d5["c"][-1]
        atr = sum([d4["h"][i]-d4["l"][i] for i in range(-14,0)])/14
        is_buy = direction=="BUY"
        sl = live-atr*1.5 if is_buy else live+atr*1.5
        tp1 = live+atr*1.5 if is_buy else live-atr*1.5
        tp2 = live+atr*3 if is_buy else live-atr*3
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
        tg(f"{'🟢 BUY' if is_buy else '🔴 SELL'} {s}\n5M {reason}\n4H wall {floor_4 if is_buy else ceil_4}\nDaily {floor_d}/{ceil_d} trend {daily_trend}\nENTRY {live:.5f} SL {sl:.5f} TP2 {tp2:.5f}\n{get_time()}")
        break

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
