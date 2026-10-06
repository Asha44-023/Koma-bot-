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
# MIGRATION V131 -> V134
for k,v in list(ACTIVE.items()):
    if "tp3" not in v and "tp2" in v:
        v["tp3"] = v["tp2"]*1.015 if v.get("is_buy") else v["tp2"]*0.985
    if "tp1_hit" not in v: v["tp1_hit"]=False
    if "tp2_hit" not in v: v["tp2_hit"]=False

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
    if COOLDOWN.get("daily_pnl",0) < -8:
        print(f"PAUSED DAILY LOSS {COOLDOWN['daily_pnl']:.2f}%"); return
    for s,data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        tp1=data.get("tp1"); tp2=data.get("tp2"); tp3=data.get("tp3", tp2)
        if tp1 is None or tp2 is None:
            del ACTIVE[s]; save_a(); continue
        try:
            d4r=kl(s,"Hour4"); d1r=kl(s,"Day1")
            if d4r and d1r:
                dr=get_4h_dir(d4r); sr,_,_,_ = daily_ship(d1r)
                if is_buy and dr=="BEARISH" and sr in ("DESC_TRI","RISE_WEDGE","RECT_DIST"):
                    pnl=(p-entry)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c()
                    tg(f"⚠️ REVERSAL SELL {s.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); del ACTIVE[s]; save_a(); continue
                if not is_buy and dr=="BULLISH" and sr in ("ASC_TRI","FALL_WEDGE","RECT_ACC"):
                    pnl=(entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c()
                    tg(f"⚠️ REVERSAL BUY {s.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); del ACTIVE[s]; save_a(); continue
        except: pass
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {s.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            tg(f"💚 TP1 {s.replace('_USDT','')} @ {fmt(p)} -> SL BE")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp2_hit"]=True; data["sl"]=tp1; save_a()
            tg(f"💚💚 TP2 {s.replace('_USDT','')} +{((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100):.2f}% -> TRAIL SL {fmt(tp1)}")
        if (is_buy and p>=tp3) or (not is_buy and p<=tp3):
            profit=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"💚💚💚 TP3 {s.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)}"); del ACTIVE[s]; save_a()

    print(f"--- SCAN V134 COUNTER TP/SL {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% ---")
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
            broke_up = live > box["HH"]*1.001
            broke_down = live < box["LL"]*0.999
            direction=None
            is_counter=False
            if ship=="RISE_WEDGE" and broke_down: direction="SELL"; is_counter=True
            elif ship=="FALL_WEDGE" and broke_up: direction="BUY"; is_counter=True
            elif ship=="RECT_DIST" and broke_down: direction="SELL"; is_counter=(dir4h=="BULLISH")
            elif ship=="RECT_ACC" and broke_up: direction="BUY"; is_counter=(dir4h=="BEARISH")
            elif ship=="ASC_TRI" and broke_up: direction="BUY"
            elif ship=="DESC_TRI" and broke_down: direction="SELL"
            elif ship in ("SYM_TRI","RECT"):
                if broke_up: direction="BUY"
                elif broke_down: direction="SELL"
            if not direction: continue
            sym=s.replace("_USDT","")
            is_buy=direction=="BUY"
            HH,LL=box["HH"],box["LL"]
            tp1_liq, tp2_liq = next_liquidity(d15, HH, LL, direction)
            if is_buy:
                sl_pct = 0.008 if is_counter else 0.012
                sl = LL*0.995 if is_counter else LL*0.992
                sl = max(sl, live*(1-sl_pct))
                tp1 = max(tp1_liq, live*1.01)
                tp2 = max(tp2_liq, live*1.025)
                tp3 = max(tp2_liq*1.015, live*1.04)
                rr=(tp2-live)/(live-sl) if live!=sl else 0
                if rr<1.2: continue
                tag="🔄 COUNTER BUY" if is_counter else "💚 BUY"
                msg=f"{tag} {sym} @ {fmt(live)}\nShip:{ship} 4H:{dir4h}\n🛡️ SL {fmt(sl)} ({(sl/live-1)*100:.2f}%)\n🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}"
            else:
                sl_pct = 0.008 if is_counter else 0.012
                sl = HH*1.005 if is_counter else HH*1.008
                sl = min(sl, live*(1+sl_pct))
                tp1 = min(tp1_liq, live*0.99)
                tp2 = min(tp2_liq, live*0.975)
                tp3 = min(tp2_liq*0.985, live*0.96)
                rr=(live-tp2)/(sl-live) if sl!=live else 0
                if rr<1.2: continue
                tag="🔄 COUNTER SELL" if is_counter else "❤️ SELL"
                msg=f"{tag} {sym} @ {fmt(live)}\nShip:{ship} 4H:{dir4h}\n🛡️ SL {fmt(sl)} ({(sl/live-1)*100:+.2f}%)\n🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}"
            cands.append((rr,s,msg,live,is_buy,sl,tp1,tp2,tp3,HH,LL,ship))
        except Exception as e: print(f"{s} err {e}"); continue
    cands.sort(key=lambda x: x[0], reverse=True)
    print(f"FOUND {len(cands)} -> TOP 3")
    for rr,s,msg,live,is_buy,sl,tp1,tp2,tp3,HH,LL,ship in cands[:3]:
        if len(ACTIVE)>=5: break
        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"HH":HH,"LL":LL,"time":time.time(),"face":ship,"tp1_hit":False,"tp2_hit":False}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
        tg(msg); time.sleep(1)

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(15)
