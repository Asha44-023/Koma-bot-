import json, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
import numpy as np
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"); TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE="active.json","cooldown.json","stats_v192.json"
MAX_ACTIVE=35; TOP_N_PER_SCAN=3; RR_MIN=1.2
session=requests.Session(); TAG="V195-PURE-4H-MANIP-SAFE"

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

# YOUR RULE ONLY
def detect_4H_MANIPULATION(d4):
    try:
        if len(d4["c"]) < 3: return False, "", 0, 0
        prev_low = d4["l"][-2]; prev_high = d4["h"][-2]
        curr_low = d4["l"][-1]; curr_high = d4["h"][-1]
        curr_open = d4["o"][-1]; curr_close = d4["c"][-1]
        # BUY: sweep below prev low, close back above prev low
        if curr_low < prev_low * 0.9995 and curr_close > prev_low and curr_close > curr_open:
            return True, "BUY", prev_low, curr_low
        # SELL: sweep above prev high, close back below prev high
        if curr_high > prev_high * 1.0005 and curr_close < prev_high and curr_close < curr_open:
            return True, "SELL", prev_high, curr_high
    except: pass
    return False, "", 0, 0

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
            tg(f"❌ {sym.replace('_USDT','USDT')} {pnl:.1f}% SL hit 4H-MANIP"); ACTIVE.pop(sym,None); save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)): data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP1 BE - 4H-MANIP")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)): data["tp2_hit"]=True; data["sl"]=tp1; save_a(); tg(f"🟢 {sym.replace('_USDT','USDT')} TP2 - 4H-MANIP")
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)): 
            data["tp3_hit"]=True; STATS["wins"]+=1; save_s()
            tg(f"✅ {sym.replace('_USDT','USDT')} TP3 WIN W{STATS['wins']} L{STATS['losses']}"); save_a(); continue
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: continue
            d4=kl(sym,"Hour4"); time.sleep(0.4)
            if not d4: continue
            live=get_live(sym) or d4["c"][-1]
            manip_ok, manip_dir, manip_level, manip_extreme = detect_4H_MANIPULATION(d4)
            if not manip_ok: continue
            # SAFE MODE - FOLLOW BTC
            if manip_dir == "BUY" and btc_trend == "DOWN": 
                print(f"SKIP {sym} 4H-MANIP BUY blocked BTC:{btc_trend}")
                continue
            if manip_dir == "SELL" and btc_trend != "DOWN":
                print(f"SKIP {sym} 4H-MANIP SELL blocked BTC:{btc_trend}")
                continue
            is_buy = manip_dir == "BUY"
            sl = manip_extreme * 0.998 if is_buy else manip_extreme * 1.002
            tp1=get_next_liq(d4,live,is_buy,0); tp2=get_next_liq(d4,live,is_buy,1); tp3=get_next_liq(d4,live,is_buy,2); runner=get_next_liq(d4,live,is_buy,3)
            risk=abs(live-sl)/live*100; reward=abs(tp1-live)/live*100; rr=reward/risk if risk>0 else 0
            if rr < 1.0: continue
            cands.append((95,sym,manip_dir,live,sl,tp1,tp2,tp3,runner,rr,manip_extreme,manip_level))
        except Exception as e:
            print(f"EX {sym} {e}"); continue
    cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,dir,live,sl,tp1,tp2,tp3,runner,rr,manip_ex,manip_level in cands:
        is_buy=dir=="BUY"
        ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":"4H-MANIP","score":score,"rr":rr,"ts":time.time()}; save_a()
        emoji="🟢" if is_buy else "🔴"; side="BUY" if is_buy else "SELL"
        tg(f"{emoji} {side} {sym.replace('_USDT','USDT')} | PURE 4H-MANIP | 95\nSweep {fmt(manip_ex)} Prev {fmt(manip_level)} BTC:{btc_trend}\nEntry {fmt(live)} SL {fmt(sl)}\nTP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} Runner {fmt(runner)}\nRR {rr:.1f} W{STATS['wins']} L{STATS['losses']}")

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"EX {e}")
            time.sleep(900)
