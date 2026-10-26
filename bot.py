import json, math, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
import numpy as np
EAT = pytz.timezone("Africa/Nairobi")
try:
    from colorama import init, Fore, Style
    init(autoreset=True); GREEN=Fore.GREEN+Style.BRIGHT; RED=Fore.RED+Style.BRIGHT; YELLOW=Fore.YELLOW+Style.BRIGHT; BLUE=Fore.CYAN+Style.BRIGHT; MAGENTA=Fore.MAGENTA+Style.BRIGHT; RESET=Style.RESET_ALL
except: GREEN=RED=YELLOW=BLUE=MAGENTA=RESET=""

SYMBOLS=["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"); TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE="active.json","cooldown.json","stats_v157.json"
DAILY_LOSS_LIMIT,MAX_ACTIVE=-8.0,35; TOP_N_PER_SCAN=3; ATR_PERIOD=14; ATR_MULT=1.5; RR_MIN=0.7

try:
    with open("seasonality.json","r") as f: _sj=json.load(f); _sum=_sj.get("summary",{})
    def _wr(q): 
        try: return float(_sum.get(q,"").split("WR")[1].split("%")[0])
        except: return 60.0
    Q_WR={q:_wr(q) for q in ["Q1","Q2","Q3","Q4"]}
except: Q_WR={"Q1":52,"Q2":63,"Q3":38,"Q4":71}

def get_seasonality():
    m=datetime.now(EAT).month; q="Q4" if m>=10 else "Q3" if m>=7 else "Q2" if m>=4 else "Q1"; wr=Q_WR.get(q,60)
    if wr<45: return q,wr,0.4,75
    if wr<55: return q,wr,0.8,68
    if wr<65: return q,wr,1.2,62
    return q,wr,2.0,55

session=requests.Session(); TAG="V180-BOTH-ADAPTIVE-ATR-FINAL"
TP_CONFIG={"PUMP":{"CLOSE":[40,30,15,15]},"TREND":{"CLOSE":[30,30,20,20]}}; PUMP_COINS=["KOMA_USDT","GRASS_USDT","SAND_USDT","FARTCOIN_USDT","PEPE_USDT","BONK_USDT","WIF_USDT"]
def get_tp_config(sym): return (TP_CONFIG["PUMP"],"PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"],"TREND")
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f); return v if isinstance(v,type(d)) else d
    except: return d
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)) or "."; fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno()); os.replace(tp,path)
    except: 
        try: os.unlink(tp)
        except: pass; raise

ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{}); STATS=load_json(STATS_FILE,{"closed":[],"open":{}})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def save_s(): atomic_save(STATS_FILE,STATS)
def fmt(p):
    try:
        if p is None: return "0"; p=float(p)
        if not math.isfinite(p): return "0"
        if p<0.01: return f"{p:.8f}"
        if p<1: return f"{p:.6f}"
        return f"{p:.4f}"
    except: return "0"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try: r=session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15); print(f"TG {r.status_code}")
    except Exception as e: print(f"TG EX {e}")

def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}; sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    for attempt in range(3):
        try:
            r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
            if r.status_code==429: time.sleep(5+attempt*3); continue
            j=r.json(); d=j.get("data",j)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            if not d or "open" not in d: time.sleep(1); continue
            res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",d.get("volume",[0]*len(d["close"])))]}
            for k in res: res[k]=res[k][:-1]
            if len(res["c"])<30: time.sleep(0.5); continue
            return res
        except: time.sleep(2+attempt*2)
    return None

def get_live_price(s):
    for t in [s,s.replace("_",""),s.replace("_USDT","USDT")]:
        try:
            r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json()
            data=r.get("data",r); lp=data.get("lastPrice") or data.get("last_price") or data.get("price")
            if lp:
                v=float(lp)
                if v>0 and math.isfinite(v): return v
        except: pass
    return None

def calc_atr_percent(d,live_price):
    try:
        h=d["h"]; l=d["l"]; c=d["c"]
        if len(c)<ATR_PERIOD+5: return 0.05,0
        trs=[]
        for i in range(1,len(c)): trs.append(max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])))
        atr=float(np.mean(trs[-ATR_PERIOD:])); return atr/live_price if live_price>0 else 0.05,atr
    except: return 0.05,0

def get_adaptive_thresholds(atr_pct): return float(np.clip(atr_pct*ATR_MULT,0.01,0.20)),float(np.clip(atr_pct*ATR_MULT*0.5,0.008,0.10))

def get_last_structure(d,lookback=80):
    if not d or len(d["c"])<lookback: return None
    h=d["h"][-lookback:]; l=d["l"][-lookback:]; c=d["c"][-lookback:]
    swings_h=[]; swings_l=[]
    for i in range(5,len(h)-5):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: swings_h.append((i,h[i]))
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: swings_l.append((i,l[i]))
    if len(swings_h)<2 or len(swings_l)<2: return None
    last_h,prev_h=swings_h[-1][1],swings_h[-2][1]; last_l,prev_l=swings_l[-1][1],swings_l[-2][1]
    hh_type="HH" if last_h>prev_h else "LH"; ll_type="HL" if last_l>prev_l else "LL"
    trend="UP" if hh_type=="HH" and ll_type=="HL" else "DOWN" if hh_type=="LH" and ll_type=="LL" else "RANGE"
    broke_hh=broke_ll=False; bh=bl=wb=wbe=0
    for i in range(len(c)-15,len(c)):
        rng=h[i]-l[i]
        if rng==0: continue
        cp=(c[i]-l[i])/rng*100
        if c[i]>last_h:
            if cp>=62: broke_hh=True; bh=max(bh,cp)
            else: wb=max(wb,cp)
        if c[i]<last_l:
            if cp<=38: broke_ll=True; bl=cp if bl==0 else min(bl,cp)
            else: wbe=max(wbe,cp) if wbe!=0 else cp
    return {"last_high":last_h,"prev_high":prev_h,"last_low":last_l,"prev_low":prev_l,"hh_type":hh_type,"ll_type":ll_type,"trend":trend,"broke_hh":broke_hh,"broke_ll":broke_ll,"broke_hh_strength":bh,"broke_ll_strength":bl,"weak_bull":wb,"weak_bear":wbe,"last_close":c[-1]}

def get_3m_trend(d1):
    if not d1 or len(d1["c"])<90: return {"trend_3m":"RANGE","pct_3m":0}
    try: return {"trend_3m":"UP" if (d1["c"][-1]-d1["c"][-90])/d1["c"][-90]*100>=5 else "DOWN" if (d1["c"][-1]-d1["c"][-90])/d1["c"][-90]*100<=-5 else "RANGE","pct_3m":(d1["c"][-1]-d1["c"][-90])/d1["c"][-90]*100}
    except: return {"trend_3m":"RANGE","pct_3m":0}

def get_btc_filter():
    try:
        btc_d1=kl("BTC_USDT","Day1"); btc_h1=kl("BTC_USDT","Min60"); t3m=get_3m_trend(btc_d1)
        if not btc_d1 or t3m["pct_3m"]==0: return {"trend":"UP","pct_3m":24.0}
        if not btc_h1: return {"trend":t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else "UP","pct_3m":t3m["pct_3m"]}
        struct=get_last_structure(btc_h1,80)
        if not struct: return {"trend":t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else "UP","pct_3m":t3m["pct_3m"]}
        trend=t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else struct["trend"]
        if trend=="RANGE": trend="UP"
        return {"trend":trend,"pct_3m":t3m["pct_3m"]}
    except: return {"trend":"UP","pct_3m":24.0}

def get_4h_sr_boxes(d4):
    h=d4["h"]; l=d4["l"]; lookback=50
    lows=[l[i] for i in range(len(l)-lookback,len(l)-2) if l[i]<l[i-1] and l[i]<l[i+1]]; highs=[h[i] for i in range(len(h)-lookback,len(h)-2) if h[i]>h[i-1] and h[i]>h[i+1]]
    if not lows or not highs: return {"gap_pct":15}
    sup=min(lows); res=max(highs); return {"gap_pct":(res-sup)/sup*100 if sup>0 else 0}

def get_1h_box(d1h,trend_3m="RANGE",pct_3m=0):
    look=10 if (trend_3m=="UP" and pct_3m>=20) else 20; h=d1h["h"][-look:]; l=d1h["l"][-look:]; HH=max(h); LL=min(l); mid=(HH+LL)/2
    if mid==0 or (HH-LL)/mid>1.5: return None
    return {"HH":HH,"LL":LL,"look":look}

def check_entry_5m(d5,direction,relaxed=False):
    if not d5 or len(d5["c"])<3: return False
    o,c=d5["o"][-1],d5["c"][-1]
    if relaxed: return (c>=o*0.998) if direction=="BUY" else (c<=o*1.002)
    return (c>d5["o"][-1] and c>=d5["o"][-2]) if direction=="BUY" else (c<d5["o"][-1] and c<=d5["o"][-2])

def valid_signal_data(d):
    try:
        for k in ("entry","sl","tp1","tp2","tp3"):
            if not math.isfinite(float(d[k])): return False
        return True
    except: return False

def get_next_liquidity_auto(d4,live,is_buy,depth=0):
    try:
        default_levels=[0.015,0.028,0.045,0.10]; level_p=default_levels[depth] if depth<len(default_levels) else 0.10+(depth-3)*0.06
        if not d4 or len(d4["h"])<50: return (live*(1+level_p) if is_buy else live*(1-level_p)),0,True
        h=d4["h"][-100:]; l=d4["l"][-100:]; swings_h=[]; swings_l=[]
        for i in range(10,len(h)-10):
            if h[i]==max(h[i-4:i+5]): swings_h.append(h[i])
            if l[i]==min(l[i-4:i+5]): swings_l.append(l[i])
        if is_buy:
            candidates=[x for x in set(swings_h) if x>live*1.003]; cc=[]
            for lvl in candidates:
                cnt=sum(1 for x in swings_h if abs(x-lvl)/lvl<0.003)
                if cnt>=2 and 0.5<=(lvl-live)/live*100<=4.0: cc.append((lvl,cnt))
            cc=sorted(list(set(cc)),key=lambda x:x[0])
            if not cc: return live*(1+level_p),0,True
            if depth<len(cc): return cc[depth][0],cc[depth][1],False
            return cc[-1][0]*(1+0.006*(depth-len(cc)+1)),cc[-1][1],False
        else:
            candidates=[x for x in set(swings_l) if x<live*0.997]; cc=[]
            for lvl in candidates:
                cnt=sum(1 for x in swings_l if abs(x-lvl)/lvl<0.003)
                if cnt>=2 and 0.5<=(live-lvl)/live*100<=4.0: cc.append((lvl,cnt))
            cc=sorted(list(set(cc)),key=lambda x:x[0],reverse=True)
            if not cc: return live*(1-level_p),0,True
            if depth<len(cc): return cc[depth][0],cc[depth][1],False
            return cc[-1][0]*(1-0.006*(depth-len(cc)+1)),cc[-1][1],False
    except: fp=0.015 if depth==0 else 0.028 if depth==1 else 0.045 if depth==2 else 0.10; return (live*(1+fp) if is_buy else live*(1-fp)),0,True

def get_elite_score(sym,label,btc_trend,direction,coin_trend,broke_strength,mtf_align=False):
    s=50
    if label=="HL": s+=25
    elif label=="LH": s+=25
    elif label=="HH" and broke_strength>=62: s+=22
    elif label=="LL" and broke_strength<=38: s+=22
    else: s-=20
    if coin_trend==direction: s+=15
    if mtf_align: s+=10
    if sym in ["FARTCOIN_USDT","WIF_USDT","PEPE_USDT","BONK_USDT","KOMA_USDT","SEI_USDT"]: s+=5
    return s

def scan():
    q,wr_q,_,min_score_threshold=get_seasonality(); today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    btc_info=get_btc_filter(); btc_trend=btc_info["trend"]
    print(f"--- SCAN {TAG} {get_time()} BTC:{btc_trend} 3M:{btc_info.get('pct_3m',0):.1f}% Q:{q} WR:{wr_q:.0f}% BOTH+COLOR ---")
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]); tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"]); runner_target=float(data.get("runner",tp3*1.15 if is_buy else tp3*0.85)); label=data.get("label","?")
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c(); STATS["closed"].append({"sym":sym,"result":"LOSS","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            print(f"{RED}STOP {sym} {pnl:.2f}%{RESET}"); tg(f"STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)} [{label}] BTC:{btc_trend}"); ACTIVE.pop(sym,None); save_a(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)): data["tp1_hit"]=True; data["sl"]=entry; changed=True; print(f"{GREEN}TP1 {sym} -> BE{RESET}"); tg(f"🟢 TP1 {sym.replace('_USDT','')} @ {fmt(p)} -> BE [{label}]")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)): data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True; print(f"{GREEN}TP2 {sym}{RESET}"); tg(f"🟢 TP2 {sym.replace('_USDT','')} @ {fmt(p)} [{label}]")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)): data["tp3_hit"]=True; data["sl"]=tp2; save_a(); print(f"{GREEN}TP3 SWEEP {sym} -> RUNNER{RESET}"); tg(f"🟢 TP3 SWEEP {sym.replace('_USDT','')} -> RUNNER {fmt(runner_target)} [{label}]"); continue
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.8); d4=kl(sym,"Hour4"); time.sleep(0.8); h1=kl(sym,"Min60"); time.sleep(0.8); m15=kl(sym,"Min15"); time.sleep(0.8); m5=kl(sym,"Min5"); time.sleep(1.0)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            coin_3m=get_3m_trend(d1); trend_3m=coin_3m["trend_3m"]; pct_3m=coin_3m["pct_3m"]
            struct=get_last_structure(h1,80)
            if not struct: skipped[sym]="no_structure"; continue
            live_raw=get_live_price(sym); live=live_raw if live_raw and live_raw>0 else h1["c"][-1]
            if not live or not math.isfinite(live): skipped[sym]="live_none"; continue
            atr_pct,_=calc_atr_percent(h1,live); NEAR_THRESHOLD,RETEST_THRESHOLD=get_adaptive_thresholds(atr_pct)
            box1h=get_1h_box(h1,trend_3m,pct_3m)
            if not box1h: skipped[sym]="no_1H_box"; continue
            if struct.get("weak_bull",0)>0 and not struct["broke_hh"]: skipped[sym]=f"FBS_WEAK_BULL {struct['weak_bull']:.0f}% SKIP"; continue
            if struct.get("weak_bear",0)>0 and not struct["broke_ll"]: skipped[sym]=f"FBS_WEAK_BEAR {struct['weak_bear']:.0f}% SKIP"; continue
            direction=label=None; broke_str=0; is_pred=False
            if struct["ll_type"]=="HL":
                dist=abs(live-struct["last_low"])/struct["last_low"]
                if dist<=NEAR_THRESHOLD: direction="BUY"; label="HL"; broke_str=70; is_pred=True
            if not direction and struct["hh_type"]=="LH":
                dist=abs(live-struct["last_high"])/struct["last_high"]
                if dist<=NEAR_THRESHOLD: direction="SELL"; label="LH"; broke_str=30; is_pred=True
            if not direction and struct["broke_hh"] and struct["broke_hh_strength"]>=62:
                dist=abs(live-struct["last_high"])/struct["last_high"]
                if dist<=RETEST_THRESHOLD: direction="BUY"; label="HH"; broke_str=struct["broke_hh_strength"]; is_pred=False
            if not direction and struct["broke_ll"] and (struct["broke_ll_strength"]<=38 or struct["broke_ll_strength"]==0):
                ll_s=struct["broke_ll_strength"] if struct["broke_ll_strength"]!=0 else 25
                if ll_s<=38:
                    dist=abs(live-struct["last_low"])/struct["last_low"]
                    if dist<=RETEST_THRESHOLD: direction="SELL"; label="LL"; broke_str=ll_s; is_pred=False
            if not direction: skipped[sym]=f"no_break {struct['hh_type']}/{struct['ll_type']} NEAR={NEAR_THRESHOLD*100:.1f}% ATR={atr_pct*100:.1f}%"; continue
            mtf_align=(trend_3m=="UP" and direction=="BUY") or (trend_3m=="DOWN" and direction=="SELL")
            if get_4h_sr_boxes(d4).get("gap_pct",0)<3: skipped[sym]="gap_small"; continue
            if not check_entry_5m(m5,direction,relaxed=is_pred): skipped[sym]=f"no_5m_{'relaxed' if is_pred else 'engulf'}"; continue
            is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            sl=min(LL*0.996,live*(1-atr_pct*1.2)) if is_buy else max(HH*1.004,live*(1+atr_pct*1.2))
            sl=max(sl,live*0.80) if is_buy else min(sl,live*1.20)
            tp1,_,_=get_next_liquidity_auto(d4,live,is_buy,0); tp2,_,_=get_next_liquidity_auto(d4,live,is_buy,1); tp3,_,_=get_next_liquidity_auto(d4,live,is_buy,2); runner,_,_=get_next_liquidity_auto(d4,live,is_buy,3)
            risk=(live-sl)/live*100 if is_buy else (sl-live)/live*100; reward1=(tp1-live)/live*100 if is_buy else (live-tp1)/live*100; rr=reward1/risk if risk!=0 else 0
            if rr<RR_MIN: skipped[sym]=f"rr_{rr:.2f} ATR_{atr_pct*100:.1f}%"; continue
            score=get_elite_score(sym,label,btc_trend,direction,struct["trend"],broke_str,mtf_align)
            if score<min_score_threshold: skipped[sym]=f"score_{score}"; continue
            cands.append((score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,f"ATR{atr_pct*100:.1f}%",broke_str,rr,coin_3m,box1h["look"],NEAR_THRESHOLD,is_pred,mtf_align))
        except Exception as e: import traceback; print(f"CRASH {sym}: {e}"); skipped[sym]=f"ex_{e}"; continue
    cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,pull_label,broke_str,rr,coin_3m,look,near_th,is_pred,mtf_align in cands:
        is_buy=direction=="BUY"; tp_cfg,tp_type=get_tp_config(sym); ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":label,"score":score,"pct":pull_label,"rr":rr,"ts":time.time(),"tp_cfg":tp_cfg,"tp_type":tp_type}; save_a(); STATS["open"][sym]={"label":label,"entry":live,"ts":time.time()}; save_s()
        if is_pred: col=BLUE; type_str="PRED-DIP" if direction=="BUY" else "PRED-RALLY"; emoji="🔵"
        else: col=GREEN if is_buy else RED; type_str="BREAKOUT"; emoji="🟢" if is_buy else "🔴"
        mtf_str="✅ALIGN" if mtf_align else "⚠️COUNTER"; mtf_col=GREEN if mtf_align else YELLOW
        print(f"{col}{emoji} NEW {sym} {direction} [{label} {broke_str:.0f}% {type_str}] {mtf_col}{mtf_str}{col} @ {fmt(live)} SL {fmt(sl)} NEAR {near_th*100:.1f}% {pull_label} SCORE {score} RR {rr:.2f} 3M {coin_3m['pct_3m']:.0f}%{RESET}")
        tg(f"{emoji} {type_str} {sym.replace('_USDT','')} {direction} [{label} {broke_str:.0f}%] @ {fmt(live)} SL {fmt(sl)}\nTP {fmt(tp1)}/{fmt(tp2)}/{fmt(tp3)} RUNNER {fmt(runner)}\n{mtf_str} 3M:{coin_3m['trend_3m']} {coin_3m['pct_3m']:.0f}% NEAR {near_th*100:.1f}% {pull_label} SCORE {score} RR {rr:.2f} Q:{q} WR:{wr_q:.0f}% BTC:{btc_trend}")
    if not cands:
        print(f"{YELLOW}No cands, skips:{RESET}")
        for k,v in list(skipped.items())[:15]:
            c=YELLOW if "no_break" in v else BLUE if "MTF" in v else RED if "score" in v or "rr_" in v else MAGENTA if "5m" in v else RESET
            print(f"  {c}{k}: {v}{RESET}")

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"{RED}SCAN EX {e}{RESET}"); import traceback; traceback.print_exc()
            time.sleep(900)
