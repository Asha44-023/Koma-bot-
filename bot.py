import json, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
import numpy as np
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"); TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE="active.json","cooldown.json","stats_v192.json"
MAX_ACTIVE=35; TOP_N_PER_SCAN=4; RR_MIN=1.2
session=requests.Session(); TAG="V192-BUY-ONLY-FILTERED"

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
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{}); STATS=load_json(STATS_FILE,{"closed":[],"open":{},"wins":0,"losses":0})
COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def save_s(): atomic_save(STATS_FILE,STATS)
def fmt(p):
    try:
        p=float(p)
        if p<0.01: return f"{p:.8f}"
        if p<1: return f"{p:.6f}"
        return f"{p:.4f}"
    except: return "0"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try: session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15)
    except: pass
def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}; sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*500
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    for _ in range(3):
        try:
            r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
            j=r.json(); d=j.get("data",j)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            if not d or "open" not in d: continue
            res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",d.get("volume",[0]*len(d["close"])))]}
            for k in res: res[k]=res[k][:-1]
            if len(res["c"])<50: continue
            return res
        except: time.sleep(1)
    return None
def get_live(s):
    for t in [s,s.replace("_",""),s.replace("_USDT","USDT")]:
        try:
            r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json()
            data=r.get("data",r); lp=data.get("lastPrice") or data.get("last_price") or data.get("price")
            if lp and float(lp)>0: return float(lp)
        except: pass
    return None
def calc_atr(d):
    try:
        h=d["h"]; l=d["l"]; c=d["c"]
        trs=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
        return float(np.mean(trs[-14:]))
    except: return 0
def fbs_check(d, direction):
    try:
        o=d["o"]; h=d["h"]; l=d["l"]; c=d["c"]
        po=o[-2]; ph=h[-2]; pl=l[-2]; pc=c[-2]; cc=c[-1]
        rng=ph-pl
        if rng<=0: return False,0
        pct=(cc-pl)/rng*100
        if direction=="BUY":
            if not (pc>po): return False,pct
            if cc < pl+rng*0.62: return False,pct
            return True,pct
        else:
            if not (pc<po): return False,pct
            if cc > pl+rng*0.42: return False,pct
            return True,pct
    except: return False,0
def get_swings(d, lookback=60):
    h=d["h"][-lookback:]; l=d["l"][-lookback:]; c=d["c"][-lookback:]
    sh=[]; sl=[]
    for i in range(5,len(h)-5):
        if h[i]>=max(h[i-3:i]) and h[i]>=max(h[i+1:i+4]): sh.append((len(c)-lookback+i, h[i]))
        if l[i]<=min(l[i-3:i]) and l[i]<=min(l[i+1:i+4]): sl.append((len(c)-lookback+i, l[i]))
    return sh,sl,c,h,l
def detect_V(d):
    try:
        c=d["c"]; l=d["l"]; o=d["o"]
        if len(c)<12: return False
        if c[-5] < c[-12] and c[-1] > o[-1] and c[-1] > c[-2]*1.008:
            if c[-3]<o[-3] and c[-2]<o[-2]: return True
    except: pass
    return False
def detect_W(d):
    try:
        c=d["c"]
        if c[-1] < c[-15]*1.02 and c[-1] > min(c[-15:]):
            sh,sl,_,_,_ = get_swings(d,50)
            if len(sl)>=2:
                last=sl[-1][1]; prev=sl[-2][1]
                if abs(last-prev)/prev*100<=5.0 and last>=prev*0.97: return True
    except: pass
    return False
def detect_M(d):
    try:
        c=d["c"]
        if c[-1] > c[-15]*0.98 and c[-1] < max(c[-15:]):
            sh,sl,_,_,_ = get_swings(d,50)
            if len(sh)>=2:
                last=sh[-1][1]; prev=sh[-2][1]
                if abs(last-prev)/prev*100<=5.0 and last<=prev*1.03: return True
    except: pass
    return False
def detect_U(d):
    try:
        l=d["l"][-12:]; c=d["c"][-12:]
        if c[-1] > min(c[-12:])*1.03 and c[-1] > c[-6]:
            if sum(1 for i in range(1,len(l)) if l[i]>=l[i-1]*0.999)>=7: return True
    except: pass
    return False
def detect_CUP_HANDLE(d):
    try:
        c=d["c"]; h=d["h"]; l=d["l"]
        if len(c)<30: return False
        if c[-1] > c[-20]*1.03:
            if sum(1 for i in range(20,30) if l[-i]>=l[-i-1]*0.998)>=5:
                pull = (max(h[-10:])-min(l[-10:]))/max(h[-10:])*100
                if 0.8<=pull<=4.0 and c[-1]>=h[-2]*0.999: return True
    except: pass
    return False
def detect_FLAG(d):
    try:
        c=d["c"][-20:]; h=d["h"][-20:]; l=d["l"][-20:]
        up=(c[-10]-c[-20])/c[-20]*100 if c[-20]>0 else 0
        if up>=3:
            rng=(max(h[-8:])-min(l[-8:]))/max(h[-8:])*100
            if rng<=2.5: return True,"BULL"
        down=(c[-10]-c[-20])/c[-20]*100
        if down<=-3:
            rng=(max(h[-8:])-min(l[-8:]))/min(l[-8:])*100
            if rng<=2.5: return True,"BEAR"
    except: pass
    return False,""
def detect_TRIANGLE(d):
    try:
        h=d["h"][-20:]; l=d["l"][-20:]
        if max(h[-8:])<=max(h[-18:-8])*1.015 and min(l[-8:])>min(l[-18:-8])*1.005: return True,"ASC"
        if min(l[-8:])>=min(l[-18:-8])*0.985 and max(h[-8:])<max(h[-18:-8])*0.995: return True,"DESC"
    except: pass
    return False,""
def detect_SWEEP(d):
    try:
        l=d["l"]; c=d["c"]; h=d["h"]
        if len(l)<25: return False,""
        low=min(l[-20:-3])
        if l[-2]<low*0.998 and c[-1]>low: return True,"LOW"
        high=max(h[-20:-3])
        if h[-2]>high*1.002 and c[-1]<high: return True,"HIGH"
    except: pass
    return False,""
def get_next_liq(d4,live,is_buy,depth):
    try:
        default=[0.015,0.028,0.045,0.10]; lp=default[depth] if depth<len(default) else 0.10+(depth-3)*0.06
        return live*(1+lp) if is_buy else live*(1-lp)
    except: return live*1.015 if is_buy else live*0.985
def get_btc_trend():
    try:
        d=kl("BTC_USDT","Hour4")
        if not d: return "RANGE"
        c=d["c"]
        if c[-1] > c[-20]*1.015: return "UP"
        if c[-1] < c[-20]*0.985: return "DOWN"
        return "RANGE"
    except: return "RANGE"
def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    btc_trend=get_btc_trend()
    print(f"--- SCAN {TAG} {get_time()} BTC:{btc_trend} ---")
    for sym,data in list(ACTIVE.items()):
        p=get_live(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]); tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; STATS["losses"]+=1; save_s()
            tg(f"❌ SELL {sym.replace('_USDT','USDT')} {pnl:.1f}% SL {data.get('label','')}" if not is_buy else f"❌ BUY {sym.replace('_USDT','USDT')} {pnl:.1f}% SL {data.get('label','')}"); ACTIVE.pop(sym,None); save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)): data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"🟢 BUY {sym.replace('_USDT','USDT')} TP1 BE {data.get('label','')}" if is_buy else f"🔴 SELL {sym.replace('_USDT','USDT')} TP1 BE {data.get('label','')}")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)): data["tp2_hit"]=True; data["sl"]=tp1; save_a(); tg(f"🟢 BUY {sym.replace('_USDT','USDT')} TP2 {data.get('label','')}" if is_buy else f"🔴 SELL {sym.replace('_USDT','USDT')} TP2 {data.get('label','')}")
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)): 
            data["tp3_hit"]=True; STATS["wins"]+=1; save_s()
            tg(f"✅ BUY {sym.replace('_USDT','USDT')} TP3 {data.get('label','')} W{STATS['wins']} L{STATS['losses']}" if is_buy else f"✅ SELL {sym.replace('_USDT','USDT')} TP3 {data.get('label','')} W{STATS['wins']} L{STATS['losses']}"); save_a(); continue
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.3); d4=kl(sym,"Hour4"); time.sleep(0.3); h1=kl(sym,"Min60"); time.sleep(0.3); m15=kl(sym,"Min15"); time.sleep(0.3); m5=kl(sym,"Min5"); time.sleep(0.3)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl"; continue
            live=get_live(sym) or h1["c"][-1]
            atr=calc_atr(h1)
            atr_pct=atr/live*100 if live>0 else 0
            if atr_pct<0.25 or atr_pct>5.0: skipped[sym]=f"atr {atr_pct:.1f}"; continue
            fbs_b_ok,fbs_b_pct=fbs_check(h1,"BUY"); fbs_s_ok,fbs_s_pct=fbs_check(h1,"SELL")
            fbs_b15_ok,fbs_b15_pct=fbs_check(m15,"BUY"); fbs_s15_ok,fbs_s15_pct=fbs_check(m15,"SELL")
            c4=d4["c"]; trend="UP" if c4[-1]>c4[-20]*1.02 else "DOWN" if c4[-1]<c4[-20]*0.98 else "RANGE"
            patterns=[]
            sh_d,sl_d,_,_,_=get_swings(d1,50)
            if trend=="UP":
                if len(sh_d)>=2 and len(sl_d)>=2:
                    if sh_d[-1][1]>sh_d[-2][1] and sl_d[-1][1]>sl_d[-2][1]: patterns.append(("HH-HL","BUY",88,fbs_b_pct))
                if len(sl_d)>=2 and sl_d[-1][1]>sl_d[-2][1]: patterns.append(("HL","BUY",72,fbs_b_pct))
                if detect_W(h1): patterns.append(("W","BUY",85,fbs_b_pct))
                if detect_V(h1): patterns.append(("V","BUY",80,fbs_b_pct))
                if detect_U(h1): patterns.append(("U","BUY",70,fbs_b_pct))
                if detect_CUP_HANDLE(h1): patterns.append(("CUP","BUY",90,fbs_b_pct))
                flag_ok,flag_dir=detect_FLAG(h1)
                if flag_ok and flag_dir=="BULL": patterns.append(("FLAG","BUY",75,fbs_b_pct))
                tri_ok,tri_dir=detect_TRIANGLE(h1)
                if tri_ok and tri_dir=="ASC": patterns.append(("TRI","BUY",70,fbs_b_pct))
                sweep_ok,sweep_dir=detect_SWEEP(h1)
                if sweep_ok and sweep_dir=="LOW": patterns.append(("SWEEP","BUY",80,fbs_b_pct))
            if trend=="DOWN" and btc_trend=="DOWN":
                if len(sh_d)>=2 and len(sl_d)>=2:
                    if sh_d[-1][1]<sh_d[-2][1] and sl_d[-1][1]<sl_d[-2][1]: patterns.append(("LL-LH","SELL",88,fbs_s_pct))
                if len(sh_d)>=2 and sh_d[-1][1]<sh_d[-2][1]: patterns.append(("LH","SELL",72,fbs_s_pct))
                if detect_M(h1): patterns.append(("M","SELL",85,fbs_s_pct))
                flag_ok,flag_dir=detect_FLAG(h1)
                if flag_ok and flag_dir=="BEAR": patterns.append(("FLAG","SELL",75,fbs_s_pct))
                tri_ok,tri_dir=detect_TRIANGLE(h1)
                if tri_ok and tri_dir=="DESC": patterns.append(("TRI","SELL",70,fbs_s_pct))
                sweep_ok,sweep_dir=detect_SWEEP(h1)
                if sweep_ok and sweep_dir=="HIGH": patterns.append(("SWEEP","SELL",80,fbs_s_pct))
            if not patterns: skipped[sym]=f"no pat BTC:{btc_trend} 4H:{trend}"; continue
            best=sorted(patterns,key=lambda x:x[2],reverse=True)[0]
            label,dir,score,fbs_pct=best
            if dir=="BUY" and fbs_pct<60: skipped[sym]=f"BUY FBS {fbs_pct:.0f}%<60"; continue
            if dir=="SELL" and fbs_pct>40: skipped[sym]=f"SELL FBS {fbs_pct:.0f}%>40 top"; continue
            if score>=85:
                if dir=="BUY" and not (fbs_b_ok or fbs_b15_ok): skipped[sym]=f"WEAK {label} BUY {fbs_pct:.0f}%<62%"; continue
                if dir=="SELL" and not (fbs_s_ok or fbs_s15_ok): skipped[sym]=f"WEAK {label} SELL {fbs_pct:.0f}%>42%"; continue
            if dir=="BUY" and m15["c"][-1]<m15["o"][-1]*0.999: skipped[sym]="15m down"; continue
            if dir=="SELL" and m15["c"][-1]>m15["o"][-1]*1.001: skipped[sym]="15m up"; continue
            is_buy=dir=="BUY"
            sl_mult=2.0 if label in ("LL-LH","HH-HL","TRI","W") else 1.6
            sl=live-atr*sl_mult if is_buy else live+atr*sl_mult
            tp1=get_next_liq(d4,live,is_buy,0); tp2=get_next_liq(d4,live,is_buy,1); tp3=get_next_liq(d4,live,is_buy,2); runner=get_next_liq(d4,live,is_buy,3)
            risk=abs(live-sl)/live*100; reward=abs(tp1-live)/live*100; rr=reward/risk if risk>0 else 0
            if rr<RR_MIN: skipped[sym]=f"rr {rr:.1f}"; continue
            cands.append((score,sym,dir,label,live,sl,tp1,tp2,tp3,runner,rr,trend,fbs_pct,patterns))
        except Exception as e:
            skipped[sym]=f"ex {e}"; continue
    cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,dir,label,live,sl,tp1,tp2,tp3,runner,rr,trend,fbs_pct,all_pats in cands:
        is_buy=dir=="BUY"
        ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":label,"score":score,"rr":rr,"ts":time.time()}; save_a()
        fbs_disp = int(min(100,max(0,fbs_pct)))
        same_dir_labels = [p[0] for p in all_pats if p[1]==dir]
        all_str = ",".join(same_dir_labels[:4])
        emoji="🟢" if is_buy else "🔴"
        side="BUY" if is_buy else "SELL"
        tg(f"{emoji} {side} {sym.replace('_USDT','USDT')} | {label} | {score}\nEntry {fmt(live)} SL {fmt(sl)}\nTP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} Runner {fmt(runner)}\nRR {rr:.1f} 4H {trend} FBS {fbs_disp}% {all_str} W{STATS['wins']} L{STATS['losses']}")

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"EX {e}")
            time.sleep(900)
