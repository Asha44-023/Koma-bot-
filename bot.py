import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","SUI_USDT","PHA_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT"]
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
def fmt(p):
    if p is None: return "0"
    if p < 0.01: return f"{p:.8f}"
    elif p < 1: return f"{p:.6f}"
    else: return f"{p:.4f}"
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

def daily_ship(d1):
    h=d1["h"][-20:]; l=d1["l"][-20:]; c=d1["c"][-20:]
    HH=max(h); LL=min(l); rng=HH-LL or 0.00001
    h0,h1=h[0],h[-1]; l0,l1=l[0],l[-1]
    flat=rng*0.35
    if abs(h1-h0)<flat and l1>l0+flat: return "ASC_TRI","UP",HH,LL
    if abs(l1-l0)<flat and h1<h0-flat: return "DESC_TRI","DOWN",HH,LL
    if h1<h0-flat and l1>l0+flat: return "SYM_TRI","BOTH",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat and c[-1]>sum(c[-12:-6])/6: return "RECT_ACC","UP",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat: return "RECT_DIST","DOWN",HH,LL
    if h1>h0+flat and l1>l0+flat: return "RISE_WEDGE","DOWN",HH,LL
    if h1<h0-flat and l1<l0-flat: return "FALL_WEDGE","UP",HH,LL
    return "RECT","BOTH",HH,LL

def get_4h_dir(d4):
    c=d4["c"][-20:]; s10=sum(c[-10:])/10; s20=sum(c[-20:])/20
    if s10 > s20*1.002: return "BULLISH"
    if s10 < s20*0.998: return "BEARISH"
    return "NEUTRAL"

def get_15m_box(d15):
    h=d15["h"][-80:]; l=d15["l"][-80:]; c=d15["c"][-80:]
    best=None; best_score=0
    for wid in range(10,35):
        for off in range(1,40):
            end=len(h)-off; start=end-wid
            if start<0: continue
            HH=max(h[start:end]); LL=min(l[start:end]); rng=HH-LL
            full=max(h)-min(l) or rng
            if rng>full*0.7 or rng<full*0.03: continue
            touches=sum(1 for i in range(start,end) if abs(h[i]-HH)<rng*0.15 or abs(l[i]-LL)<rng*0.15)
            if touches>best_score:
                best_score=touches
                best={"HH":HH,"LL":LL,"rng":rng,"touches":touches}
    return best

def next_liquidity(d15, box_HH, box_LL, direction):
    h=d15["h"][-80:]; l=d15["l"][-80:]
    zones_up=[]; zones_down=[]
    for i in range(10, len(h)-10):
        hh=max(h[i-5:i+5]); ll=min(l[i-5:i+5])
        if hh > box_HH*1.005 and (hh-ll) < (max(h)-min(l))*0.15:
            zones_up.append(hh)
        if ll < box_LL*0.995 and (hh-ll) < (max(h)-min(l))*0.15:
            zones_down.append(ll)
    liq_up=[h[i] for i in range(2,len(h)-2) if h[i]>h[i-1] and h[i]>h[i+1] and h[i]>box_HH]
    liq_down=[l[i] for i in range(2,len(l)-2) if l[i]<l[i-1] and l[i]<l[i+1] and l[i]<box_LL]
    if direction=="BUY":
        next1 = min(zones_up+liq_up, default=box_HH*1.03)
        next2 = min([x for x in zones_up+liq_up if x>next1], default=next1*1.02)
        return next1, next2
    else:
        next1 = max(zones_down+liq_down, default=box_LL*0.97)
        next2 = max([x for x in zones_down+liq_down if x<next1], default=next1*0.98)
        return next1, next2

def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today:
        COOLDOWN["daily_pnl"]=0; COOLDOWN["last_day"]=today; save_c()
    for s,data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            sym=s.replace("_USDT","")
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {sym} {pnl:.2f}% @ {fmt(p)}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            sym=s.replace("_USDT","")
            tg(f"💚 TP1 {sym} @ {fmt(p)} -> SL BE")
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            profit=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            sym=s.replace("_USDT","")
            tg(f"💚 TP2 {sym} +{profit:.2f}% CLOSED"); del ACTIVE[s]; save_a()

    print(f"--- SCAN V131 GREEN/RED {get_time()} ---")
    if len(ACTIVE)>=5: return
    cands=[]
    for s in SYMBOLS:
        try:
            if s in ACTIVE: continue
            d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d15 or not d4 or not d1: continue
            ship, ship_dir, _, _ = daily_ship(d1)
            dir4h = get_4h_dir(d4)
            box = get_15m_box(d15)
            live=get_live_price(s) or d15["c"][-1]
            if not box: continue
            if time.time()-COOLDOWN["signals"].get(s,0) < 1800: continue
            print(f"{s.replace('_USDT',''):10} DAY:{ship:12} {ship_dir:4} 4H:{dir4h:8} Box:{fmt(box['LL'])}-{fmt(box['HH'])}")
            if ship_dir=="BOTH":
                if dir4h=="NEUTRAL": continue
                want = "UP" if dir4h=="BULLISH" else "DOWN"
            else:
                if ship_dir=="UP" and dir4h=="BEARISH": continue
                if ship_dir=="DOWN" and dir4h=="BULLISH": continue
                want = ship_dir
                if dir4h!="NEUTRAL":
                    want = "UP" if dir4h=="BULLISH" else "DOWN"
            broke_up = live > box["HH"]*1.001
            broke_down = live < box["LL"]*0.999
            direction=None
            if want=="UP" and broke_up: direction="BUY"
            elif want=="DOWN" and broke_down: direction="SELL"
            if not direction: continue
            sym=s.replace("_USDT","")
            is_buy=direction=="BUY"
            HH,LL=box["HH"],box["LL"]
            tp1_liq, tp2_liq = next_liquidity(d15, HH, LL, direction)
            if is_buy:
                sl=LL*0.992
                tp1=max(tp1_liq, live*1.01); tp2=max(tp2_liq, live*1.025)
                rr=(tp2-live)/(live-sl) if live!=sl else 0
                if rr<1.2: continue
                msg=f"💚 {ship}\n💚 BUY {sym} @ {fmt(live)}\n🛡️ SL {fmt(sl)}\n🎯 TP {fmt(tp1)} / {fmt(tp2)}"
            else:
                sl=HH*1.008
                tp1=min(tp1_liq, live*0.99); tp2=min(tp2_liq, live*0.975)
                rr=(live-tp2)/(sl-live) if sl!=live else 0
                if rr<1.2: continue
                msg=f"❤️ {ship}\n❤️ SELL {sym} @ {fmt(live)}\n🛡️ SL {fmt(sl)}\n🎯 TP {fmt(tp1)} / {fmt(tp2)}"
            cands.append((rr,s,msg,live,is_buy,sl,tp1,tp2,HH,LL,ship))
        except Exception as e: print(f"{s} err {e}"); continue
    cands.sort(key=lambda x: x[0], reverse=True)
    print(f"FOUND {len(cands)} -> TOP 3")
    for rr,s,msg,live,is_buy,sl,tp1,tp2,HH,LL,ship in cands[:3]:
        if len(ACTIVE)>=5: break
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"HH":HH,"LL":LL,"time":time.time(),"face":ship}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
        tg(msg); time.sleep(1)

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(15)
