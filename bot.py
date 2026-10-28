import json, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","POPCAT_USDT","PENGU_USDT","WLD_USDT","BOME_USDT","BRETT_USDT","TURBO_USDT","MEME_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"); TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE="active.json","cooldown.json","stats_v192.json"
MAX_ACTIVE=10; TOP_N_PER_SCAN=2
session=requests.Session(); TAG="V198.1-100X-HH-HL-PIN"

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

def detect_4H_MANIPULATION(d4):
    try:
        if len(d4["c"]) < 25: return False, "", 0, 0
        c=d4["c"]; h=d4["h"]; l=d4["l"]; o=d4["o"]
        uptrend = h[-1] > h[-5] and h[-5] > h[-10] and l[-1] > l[-5] and l[-5] > l[-10]
        downtrend = h[-1] < h[-5] and h[-5] < h[-10] and l[-1] < l[-5] and l[-5] < l[-10]
        prev_high=h[-2]; prev_low=l[-2]
        curr_high=h[-1]; curr_low=l[-1]
        curr_open=o[-1]; curr_close=c[-1]
        body=abs(curr_close-curr_open) or 0.00001
        lower_wick=min(curr_open,curr_close)-curr_low
        upper_wick=curr_high-max(curr_open,curr_close)
        if uptrend and curr_low < prev_low and lower_wick > body*2 and curr_close > prev_low:
            return True, "BUY", prev_low, curr_low
        if downtrend and curr_high > prev_high and upper_wick > body*2 and curr_close < prev_high:
            return True, "SELL", prev_high, curr_high
    except: pass
    return False, "", 0, 0

def is_choppy_4H(d4):
    try:
        c=d4["c"][-10:]; h=d4["h"][-10:]; l=d4["l"][-10:]
        avg_range=sum((h[i]-l[i])/c[i] for i in range(10))/10
        if avg_range<0.008: return True
        return False
    except: return False

def get_15m_refined_entry(sym, direction):
    try:
        d15=kl(sym,"Min15")
        if not d15 or len(d15["c"])<20: return None,None,"no 15m"
        c=d15["c"]; h=d15["h"]; l=d15["l"]
        live=c[-1]; last_low=min(l[-10:]); last_high=max(h[-10:])
        avg_range=sum((h[-10+i]-l[-10+i])/c[-10+i] for i in range(10))/10
        is_tight=avg_range<0.006
        if direction=="BUY":
            choch=c[-1]>max(h[-6:-1])
            if is_tight or choch or live>last_low*1.002:
                sl=min(l[-3:])*0.998
                if 0.001<abs(live-sl)/live<0.012:
                    return live,sl,f"HH+Pin 15m tight={is_tight} CHoCH={choch}"
        else:
            choch=c[-1]<min(l[-6:-1])
            if is_tight or choch or live<last_high*0.998:
                sl=max(h[-3:])*1.002
                if 0.001<abs(sl-live)/live<0.012:
                    return live,sl,f"LL+Pin 15m tight={is_tight} CHoCH={choch}"
        return None,None,"no 15m pattern"
    except Exception as e:
        return None,None,f"15m err {e}"

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
        if c[-1]>c[-20]*1.015: return "UP"
        if c[-1]<c[-20]*0.985: return "DOWN"
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
            tg(f"❌ {sym.replace('_USDT','USDT')} {pnl:.1f}% SL {TAG}"); ACTIVE.pop(sym,None); save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)): data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP1 BE")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)): data["tp2_hit"]=True; data["sl"]=tp1; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP2")
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)): 
            data["tp3_hit"]=True; STATS["wins"]+=1; save_s()
            tg(f"✅ {sym.replace('_USDT','USDT')} TP3 WIN W{STATS['wins']} L{STATS['losses']}"); save_a(); continue
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: continue
            d4=kl(sym,"Hour4"); time.sleep(0.3)
            if not d4: continue
            if is_choppy_4H(d4): continue
            manip_ok, manip_dir, manip_level, manip_extreme = detect_4H_MANIPULATION(d4)
            if not manip_ok: continue
            if manip_dir=="BUY" and btc_trend=="DOWN": continue
            if manip_dir=="SELL" and btc_trend!="DOWN": continue
            entry_15m, sl_15m, reason_15m = get_15m_refined_entry(sym, manip_dir)
            if not entry_15m: print(f"WAIT {sym} {manip_dir} no 15m"); continue
            live=entry_15m; is_buy=manip_dir=="BUY"; sl=sl_15m
            tp1=get_next_liq(d4,live,is_buy,0); tp2=get_next_liq(d4,live,is_buy,1); tp3=get_next_liq(d4,live,is_buy,2); runner=get_next_liq(d4,live,is_buy,3)
            risk=abs(live-sl)/live*100; reward=abs(tp1-live)/live*100; rr=reward/risk if risk>0 else 0
            if rr<2.0: continue
            print(f"READY {sym} {manip_dir} {reason_15m} RR{rr:.1f}")
            cands.append((95,sym,manip_dir,live,sl,tp1,tp2,tp3,runner,rr,manip_extreme,manip_level,reason_15m))
        except Exception as e:
            print(f"EX {sym} {e}"); continue
    cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,dir,live,sl,tp1,tp2,tp3,runner,rr,manip_ex,manip_level,reason15 in cands:
        is_buy=dir=="BUY"
        ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":TAG,"score":score,"rr":rr,"ts":time.time()}; save_a()
        emoji="🟢" if is_buy else "🔴"; side="BUY" if is_buy else "SELL"
        tg(f"{emoji} {side} {sym.replace('_USDT','USDT')} | {TAG}\n4H {dir} Sweep {fmt(manip_ex)} Prev {fmt(manip_level)} BTC:{btc_trend}\n{reason15}\nEntry {fmt(live)} SL {fmt(sl)}\nTP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}\nRR {rr:.1f} W{STATS['wins']} L{STATS['losses']}")

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"EX {e}")
            time.sleep(900)
