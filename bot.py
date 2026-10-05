import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","C_USDT","G_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE, STATS_FILE = "active.json", "cooldown.json", "stats.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"wall":{},"daily_pnl":0,"last_day":"2026-10-04"}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
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
def get_funding(s):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/funding_rate/{s}", timeout=5).json()
        return float(r.get("data", r).get("fundingRate", 0))*100
    except: return 0
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
    return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":get_tick(d),"face":shape,"shape":shape,"expected":exp,"tf":label}
def find_box(d, live, label):
    for off in range(1,20):
        end=len(d["h"])-off; start=end-12
        if start<0: break
        HH=max(d["h"][start:end]); LL=min(d["l"][start:end]); rng=HH-LL or 0.00001
        if live>HH: return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":get_tick(d),"face":"RECT_ACC","shape":"RECT_ACC","expected":"UP","tf":f"{label} BROKE {off}c ago"}
        if live<LL: return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":get_tick(d),"face":"RECT_DIST","shape":"RECT_DIST","expected":"DOWN","tf":f"{label} BROKE {off}c ago"}
    return None
def get_day_bias(d1,d4):
    b=detect_shape(d1,"DAY")
    if not b:
        hl=sum(1 for i in range(1,20) if d4["l"][-i]>d4["l"][-i-1])
        return ("BULLISH" if hl>=12 else "BEARISH"), None
    if b["face"] in BULL_SHAPES: return "BULLISH", b
    if b["face"] in BEAR_SHAPES: return "BEARISH", b
    return "NEUTRAL", b
def guard_V116(d15,d5,d4,d1,symbol):
    bias, dbox = get_day_bias(d1,d4)
    if not dbox: return None,None,"no day box",None,None,None,bias
    if bias=="NEUTRAL": return None,None,f"NEUTRAL {dbox['face']}",None,None,dbox,bias
    live=get_live_price(symbol) or d5["c"][-1]
    hbox=find_box(d4,live,"4H")
    if not hbox: return None,None,"no 4H break",None,None,dbox,bias
    HH,LL=hbox["HH"],hbox["LL"]; rng=hbox["range"]
    c15=d15["c"][-1]
    if bias=="BULLISH" and hbox["expected"]=="UP":
        if LL < c15 < HH and abs(c15 - hbox["lvl_38"]) < rng*0.25:
            return "BUY", LL-hbox["tick"]*10, f"V116 BULL {dbox['face']} + {hbox['tf']} + 38% RETEST", HH, LL, dbox, bias
    if bias=="BEARISH" and hbox["expected"]=="DOWN":
        if LL < c15 < HH and abs(c15 - hbox["lvl_62"]) < rng*0.25:
            return "SELL", HH+hbox["tick"]*10, f"V116 BEAR {dbox['face']} + {hbox['tf']} + 62% RETEST", HH, LL, dbox, bias
    return None,None,f"{bias} wait retest {dbox['face']} inside {c15:.4f} vs 38:{hbox['lvl_38']:.4f} 62:{hbox['lvl_62']:.4f}",HH,LL,dbox,bias
def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today:
        COOLDOWN["daily_pnl"]=0; COOLDOWN["last_day"]=today; save_c()
    if COOLDOWN["daily_pnl"] <= -3: print(f"PAUSE daily {COOLDOWN['daily_pnl']}"); return
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
    if len(ACTIVE)>=3:
        print(f"V116 FULL ACTIVE:{len(ACTIVE)}"); return
    print(f"--- SCAN {get_time()} ---")
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1:
                print(f"{s:12} no data"); continue
            direction, pool, reason, HH, LL, dbox, bias = guard_V116(d15,d5,d4,d1,s)
            if dbox:
                face=dbox['face']
                if HH: print(f"{s.replace('_USDT',''):10} DAY:{bias:8} {face:12} {reason}")
                else: print(f"{s.replace('_USDT',''):10} DAY:{bias:8} {face:12} {reason}")
            else:
                print(f"{s:10} {reason}")
            if not direction: continue
            if time.time()-COOLDOWN["signals"].get(s,0) < 14400: print(" -> SKIP cooldown"); continue
            fund=get_funding(s)
            if fund>=0.08 and direction=="BUY": print(f" -> SKIP funding {fund}"); continue
            if fund<=-0.08 and direction=="SELL": print(f" -> SKIP funding {fund}"); continue
            live=get_live_price(s) or d5["c"][-1]
            is_buy=direction=="BUY"
            tick=(HH-LL)/10 if HH and LL else live*0.002
            tp1=live+tick*5 if is_buy else live-tick*5
            tp2=tp1*1.008 if is_buy else tp1*0.992
            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":pool,"tp1":tp1,"tp2":tp2,"HH":HH,"LL":LL,"time":time.time(),"face":dbox["face"]}; save_a()
            COOLDOWN["signals"][s]=time.time(); save_c()
            if is_buy:
                tg(f"🟢 BUY {s.replace('_USDT','')} @ {live:.6f}\n{bias} {dbox['face']}\n{reason}\nSL {pool:.6f} | TP {tp1:.6f} -> {tp2:.6f}\nV116 {get_time()}")
            else:
                tg(f"🔴 SELL {s.replace('_USDT','')} @ {live:.6f}\n{bias} {dbox['face']}\n{reason}\nSL {pool:.6f} | TP {tp1:.6f} -> {tp2:.6f}\nV116 {get_time()}")
            break
        except Exception as e:
            print(f"{s} err {e}"); continue
    print(f"V116 done {get_time()} ACTIVE:{len(ACTIVE)} checked {len(SYMBOLS)}")
if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(10)
