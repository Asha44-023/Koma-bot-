import json, math, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","SUI_USDT","PHA_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT","MUBARAK_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 5, 7200
session = requests.Session()
COUNTER_MIN_RR = 1.1
TREND_MIN_RR = 0.9
TAG = "BOT-ENTRY-V143-HYBRID-RUNNER"
TP_CONFIG = {
    "PUMP": {"TP1": 1.0, "TP2": 2.8, "TP3": 6.0, "RUNNER_TARGET": 20.0, "CLOSE": [40,30,15,15]},
    "TREND": {"TP1": 1.5, "TP2": 4.0, "TP3": 8.5, "RUNNER_TARGET": 15.0, "CLOSE": [30,30,20,20]},
}
PUMP_COINS = ["GRASS_USDT","SENT_USDT","SAND_USDT","SIREN_USDT","KOMA_USDT","LAB_USDT","FARTCOIN_USDT","VELVET_USDT","MUBARAK_USDT"]
def get_tp_config(sym):
    if sym in PUMP_COINS:
        return TP_CONFIG["PUMP"], "PUMP"
    return TP_CONFIG["TREND"], "TREND"
def calc_tps(sym, live, is_buy):
    cfg, typ = get_tp_config(sym)
    if is_buy:
        tp1 = live * (1 + cfg["TP1"]/100)
        tp2 = live * (1 + cfg["TP2"]/100)
        tp3 = live * (1 + cfg["TP3"]/100)
        runner = live * (1 + cfg["RUNNER_TARGET"]/100)
    else:
        tp1 = live * (1 - cfg["TP1"]/100)
        tp2 = live * (1 - cfg["TP2"]/100)
        tp3 = live * (1 - cfg["TP3"]/100)
        runner = live * (1 - cfg["RUNNER_TARGET"]/100)
    return tp1, tp2, tp3, runner, cfg, typ
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f)
        return v if isinstance(v,type(d)) else d
    except: return d
ACTIVE=load_json(ACTIVE_FILE,{})
COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
for s,dat in list(ACTIVE.items()):
    if not isinstance(dat,dict): del ACTIVE[s]; continue
    if "tp3" not in dat and dat.get("tp2"): dat["tp3"]=dat["tp2"]*1.015 if dat.get("is_buy") else dat["tp2"]*0.985
    dat.setdefault("tp1_hit",False); dat.setdefault("tp2_hit",False); dat.setdefault("tp3_hit",False); dat.setdefault("runner_hit",False)
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)); fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tp,path)
    except:
        try: os.unlink(tp)
        except: pass
        raise
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def fmt(p):
    if p is None: return "0"
    if p<0.01: return f"{p:.8f}"
    if p<1: return f"{p:.6f}"
    return f"{p:.4f}"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try: session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT,"text":m},timeout=10)
    except: pass
    print(m)
def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}
    sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=10).json()
        d=r.get("data",r)
        if isinstance(d,dict) and "data" in d: d=d["data"]
        res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]]}
        for k in res: res[k]=res[k][:-1]
        if len(res["c"])<30: return None
        return res
    except: return None
def get_live_price(s):
    for t in [s,s.replace("_","")]:
        try:
            r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json()
            return float((r.get("data",r))["lastPrice"])
        except: pass
    return None
def atr_from_kl(d,period=14):
    h,l,c=d["h"],d["l"],d["c"]; tr=[]
    for i in range(1,len(c)): tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    if len(tr)<period: return tr[-1] if tr else 0.0001
    return sum(tr[-period:])/period
def daily_ship(d1):
    h=d1["h"][-20:]; l=d1["l"][-20:]; c=d1["c"][-20:]
    if len(h)<20: return "RECT","BOTH",max(h),min(l)
    HH=max(h); LL=min(l); rng=HH-LL or 0.00001; h0,h1=h[0],h[-1]; l0,l1=l[0],l[-1]; flat=rng*0.35
    if abs(h1-h0)<flat and l1>l0+flat: return "ASC_TRI","UP",HH,LL
    if abs(l1-l0)<flat and h1<h0-flat: return "DESC_TRI","DOWN",HH,LL
    if h1<h0-flat and l1>l0+flat: return "SYM_TRI","BOTH",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat and c[-1]>sum(c[-12:-6])/6: return "RECT_ACC","UP",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat: return "RECT_DIST","DOWN",HH,LL
    if h1>h0+flat and l1>l0+flat: return "RISE_WEDGE","DOWN",HH,LL
    if h1<h0-flat and l1<l0-flat: return "FALL_WEDGE","UP",HH,LL
    return "RECT","BOTH",HH,LL
def get_1h_box(d1h):
    LOOKBACK = 10
    h=d1h["h"][-LOOKBACK:]; l=d1h["l"][-LOOKBACK:]
    if len(h)<LOOKBACK: return None
    HH=max(h); LL=min(l); rng=HH-LL
    if rng<=0: return None
    mid=(HH+LL)/2
    if rng/mid > 0.25:
        return None
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng,"lookback":LOOKBACK}
def get_4h_dir(d4):
    o,c=d4["o"][-1], d4["c"][-1]
    s10=sum(d4["c"][-10:])/10; s20=sum(d4["c"][-20:])/20
    if c>o and s10>s20*1.001: return "BUY"
    if c<o and s10<s20*0.999: return "SELL"
    return "BUY" if c>o else "SELL"
def check_pullback_15m(d15, box, direction):
    if not d15: return False
    live_c = d15["c"][-1]
    mid_low = box["LL"] + box["rng"]*0.35
    mid_high = box["LL"] + box["rng"]*0.65
    in_mid = mid_low <= live_c <= mid_high
    if direction=="BUY":
        return in_mid and d15["c"][-1] > d15["o"][-1]
    else:
        return in_mid and d15["c"][-1] < d15["o"][-1]
def check_entry_5m(d5, direction):
    if not d5: return False
    o,c = d5["o"][-1], d5["c"][-1]
    if direction=="BUY": return c>o and (c-o)/o > 0.0002
    else: return c<o and (o-c)/o > 0.0002
def next_liquidity(d1,HH,LL,direction):
    h=d1["h"][-20:]; l=d1["l"][-20:]
    liq_up=[x for x in h if x>HH]; liq_down=[x for x in l if x<LL]
    if direction=="BUY":
        lv=sorted(set(liq_up))
        if len(lv)>=2: return lv[0],lv[1]
        if len(lv)==1: return lv[0],lv[0]*1.02
        return HH*1.03,HH*1.06
    else:
        lv=sorted(set(liq_down),reverse=True)
        if len(lv)>=2: return lv[0],lv[1]
        if len(lv)==1: return lv[0],lv[0]*0.98
        return LL*0.97,LL*0.94
def valid_signal_data(d):
    try:
        for k in ("entry","sl","tp1","tp2","tp3"):
            if not math.isfinite(float(d[k])): return False
        return True
    except: return False
def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
        tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        runner_target=float(data.get("runner", tp3*1.15 if is_buy else tp3*0.85))
        cfg_close=data.get("cfg_close",[40,30,15,15])
        if is_buy and not (sl<entry<tp1<tp2<tp3): ACTIVE.pop(sym,None); save_a(); continue
        if not is_buy and not (tp3<tp2<tp1<entry<sl): ACTIVE.pop(sym,None); save_a(); continue
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); ACTIVE.pop(sym,None); save_a(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True
            tg(f"💚 TP1 {sym.replace('_USDT','')} @ {fmt(p)} (-{cfg_close[0]}% closed) -> SL BE | Runner {cfg_close[3]}% left")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚 TP2 {sym.replace('_USDT','')} +{pnl_now:.2f}% (-{cfg_close[1]}%) -> SL to TP1 | TRAIL")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a()
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚💚 TP3 {sym.replace('_USDT','')} +{pnl_now:.2f}% (-{cfg_close[2]}%) -> 15% RUNNER to {fmt(runner_target)}")
            continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"🚀 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% MEGA PUMP CLOSED @ {fmt(p)}")
            ACTIVE.pop(sym,None); save_a()
    print(f"--- SCAN {TAG} {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: print("daily limit hit"); return
    if len(ACTIVE)>=MAX_ACTIVE: print("max active hit"); return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.05)
            d4=kl(sym,"Hour4"); time.sleep(0.05)
            h1=kl(sym,"Min60"); time.sleep(0.05)
            m15=kl(sym,"Min15"); time.sleep(0.05)
            m5=kl(sym,"Min5"); time.sleep(0.05)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            dir4h = get_4h_dir(d4)
            box1h = get_1h_box(h1)
            if not box1h: skipped[sym]=f"no_1H_box_wide"; continue
            live=get_live_price(sym) or h1["c"][-1]
            atr=atr_from_kl(h1,14)
            buf=0.3*atr
            close1h=h1["c"][-1]; open1h=h1["o"][-1]
            broke_up = close1h > box1h["HH"] + buf*0.3 and close1h > open1h
            broke_down = close1h < box1h["LL"] - buf*0.3 and close1h < open1h
            direction=None
            if broke_up and dir4h=="BUY": direction="BUY"
            elif broke_down and dir4h=="SELL": direction="SELL"
            else:
                if broke_up: direction="BUY"
                elif broke_down: direction="SELL"
            if not direction:
                skipped[sym]=f"no_break_1H 4H={dir4h} 1H_Box={fmt(box1h['LL'])}-{fmt(box1h['HH'])} cur={fmt(live)}"
                continue
            if not check_pullback_15m(m15, box1h, direction):
                skipped[sym]=f"no_pullback_15M dir={direction} 1HBox={fmt(box1h['LL'])}-{fmt(box1h['HH'])}"
                continue
            if not check_entry_5m(m5, direction):
                skipped[sym]=f"no_entry_5M dir={direction}"
                continue
            ship,_,_,_=daily_ship(d1)
            is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            liq1,liq2=next_liquidity(d1,HH,LL,direction)
            tp1_raw, tp2_raw, tp3_raw, runner_raw, cfg, typ = calc_tps(sym, live, is_buy)
            if is_buy:
                tp1=max(tp1_raw, liq1 if liq1>live else tp1_raw)
                tp2=max(tp2_raw, liq2 if liq2>live else tp2_raw)
                tp3=max(tp3_raw, tp2*1.02)
                runner=max(runner_raw, tp3*1.12)
                sl = min(LL*0.993, live*0.993, close1h - buf*1.1)
            else:
                tp1=min(tp1_raw, liq1 if liq1<live else tp1_raw)
                tp2=min(tp2_raw, liq2 if liq2<live else tp2_raw)
                tp3=min(tp3_raw, tp2*0.98)
                runner=min(runner_raw, tp3*0.88)
                sl = max(HH*1.007, live*1.007, close1h + buf*1.1)
            if is_buy:
                if not (sl<live<tp1<tp2<tp3): skipped[sym]="bad_levels"; continue
                rr=(tp2-live)/(live-sl) if live!=sl else 0
            else:
                if not (tp3<tp2<tp1<live<sl): skipped[sym]="bad_levels"; continue
                rr=(live-tp2)/(sl-live) if sl!=live else 0
            is_counter = (direction!=dir4h)
            if is_counter and rr < COUNTER_MIN_RR: skipped[sym]=f"counter_rr_low {rr:.2f}"; continue
            if not is_counter and rr < TREND_MIN_RR: skipped[sym]=f"trend_rr_low {rr:.2f}"; continue
            if time.time()-COOLDOWN["signals"].get(sym,0)<SYMBOL_COOLDOWN_SECONDS: skipped[sym]="cooldown"; continue
            tag="🔄 COUNTER BUY" if is_buy and is_counter else "🔄 COUNTER SELL" if not is_buy and is_counter else "💚 BUY" if is_buy else "❤️ SELL"
            stop_pct=(sl/live-1)*100
            msg=f"{tag} {sym.replace('_USDT','')} @ {fmt(live)} [{typ} {cfg['TP1']}/{cfg['TP2']}/{cfg['TP3']}% + RUNNER {cfg['RUNNER_TARGET']}%]\n4H:{dir4h} 1H-Box:{fmt(LL)}-{fmt(HH)} Mid:{fmt(box1h['mid'])}\n15M pullback OK + 5M entry OK\n🛡️ SL {fmt(sl)} ({stop_pct:+.2f}%)\n🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} RUNNER {fmt(runner)} RR:{rr:.2f} [{TAG}]"
            cands.append((rr,sym,msg,live,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship))
        except Exception as e:
            skipped[sym]=f"err {e}"; print(f"{sym} err {e}")
    cands.sort(key=lambda x: x[0], reverse=True)
    print(f"FOUND {len(cands)} signals | SKIPPED: {skipped}")
    if len(cands)==0:
        minute = datetime.now(EAT).minute
        if minute < 15:
            tg(f"⏰ SCAN {get_time()} | active:{len(ACTIVE)} | daily:{COOLDOWN.get('daily_pnl',0):.2f}%\nNo entry: {list(skipped.values())[:3]}")
        return
    for it in cands[:3]:
        if len(ACTIVE)>=MAX_ACTIVE: break
        rr,sym,msg,entry,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship=it
        ACTIVE[sym]={"entry":entry,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"cfg_close":cfg["CLOSE"],"HH":HH,"LL":LL,"time":time.time(),"face":ship,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False,"type":get_tp_config(sym)[1]}
        COOLDOWN["signals"][sym]=time.time(); save_a(); save_c(); tg(msg); time.sleep(1)
if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(60)
