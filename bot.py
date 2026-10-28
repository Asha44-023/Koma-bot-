import json, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"); TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE="active.json","cooldown.json","stats_v199.json"
MAX_ACTIVE=6; TOP_N_PER_SCAN=2
session=requests.Session(); TAG="V199.1-5COINS-30M-SWEEP+BREAKOUT"

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

def get_daily_levels(d1):
    y_high=float(d1["h"][-2]); y_low=float(d1["l"][-2]); y_mid=(y_high+y_low)/2.0; y_range=y_high-y_low
    return y_high,y_low,y_mid,y_range

def detect_1D_signal(d1, d15, live):
    try:
        if not d1 or len(d1["c"])<3: return False,"","","",0,0,0
        y_high,y_low,y_mid,y_range=get_daily_levels(d1)
        if y_range==0: return False,"","","",0,0,0
        h15=d15["h"]; l15=d15["l"]; c15=d15["c"]; o15=d15["o"]
        if len(c15)<6: return False,"","","",y_high,y_low,y_mid
        last_h=max(h15[-5:]); last_l=min(l15[-5:]); last_c=c15[-1]
        body=abs(o15[-1]-c15[-1]) or 0.000001
        upper_wick=h15[-1]-max(o15[-1],c15[-1])
        lower_wick=min(o15[-1],c15[-1])-l15[-1]
        if last_h > y_high and last_c < y_high and upper_wick > body*0.5:
            return True, "SELL", "SWEEP_FAKE", f"FAKE HIGH Sweep {fmt(last_h)} > Yest H {fmt(y_high)} close {fmt(last_c)} back below", y_high, y_low, y_mid
        if last_l < y_low and last_c > y_low and lower_wick > body*0.5:
            return True, "BUY", "SWEEP_FAKE", f"FAKE LOW Sweep {fmt(last_l)} < Yest L {fmt(y_low)} close {fmt(last_c)} back above", y_high, y_low, y_mid
        two_closes_above = c15[-1] > y_high and c15[-2] > y_high
        two_closes_below = c15[-1] < y_low and c15[-2] < y_low
        if two_closes_above and live >= y_high*0.998 and live <= y_high*1.015:
            return True, "BUY", "BREAKOUT_RETEST", f"REAL BREAKOUT UP Holds above {fmt(y_high)} retest {fmt(live)} as support - NEVER CAME BACK", y_high, y_low, y_mid
        if two_closes_below and live <= y_low*1.002 and live >= y_low*0.985:
            return True, "SELL", "BREAKOUT_RETEST", f"REAL BREAKOUT DOWN Holds below {fmt(y_low)} retest {fmt(live)} as resistance - NEVER CAME BACK", y_high, y_low, y_mid
        return False, "", "", "", y_high, y_low, y_mid
    except Exception as e:
        return False, "", f"ERR {e}", "",0,0,0

def get_btc_trend():
    try:
        d=kl("BTC_USDT","Hour4")
        if not d: return "RANGE"
        c=d["c"]
        if c[-1]>c[-20]*1.015: return "UP"
        if c[-1]<c[-20]*0.985: return "DOWN"
        return "RANGE"
    except: return "RANGE"

def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    btc_trend=get_btc_trend()
    print(f"--- SCAN {TAG} {get_time()} BTC:{btc_trend} 5COINS ---")
    for sym,data in list(ACTIVE.items()):
        p=get_live(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]); tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; STATS["losses"]+=1; save_s()
            tg(f"❌ {sym.replace('_USDT','USDT')} {pnl:.1f}% SL {TAG}"); ACTIVE.pop(sym,None); save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)): data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP1 25% BE {data.get('type','')}")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)): data["tp2_hit"]=True; data["sl"]=tp1; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP2 50% {data.get('type','')}")
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)): 
            data["tp3_hit"]=True; STATS["wins"]+=1; save_s()
            tg(f"✅ {sym.replace('_USDT','USDT')} TP3 WIN {data.get('type','')} W{STATS['wins']} L{STATS['losses']}"); save_a(); continue
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: continue
            d1=kl(sym,"Day1"); time.sleep(0.3)
            d15=kl(sym,"Min15"); time.sleep(0.3)
            if not d1 or not d15: continue
            live=get_live(sym)
            if not live: continue
            ok, direction, sig_type, reason, y_h, y_l, y_mid = detect_1D_signal(d1, d15, live)
            if not ok:
                print(f"WAIT {sym} {reason[:70] if reason else 'no setup'}")
                continue
            is_buy=direction=="BUY"
            y_range=y_h-y_l
            if sig_type=="SWEEP_FAKE":
                if is_buy:
                    sl=min(d15["l"][-3:])*0.998
                    tp1=live + y_range*0.25; tp2=y_mid; tp3=y_h; runner=y_h + y_range*0.3
                else:
                    sl=max(d15["h"][-3:])*1.002
                    tp1=live - y_range*0.25; tp2=y_mid; tp3=y_l; runner=y_l - y_range*0.3
            else:
                if is_buy:
                    sl=y_h*0.996
                    tp1=y_h + y_range*0.25; tp2=y_h + y_range*0.5; tp3=y_h + y_range*1.0; runner=y_h + y_range*1.8
                else:
                    sl=y_l*1.004
                    tp1=y_l - y_range*0.25; tp2=y_l - y_range*0.5; tp3=y_l - y_range*1.0; runner=y_l - y_range*1.8
            risk=abs(live-sl)/live*100; reward=abs(tp1-live)/live*100; rr=reward/risk if risk>0 else 0
            if rr<1.5: continue
            if not (0.0008 < risk < 0.02): continue
            print(f"READY {sym} {direction} {sig_type} RR{rr:.1f} - {reason}")
            cands.append((95 if sig_type=="BREAKOUT_RETEST" else 90,sym,direction,sig_type,live,sl,tp1,tp2,tp3,runner,rr,y_h,y_l,y_mid,reason))
        except Exception as e:
            print(f"EX {sym} {e}"); continue
    cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,dir,sig_type,live,sl,tp1,tp2,tp3,runner,rr,y_h,y_l,y_mid,reason in cands:
        is_buy=dir=="BUY"
        ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":TAG,"type":sig_type,"score":score,"rr":rr,"ts":time.time()}; save_a()
        emoji="🟢" if is_buy else "🔴"; side="BUY" if is_buy else "SELL"
        tg(f"{emoji} {side} {sym.replace('_USDT','USDT')} | {TAG}\nType: {sig_type}\n{reason}\nYest H {fmt(y_h)} L {fmt(y_l)} 50% {fmt(y_mid)} BTC:{btc_trend}\nEntry {fmt(live)} SL {fmt(sl)}\nTP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}\nRR {rr:.1f} W{STATS['wins']} L{STATS['losses']}")

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"EX {e}")
            time.sleep(900)
