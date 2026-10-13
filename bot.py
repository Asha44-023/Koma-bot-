import json, math, os, sys, time, tempfile, requests, io
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","SUI_USDT","PHA_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT","MUBARAK_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 5, 7200
session = requests.Session()
COUNTER_MIN_RR = 0.8
TREND_MIN_RR = 0.6
TAG = "BOT-V146-4H-SR-CHART"
TP_CONFIG = {
    "PUMP": {"TP1": 1.0, "TP2": 2.8, "TP3": 6.0, "RUNNER_TARGET": 20.0, "CLOSE": [40,30,15,15]},
    "TREND": {"TP1": 1.5, "TP2": 4.0, "TP3": 8.5, "RUNNER_TARGET": 15.0, "CLOSE": [30,30,20,20]},
}
PUMP_COINS = ["GRASS_USDT","SENT_USDT","SAND_USDT","SIREN_USDT","KOMA_USDT","LAB_USDT","FARTCOIN_USDT","VELVET_USDT","MUBARAK_USDT"]

def get_tp_config(sym):
    return (TP_CONFIG["PUMP"], "PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"], "TREND")
def calc_tps(sym, live, is_buy):
    cfg, typ = get_tp_config(sym)
    if is_buy:
        tp1 = live*(1+cfg["TP1"]/100); tp2=live*(1+cfg["TP2"]/100); tp3=live*(1+cfg["TP3"]/100); runner=live*(1+cfg["RUNNER_TARGET"]/100)
    else:
        tp1 = live*(1-cfg["TP1"]/100); tp2=live*(1-cfg["TP2"]/100); tp3=live*(1-cfg["TP3"]/100); runner=live*(1-cfg["RUNNER_TARGET"]/100)
    return tp1,tp2,tp3,runner,cfg,typ
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f)
        return v if isinstance(v,type(d)) else d
    except: return d
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
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

def send_chart(sym, d4, sr4h, live, direction, exp_hours):
    try:
        closes = d4["c"][-70:]
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(closes, color='white', linewidth=1.2, label='4H close')
        ax.axhspan(sr4h["SUPPORT_LOW"], sr4h["SUPPORT_HIGH"], color='#00ff88', alpha=0.25)
        ax.axhspan(sr4h["RESIST_LOW"], sr4h["RESIST_HIGH"], color='#ff4444', alpha=0.28)
        ax.axhline(sr4h["support_level"], color='#00ff88', ls='--', alpha=0.7)
        ax.axhline(sr4h["resist_level"], color='#ff4444', ls='--', alpha=0.7)
        ax.axhline(live, color='yellow', ls=':', lw=1.5, label=f'LIVE {fmt(live)}')
        ax.set_title(f'{sym.replace("_USDT","")} 4H — {direction} | GREEN {fmt(sr4h["SUPPORT_LOW"])}-{fmt(sr4h["SUPPORT_HIGH"])} ({sr4h["sup_touches"]}x) | RED {fmt(sr4h["RESIST_LOW"])}-{fmt(sr4h["RESIST_HIGH"])} ({sr4h["res_touches"]}x) | ⏱️ ~{exp_hours}h', fontsize=10)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(alpha=0.15)
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close(fig)
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            session.post(url, data={"chat_id": TELEGRAM_CHAT, "caption": f"{sym.replace('_USDT','')} {direction} — Expected {exp_hours}h to target"}, files={"photo": (f"{sym}.png", buf, "image/png")}, timeout=15)
    except Exception as e:
        print(f"chart err {e}")

def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}
    sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=10).json()
        d=r.get("data",r)
        if isinstance(d,dict) and "data" in d: d=d["data"]
        res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol", d.get("volume", [0]*len(d["close"])))]}
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

def get_4h_sr_boxes(d4, sym=""):
    lookback=70
    lows=d4["l"][-lookback:]; highs=d4["h"][-lookback:]
    is_pump=sym in PUMP_COINS; tol=0.012 if is_pump else 0.008
    def cluster_levels(arr, need=3):
        levels=[]
        for v in arr:
            cnt=sum(1 for x in arr if abs(x-v)/v < tol)
            if cnt>=need: levels.append((v,cnt))
        if not levels: return None,0
        levels.sort(key=lambda x:x[1], reverse=True)
        return levels[0][0], levels[0][1]
    sup,sup_cnt=cluster_levels(lows, need=2 if is_pump else 3)
    res,res_cnt=cluster_levels(highs, need=2 if is_pump else 3)
    if sup is None or res is None: return None
    return {"SUPPORT_LOW":sup*0.992,"SUPPORT_HIGH":sup*1.008,"RESIST_LOW":res*0.992,"RESIST_HIGH":res*1.008,"support_level":sup,"resist_level":res,"sup_touches":sup_cnt,"res_touches":res_cnt}

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
    h=d1h["h"][-20:]; l=d1h["l"][-20:]
    HH=max(h); LL=min(l); rng=HH-LL; mid=(HH+LL)/2
    if rng/mid>0.15: return None
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}
def get_4h_dir(d4):
    o,c=d4["o"][-1],d4["c"][-1]; s10=sum(d4["c"][-10:])/10; s20=sum(d4["c"][-20:])/20
    if c>o and s10>s20*1.001: return "BUY"
    if c<o and s10<s20*0.999: return "SELL"
    return "BUY" if c>o else "SELL"
def check_pullback_15m(d15, box, direction):
    if not d15: return False
    live_c=d15["c"][-1]
    return (box["LL"]+box["rng"]*0.40) <= live_c <= (box["LL"]+box["rng"]*0.60)
def check_entry_5m(d5, direction):
    if not d5 or len(d5["c"])<3: return False
    o,c=d5["o"][-1],d5["c"][-1]; o2,c2=d5["o"][-2],d5["c"][-2]
    if "v" in d5:
        avg=sum(d5["v"][-10:-1])/9 if len(d5["v"])>10 else d5["v"][-1]
        if d5["v"][-1] < avg*0.8: return False
    return (c>o and c>o2 and c>c2) if direction=="BUY" else (c<o and c<o2 and c<c2)
def next_liquidity(d1,HH,LL,direction):
    h=d1["h"][-20:]; l=d1["l"][-20:]
    liq_up=[x for x in h if x>HH]; liq_down=[x for x in l if x<LL]
    if direction=="BUY":
        lv=sorted(set(liq_up))
        return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*1.02) if len(lv)==1 else (HH*1.03,HH*1.06)
    else:
        lv=sorted(set(liq_down),reverse=True)
        return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*0.98) if len(lv)==1 else (LL*0.97,LL*0.94)
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
            tg(f"💚 TP1 {sym.replace('_USDT','')} @ {fmt(p)} (-{cfg_close[0]}% closed) -> SL BE")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚 TP2 {sym.replace('_USDT','')} +{pnl_now:.2f}%")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a()
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚💚 TP3 {sym.replace('_USDT','')} +{pnl_now:.2f}% -> RUNNER to {fmt(runner_target)}")
            continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"🚀 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)}")
            ACTIVE.pop(sym,None); save_a()

    print(f"--- SCAN {TAG} {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: return
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.15); d4=kl(sym,"Hour4"); time.sleep(0.15); h1=kl(sym,"Min60"); time.sleep(0.15); m15=kl(sym,"Min15"); time.sleep(0.15); m5=kl(sym,"Min5"); time.sleep(0.15)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            sr4h=get_4h_sr_boxes(d4,sym)
            if not sr4h: skipped[sym]="no_4h_SR_3touches"; continue
            dir4h=get_4h_dir(d4); box1h=get_1h_box(h1)
            if not box1h: skipped[sym]="no_1H_box"; continue
            live=get_live_price(sym) or h1["c"][-1]
            atr4=atr_from_kl(d4,14); atr1=atr_from_kl(h1,14)
            in_resist= sr4h["RESIST_LOW"] <= live <= sr4h["RESIST_HIGH"]*1.015
            in_support= sr4h["SUPPORT_LOW"]*0.985 <= live <= sr4h["SUPPORT_HIGH"]
            direction=None; target_box=""; exp_hours=16
            if in_resist:
                direction="SELL"; dist=abs(live-sr4h["support_level"]); exp_candles=max(2,min(12,dist/(atr4 or dist*0.2))); exp_hours=int(exp_candles*4); target_box=f'GREEN {fmt(sr4h["SUPPORT_LOW"])}-{fmt(sr4h["SUPPORT_HIGH"])}'
            elif in_support:
                direction="BUY"; dist=abs(sr4h["resist_level"]-live); exp_candles=max(2,min(12,dist/(atr4 or dist*0.2))); exp_hours=int(exp_candles*4); target_box=f'RED {fmt(sr4h["RESIST_LOW"])}-{fmt(sr4h["RESIST_HIGH"])}'
            else:
                buf=0.6*atr1; close1h=h1["c"][-1]
                if close1h>box1h["HH"]+buf*0.6 and live>box1h["HH"]*1.002: direction="BUY"
                elif close1h<box1h["LL"]-buf*0.6 and live<box1h["LL"]*0.998: direction="SELL"
            if not direction: skipped[sym]=f"mid_wait S:{fmt(sr4h['support_level'])} R:{fmt(sr4h['resist_level'])} L:{fmt(live)}"; continue
            if not check_pullback_15m(m15,box1h,direction): skipped[sym]="no_pullback"; continue
            if not check_entry_5m(m5,direction): skipped[sym]="no_engulf"; continue
            ship,_,_,_=daily_ship(d1); is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            liq1,liq2=next_liquidity(d1,HH,LL,direction)
            tp1_raw,tp2_raw,tp3_raw,runner_raw,cfg,typ=calc_tps(sym,live,is_buy)
            if is_buy:
                tp1=max(tp1_raw,liq1 if liq1>live else tp1_raw); tp2=max(tp2_raw,liq2 if liq2>live else tp2_raw); tp3=max(tp3_raw,tp2*1.02); runner=max(runner_raw,tp3*1.12)
                sl=min(LL*0.998,live*0.993,box1h["mid"]*0.999,sr4h["SUPPORT_LOW"]*0.985)
            else:
                tp1=min(tp1_raw,liq1 if liq1<live else tp1_raw); tp2=min(tp2_raw,liq2 if liq2<live else tp2_raw); tp3=min(tp3_raw,tp2*0.98); runner=min(runner_raw,tp3*0.88)
                sl=max(HH*1.002,live*1.007,box1h["mid"]*1.001,sr4h["RESIST_HIGH"]*1.015)
            if is_buy:
                if not (sl<live<tp1<tp2<tp3): skipped[sym]="bad_levels"; continue
                rr=(tp2-live)/(live-sl) if live!=sl else 0
            else:
                if not (tp3<tp2<tp1<live<sl): skipped[sym]="bad_levels"; continue
                rr=(live-tp2)/(sl-live) if sl!=live else 0
            is_counter=(direction!=dir4h)
            if is_counter and rr<COUNTER_MIN_RR: skipped[sym]=f"counter_rr_low {rr:.2f}"; continue
            if not is_counter and rr<TREND_MIN_RR: skipped[sym]=f"trend_rr_low {rr:.2f}"; continue
            if time.time()-COOLDOWN["signals"].get(sym,0)<SYMBOL_COOLDOWN_SECONDS: skipped[sym]="cooldown"; continue
            tag="🔄 COUNTER BUY" if is_buy and is_counter else "🔄 COUNTER SELL" if not is_buy and is_counter else "💚 BUY" if is_buy else "❤️ SELL"
            stop_pct=(sl/live-1)*100
            msg=(f"{tag} {sym.replace('_USDT','')} @ {fmt(live)} [{typ} {cfg['TP1']}/{cfg['TP2']}/{cfg['TP3']}%]\n"
                 f"4H MAP: GREEN {fmt(sr4h['SUPPORT_LOW'])}-{fmt(sr4h['SUPPORT_HIGH'])} ({sr4h['sup_touches']}x) | RED {fmt(sr4h['RESIST_LOW'])}-{fmt(sr4h['RESIST_HIGH'])} ({sr4h['res_touches']}x)\n"
                 f"Pos: {'IN RED → SHORT to GREEN' if in_resist else 'IN GREEN → LONG to RED' if in_support else 'BREAKOUT'} | Target {target_box} | ⏱️ ~{exp_hours}h\n"
                 f"1H:{fmt(LL)}-{fmt(HH)} 4H Dir:{dir4h}\n"
                 f"🛡️ SL {fmt(sl)} ({stop_pct:+.2f}%)\n"
                 f"🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} RUNNER {fmt(runner)} RR:{rr:.2f} [{TAG}]")
            cands.append((rr,sym,msg,live,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,d4,exp_hours,direction))
        except Exception as e:
            skipped[sym]=f"err {e}"; print(f"{sym} err {e}")
    cands.sort(key=lambda x:x[0], reverse=True)
    print(f"FOUND {len(cands)} | SKIPPED: {skipped}")
    if not cands: return
    for it in cands[:3]:
        if len(ACTIVE)>=MAX_ACTIVE: break
        rr,sym,msg,entry,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,d4,exp_hours,direction=it
        ACTIVE[sym]={"entry":entry,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"cfg_close":cfg["CLOSE"],"HH":HH,"LL":LL,"time":time.time(),"face":ship,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False,"type":get_tp_config(sym)[1]}
        COOLDOWN["signals"][sym]=time.time(); save_a(); save_c()
        tg(msg)
        send_chart(sym,d4,sr4h,entry,direction,exp_hours)
        time.sleep(1.5)

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(300)
