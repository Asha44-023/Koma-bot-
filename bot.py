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
    liq_up=[h[i] for i in range(2,len(h)-2) if h[i]>h[i-1] and h[i]>h[i+1] and h[i]>box_HH]
    liq_down=[l[i] for i in range(2,len(l)-2) if l[i]<l[i-1] and l[i]<l[i+1] and l[i]<box_LL]
    if direction=="BUY":
        n1=min(liq_up, default=box_HH*1.03); n2=min([x for x in liq_up if x>n1], default=n1*1.02)
        return n1,n2
    else:
        n1=max(liq_down, default=box_LL*0.97); n2=max([x for x in liq_down if x<n1], default=n1*0.98)
        return n1,n2

def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today:
        COOLDOWN["daily_pnl"]=0; COOLDOWN["last_day"]=today; save_c()
    if COOLDOWN.get("daily_pnl",0) < -8: print(f"PAUSED {COOLDOWN['daily_pnl']:.2f}%"); return

    for s,data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        tp1,tp2,tp3=data["tp1"],data["tp2"],data["tp3"]

        # REVERSAL EXIT
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

        # SL HIT
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {s.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)} SL:{fmt(sl)}"); del ACTIVE[s]; save_a(); continue

        # TP1 -> BE
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            tg(f"💚 TP1 HIT {s.replace('_USDT','')} +1% @ {fmt(p)} -> SL BE {fmt(entry)}\nNext TP2 {fmt(tp2)} TP3 {fmt(tp3)}")

        # TP2 -> Trail 50%
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp2_hit"]=True
            # trail SL to TP1 level
            data["sl"]=tp1 if is_buy else tp1
            save_a()
            tg(f"💚💚 TP2 HIT {s.replace('_USDT','')} +2.5% @ {fmt(p)} -> TRAIL SL to TP1 {fmt(tp1)}\nFinal TP3 {fmt(tp3)}")

        # TP3 CLOSE
        if (is_buy and p>=tp3) or (not is_buy and p<=tp3):
            profit=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"💚💚💚 TP3 HIT {s.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)}"); del ACTIVE[s]; save_a()

    print(f"--- SCAN V134 TP/SL {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
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
                if dir4h=="BULLISH" and broke_up: direction="BUY"
                elif dir4h=="BEARISH" and broke_down: direction="SELL"

            if not direction: continue
            sym=s.replace("_USDT","")
            is_buy=direction=="BUY"
            HH,LL=box["HH"],box["LL"]
            tp_liq1, tp_liq2 = next_liquidity(d15, HH, LL, direction)

            if is_buy:
                # V134 TP/SL CALC
                sl_pct = 0.008 if is_counter else 0.012
                sl = LL*0.995 if is_counter else LL*0.992
                # hard cap SL by %
                sl = max(sl, live*(1-sl_pct))
                tp1 = live*1.01
                tp2 = live*1.025
                tp3 = max(tp_liq2, live*1.04)
                rr=(tp2-live)/(live-sl) if live!=sl else 0
                if rr<1.2: continue
                tag="🔄 COUNTER BUY" if is_counter else "💚 BUY"
                msg=f"{tag} {sym} @ {fmt(live)}\nShip:{ship} 4H:{dir4h}\n🛡️ SL {fmt(sl)} ({(sl/live-1)*100:.2f}%)\n🎯 TP1 {fmt(tp1)} +1% | TP2 {fmt(tp2)} +2.5% | TP3 {fmt(tp3)}"
            else:
                sl_pct = 0.008 if is_counter else 0.012
                sl = HH*1.005 if is_counter else HH*1.008
                sl = min(sl, live*(1+sl_pct))
                tp1 = live*0.99
                tp2 = live*0.975
                tp3 = min(tp_liq2, live*0.96)
                rr=(live-tp2)/(sl-live) if sl!=live else 0
                if rr<1.2: continue
                tag="🔄 COUNTER SELL" if is_counter else "❤️ SELL"
                msg=f"{tag} {sym} @ {fmt(live)}\nShip:{ship} 4H:{dir4h}\n🛡️ SL {fmt(sl)} ({(sl/live-1)*100:+.2f}%)\n🎯 TP1 {fmt(tp1)} -1% | TP2 {fmt(tp2)} -2.5% | TP3 {fmt(tp3)}"

            cands.append((rr,s,msg,live,is_buy,sl,tp1,tp2,tp3,HH,LL,ship))
            print(f"{sym:10} {ship:12} {dir4h:8} {direction} RR:{rr:.2f} SL:{fmt(sl)} TP:{fmt(tp1)}/{fmt(tp2)}/{fmt(tp3)}")
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
