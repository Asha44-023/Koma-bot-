import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","C_USDT","G_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"daily_pnl":0,"last_day":"2026-10-04"}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":m}, timeout=10)
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
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]]}
    except: return None
def get_live_price(s):
    for try_sym in [s, s.replace("_","")]:
        try:
            r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={try_sym}", timeout=5).json()
            return float((r.get("data", r))["lastPrice"])
        except: pass
    return None

BULL_SHAPES = ["FALL_WEDGE","BULL_FLAG","ASC_TRI","RECT_ACC","SYM_TRI"]
BEAR_SHAPES = ["RISE_WEDGE","BEAR_FLAG","DESC_TRI","RECT_DIST"]

def get_tick(d):
    h=d["h"][-20:]; l=d["l"][-20:]
    avg = sum(h[i]-l[i] for i in range(20))/20
    return max(avg/10, 0.00001)

def detect_shape(d, label=""):
    if len(d["c"])<14: return None
    h=d["h"][-12:]; l=d["l"][-12:]
    HH=max(h); LL=min(l); rng=HH-LL or 0.00001
    flat=rng*0.35
    h0,h1=h[0],h[-1]; l0,l1=l[0],l[-1]
    shape="RECT_ACC"; exp="UP"
    if abs(h1-h0)<flat and abs(l1-l0)<flat:
        shape="RECT_ACC" if l1>=l0 else "RECT_DIST"; exp="UP" if shape=="RECT_ACC" else "DOWN"
    elif abs(h1-h0)<flat and l1>l0+flat: shape="ASC_TRI"; exp="UP"
    elif abs(l1-l0)<flat and h1<h0-flat: shape="DESC_TRI"; exp="DOWN"
    elif h1<h0-flat and l1<l0-flat:
        shape="FALL_WEDGE" if abs(h1-h0)>abs(l1-l0)*1.2 else "BULL_FLAG"; exp="UP"
    elif h1>h0+flat and l1>l0+flat:
        shape="RISE_WEDGE" if abs(l1-l0)>abs(h1-h0)*1.2 else "BEAR_FLAG"; exp="DOWN"
    elif h1<h0-flat and l1>l0+flat: shape="SYM_TRI"; exp="UP"
    return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":get_tick(d),"face":shape,"expected":exp,"tf":label}

def get_day_bias(d1,d4):
    b=detect_shape(d1,"DAY")
    if not b:
        hl=sum(1 for i in range(1,20) if d4["l"][-i]>d4["l"][-i-1])
        return ("BULLISH" if hl>=12 else "BEARISH"), None
    if b["face"] in BULL_SHAPES: return "BULLISH", b
    if b["face"] in BEAR_SHAPES: return "BEARISH", b
    return "NEUTRAL", b

def find_today_box(d15, live):
    now = datetime.now(EAT)
    candles_since_midnight = int((now.hour*60 + now.minute)/15) + 1
    candles_since_midnight = min(candles_since_midnight, len(d15["h"])-5)
    if candles_since_midnight < 12: return None
    h_today = d15["h"][-candles_since_midnight:]
    l_today = d15["l"][-candles_since_midnight:]
    for off in range(1, candles_since_midnight-8):
        end = len(h_today)-off
        start = end-10
        if start < 0: break
        HH = max(h_today[start:end])
        LL = min(l_today[start:end])
        rng = HH-LL or 0.00001
        today_range = max(h_today)-min(l_today) or rng
        if rng > today_range*0.5: continue
        if live > HH*1.002:
            return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":rng/10,"expected":"UP","tf":f"TODAY BROKE {off*15}m ago Box {LL:.4f}-{HH:.4f}"}
        if live < LL*0.998:
            return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":rng/10,"expected":"DOWN","tf":f"TODAY BROKE {off*15}m ago Box {LL:.4f}-{HH:.4f}"}
    return None

def guard_V117(d15,d5,d4,d1,symbol):
    bias, dbox = get_day_bias(d1,d4)
    if not dbox: return None,None,"no day box",None,None,None,bias
    if bias=="NEUTRAL": return None,None,f"NEUTRAL {dbox['face']}",None,None,dbox,bias
    live=get_live_price(symbol) or d5["c"][-1]
    hbox=find_today_box(d15, live)
    if not hbox: return None,None,f"no TODAY break yet (flat since open)",None,None,dbox,bias
    HH,LL=hbox["HH"],hbox["LL"]; rng=hbox["range"]
    c15=d15["c"][-1]
    if bias=="BULLISH" and hbox["expected"]=="UP":
        if LL*0.99 < c15 < HH*1.01 or abs(c15 - hbox["lvl_38"]) < rng*0.40:
            return "BUY", LL-hbox["tick"]*2, f"V118 BULL {dbox['face']} + {hbox['tf']} + RETEST {c15:.4f}~38% {hbox['lvl_38']:.4f}", HH, LL, dbox, bias
    if bias=="BEARISH" and hbox["expected"]=="DOWN":
        if LL*0.99 < c15 < HH*1.01 or abs(c15 - hbox["lvl_62"]) < rng*0.40:
            return "SELL", HH+hbox["tick"]*2, f"V118 BEAR {dbox['face']} + {hbox['tf']} + RETEST {c15:.4f}~62% {hbox['lvl_62']:.4f}", HH, LL, dbox, bias
    return None,None,f"{bias} broke but price {c15:.4f} not back to box {LL:.4f}-{HH:.4f}",HH,LL,dbox,bias

def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today:
        COOLDOWN["daily_pnl"]=0; COOLDOWN["last_day"]=today; save_c()
    if COOLDOWN["daily_pnl"] <= -3: print(f"PAUSE {COOLDOWN['daily_pnl']}"); return
    for s,data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"🔴 STOP {s} {pnl:.2f}% {get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            tg(f"🟢 TP1 {s} @ {p:.5f} {get_time()}")
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            profit=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"🟢🟢 TP2 {s} +{profit:.2f}% {get_time()}"); del ACTIVE[s]; save_a()
    if len(ACTIVE)>=3: print(f"FULL {len(ACTIVE)}"); return
    print(f"--- SCAN V118 LIQUIDITY {get_time()} ---")
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1: print(f"{s:12} no data"); continue
            direction, pool, reason, HH, LL, dbox, bias = guard_V117(d15,d5,d4,d1,s)
            face=dbox['face'] if dbox else "NO-BOX"
            print(f"{s.replace('_USDT',''):10} DAY:{bias:8} {face:12} -> {reason}")
            if not direction: continue
            if time.time()-COOLDOWN["signals"].get(s,0) < 3600: print(" -> SKIP 1h cooldown"); continue
            live=get_live_price(s) or d5["c"][-1]
            is_buy=direction=="BUY"

            # === V118 LIQUIDITY LOOP TP ===
            now = datetime.now(EAT)
            candles_since_midnight = int((now.hour*60 + now.minute)/15) + 1
            candles_since_midnight = min(candles_since_midnight, len(d15["h"]))
            today_high = max(d15["h"][-candles_since_midnight:])
            today_low = min(d15["l"][-candles_since_midnight:])
            yest_high = d1["h"][-2]
            yest_low = d1["l"][-2]

            if is_buy:
                tp1 = today_high
                tp2 = max(yest_high, today_high*1.005)
                # ensure at least 1% / 2.5%
                tp1 = max(tp1, live*1.01)
                tp2 = max(tp2, live*1.025)
            else:
                tp1 = today_low
                tp2 = min(yest_low, today_low*0.995)
                tp1 = min(tp1, live*0.99)
                tp2 = min(tp2, live*0.975)

            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":pool,"tp1":tp1,"tp2":tp2,"HH":HH,"LL":LL,"time":time.time(),"face":face}; save_a()
            COOLDOWN["signals"][s]=time.time(); save_c()
            tg(f"{'🟢 BUY' if is_buy else '🔴 SELL'} {s.replace('_USDT','')} @ {live:.6f}\n{bias} {face}\n{reason}\nSL {pool:.6f} | TP1 {tp1:.6f} (TODAY {'HIGH' if is_buy else 'LOW'}) -> TP2 {tp2:.6f} (YEST {'HIGH' if is_buy else 'LOW'})\nV118 LIQ {get_time()}")
            break
        except Exception as e:
            print(f"{s} err {e}"); continue
    print(f"V118 done {get_time()} ACTIVE:{len(ACTIVE)}")

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(10)
