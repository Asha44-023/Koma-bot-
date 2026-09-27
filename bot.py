# BOT V46.2.1 - FIXED: NO CLOSE IN PROFIT + SIMPLE WARNINGS
import time, json, os, requests, fcntl, sys
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
FAST_COINS={"SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"}
SLOW_COINS={"GRASSUSDT","TAOUSDT","SANDUSDT","JASMYUSDT"}

PER_COIN_TP={
    "GRASSUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.12,"tp3":0.22,"tp4":0.30},
    "FARTCOINUSDT":{"sl":0.025,"tp1":0.06,"tp2":0.12,"tp3":0.20,"tp4":0.28},
    "KOMAUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.10,"tp3":0.18,"tp4":0.25},
    "SENTUSDT":{"sl":0.022,"tp1":0.04,"tp2":0.08,"tp3":0.15,"tp4":0.22},
    "LABUSDT":{"sl":0.025,"tp1":0.06,"tp2":0.12,"tp3":0.20,"tp4":0.28},
    "SIRENUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.10,"tp3":0.18,"tp4":0.25},
    "TAOUSDT":{"sl":0.015,"tp1":0.025,"tp2":0.05,"tp3":0.08,"tp4":0.12},
    "SANDUSDT":{"sl":0.012,"tp1":0.02,"tp2":0.04,"tp3":0.07,"tp4":0.10},
    "JASMYUSDT":{"sl":0.015,"tp1":0.025,"tp2":0.05,"tp3":0.08,"tp4":0.12},
}
COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"; LOCK_FILE="/tmp/bot.lock"
COOLDOWN={"signals":{}}; ACTIVE={}
WARN_TIME={}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: pass
if os.path.exists(ACTIVE_FILE):
    try: ACTIVE=json.load(open(ACTIVE_FILE))
    except: pass

def save_c(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_a(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
def get_time():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")
def tg(msg):
    print(msg,flush=True)
    try:
        token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
        if token and chat: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
    except: pass

def kl(sym,interval):
    headers={"User-Agent":"Mozilla/5.0"}
    spot_sym=sym.replace("_",""); spot_iv={"Min15":"15m","Min60":"60m","Min240":"4h"}.get(interval,"15m")
    urls=[f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval={interval}",f"https://api.mexc.com/api/v3/klines?symbol={spot_sym}&interval={spot_iv}&limit=200",f"https://futures.mexc.com/api/v1/contract/kline/{sym}?interval={interval}"]
    for url in urls:
        try:
            r=requests.get(url,timeout=12,headers=headers).json()
            data=r.get("data",[]) if isinstance(r,dict) else r
            if isinstance(data,dict) and "close" in data and len(data["close"])>20:
                return {"o":[float(x) for x in data["open"]],"h":[float(x) for x in data["high"]],"l":[float(x) for x in data["low"]],"c":[float(x) for x in data["close"]]}
            if isinstance(data,list) and len(data)>20:
                o,h,l,c=[],[],[],[]
                for k in data:
                    try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4]))
                    except: continue
                if len(c)>20: return {"o":o,"h":h,"l":l,"c":c}
        except: continue
    return None

def get_bias_4h(d):
    if len(d["c"])<50: return "RANGE",""
    LOOKBACK=48; lo=min(d["l"][-LOOKBACK:]); hi=max(d["h"][-LOOKBACK:]); mid=(lo+hi)/2; ema=sum(d["c"][-50:])/50
    if d["c"][-1]>mid and d["c"][-1]>ema: return "BULL","Above 4H SD mid+EMA"
    if d["c"][-1]<mid and d["c"][-1]<ema: return "BEAR","Below 4H SD mid+EMA"
    return "RANGE","4H Range"
def detect_fvg_1h(d):
    b=False; br=False
    if len(d["c"])<10: return False,False
    for i in range(-10,-2):
        if d["l"][i] > d["h"][i-2]: b=True
        if d["h"][i] < d["l"][i-2]: br=True
    return b,br
def detect_ob_1h(d):
    b=False; br=False
    if len(d["c"])<10: return False,False
    for i in range(-6,-1):
        body=abs(d["c"][i]-d["o"][i]); rng=d["h"][i]-d["l"][i] or 1
        if d["c"][i] < d["o"][i] and d["c"][-1] > d["h"][i] and body/rng>0.4: b=True
        if d["c"][i] > d["o"][i] and d["c"][-1] < d["l"][i] and body/rng>0.4: br=True
    return b,br
def detect_liquidity_1h(d):
    b=False; br=False
    if len(d["c"])<20: return False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2])
    if d["h"][-2] > recent_high and d["c"][-1] < recent_high: br=True
    if d["l"][-2] < recent_low and d["c"][-1] > recent_low: b=True
    return b,br
def detect_breaker_1h(d):
    b=False; br=False
    if len(d["c"])<20: return False,False
    for i in range(-18,-5):
        ob_high=d["h"][i]; ob_low=d["l"][i]
        if d["c"][i] < d["o"][i]:
            broken=False
            for j in range(i+1,-2):
                if d["c"][j] > ob_high: broken=True; break
            if broken and d["l"][-1] <= ob_high and d["l"][-1] >= ob_low*0.995: b=True
        if d["c"][i] > d["o"][i]:
            broken=False
            for j in range(i+1,-2):
                if d["c"][j] < ob_low: broken=True; break
            if broken and d["h"][-1] >= ob_low and d["h"][-1] <= ob_high*1.005: br=True
    return b,br
def detect_choch_1h(d):
    b=False; br=False
    if len(d["c"])<30: return False,False
    try:
        last_high=max(d["h"][-20:-3]); prev_high=max(d["h"][-35:-20])
        last_low=min(d["l"][-20:-3]); prev_low=min(d["l"][-35:-20])
        if prev_high > last_high and d["c"][-1] > last_high and d["c"][-2] <= last_high: b=True
        if prev_low < last_low and d["c"][-1] < last_low and d["c"][-2] >= last_low: br=True
    except: pass
    return b,br

def check_1h_confluence(d1, is_buy, is_slow=False):
    bull_fvg,bear_fvg=detect_fvg_1h(d1); bull_ob,bear_ob=detect_ob_1h(d1); bull_liq,bear_liq=detect_liquidity_1h(d1); bull_brk,bear_brk=detect_breaker_1h(d1); bull_choch,bear_choch=detect_choch_1h(d1)
    if is_buy:
        reason=f"FVG:{bull_fvg} OB:{bull_ob} LIQ:{bull_liq} BRK:{bull_brk} CHOCH:{bull_choch}"
        ok = (bull_ob or bull_brk or bull_liq or bull_fvg) if is_slow else (bull_ob or bull_brk)
        return ok,reason
    else:
        reason=f"FVG:{bear_fvg} OB:{bear_ob} LIQ:{bear_liq} BRK:{bear_brk} CHOCH:{bear_choch}"
        ok = (bear_ob or bear_brk or bear_liq or bear_fvg) if is_slow else (bear_ob or bear_brk)
        return ok,reason

def fbs_logic(h,l,c,o):
    if len(c)<3: return None,None,None
    ph,pl=h[-2],l[-2]; pc=c[-2]; cc=c[-1]; co=o[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35
    if pc>=p58 and cc>=p35 and cc>co: return "BOS_UP",True,"Prev>58% Curr>35%"
    if pc<=p35 and cc<=p58 and cc<co: return "BOS_DOWN",False,"Prev<35% Curr<58%"
    return None,None,None

def is_close(d5,is_buy):
    if len(d5["c"])<4: return False,""
    ph,pl=d5["h"][-2],d5["l"][-2]; pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35; cc=d5["c"][-1]
    if is_buy and cc<p35: return True,"lost p35"
    if not is_buy and cc>p58: return True,"lost p58"
    return False,""

def manage():
    global ACTIVE
    if not ACTIVE: return
    now=time.time(); summary=[]
    for s in list(ACTIVE.keys()):
        d5=kl(SYMBOL_MAP[s],"Min15"); d60=kl(SYMBOL_MAP[s],"Min60"); d240=kl(SYMBOL_MAP[s],"Min240")
        if not d5: continue
        pos=ACTIVE[s]; is_buy=pos["is_buy"]; cur=d5["c"][-1]; entry=pos["entry"]
        pnl=(cur-entry)/entry if is_buy else (entry-cur)/entry
        age=(now-pos["time"])/60; cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            tg(f"🔴 SL {s} {pnl*100:.1f}% {age/60:.1f}h | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if pnl>=cfg["tp4"]:
            tg(f"🟢 TP4 {s} +{pnl*100:.1f}% {age/60:.1f}h | {get_time()}"); del ACTIVE[s]; save_a(); continue

        rev,_=is_close(d5,is_buy)
        if rev and age>20:
            bull_ob,bear_ob=detect_ob_1h(d60) if d60 else (False,False)
            bull_liq,bear_liq=detect_liquidity_1h(d60) if d60 else (False,False)
            is_ob_hold=bull_ob if is_buy else bear_ob
            is_liq=bull_liq if is_buy else bear_liq

            if is_ob_hold and is_liq:
                if s not in WARN_TIME or now-WARN_TIME.get(s,0)>1800:
                    tg(f"💧 LIQ GRAB {s} {pnl*100:+.1f}% | HOLD - DON'T CLOSE | {get_time()}")
                    WARN_TIME[s]=now
                continue

            if s in FAST_COINS:
                if pnl < 0: # FIXED: only if losing
                    if s not in WARN_TIME or now-WARN_TIME.get(s,0)>900:
                        tg(f"⚠️ REVERSAL {s} {pnl*100:+.1f}% | CLOSE in ~12m | {get_time()}")
                        WARN_TIME[s]=now
                    if pnl > -0.007: continue
                    tg(f"🔵 CLOSE FAST {s} {pnl*100:+.1f}% {age:.0f}m | {get_time()}"); del ACTIVE[s]; save_a(); continue

            if s in SLOW_COINS:
                if d240:
                    bull_choch,bear_choch=detect_choch_1h(d240)
                    if (is_buy and bear_choch) or (not is_buy and bull_choch):
                        if s not in WARN_TIME or now-WARN_TIME.get(s,0)>900:
                            tg(f"⚠️ REVERSAL {s} {pnl*100:+.1f}% | CLOSE in ~15m | {get_time()}")
                            WARN_TIME[s]=now
                        if pnl > -0.01: continue
                        if pnl < 0:
                            tg(f"🔵 CLOSE SLOW CHOCH {s} {pnl*100:+.1f}% {age/60:.1f}h | {get_time()}"); del ACTIVE[s]; save_a(); continue
                if age>1440 and pnl<0:
                    tg(f"🔵 CLOSE SLOW 24H {s} {pnl*100:+.1f}% | {get_time()}"); del ACTIVE[s]; save_a(); continue

        summary.append(f"{s} {pnl*100:+.1f}% {age/60:.1f}h")
    if summary and int(now)%3600<90:
        tg(f"📊 OPEN: {' | '.join(summary)} | {get_time()}")

def scan():
    global COOLDOWN,ACTIVE
    if os.path.exists(COOLDOWN_FILE):
        try: COOLDOWN=json.load(open(COOLDOWN_FILE))
        except: pass
    if os.path.exists(ACTIVE_FILE):
        try: ACTIVE=json.load(open(ACTIVE_FILE))
        except: pass
    print(f"Starting scan {len(SYMBOLS)} pairs...",flush=True)
    manage(); found=0
    for s in SYMBOLS:
        if s in ACTIVE: print(f"{s} -> skip ACTIVE",flush=True); continue
        is_slow=s in SLOW_COINS
        cooldown_needed=7200 if not is_slow else 21600
        if time.time()-COOLDOWN["signals"].get(s,0)<cooldown_needed: print(f"{s} -> skip COOLDOWN {cooldown_needed/3600:.0f}H",flush=True); continue
        d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d5: print(f"{s} -> kl fail",flush=True); continue
        bias,_=get_bias_4h(d240); print(f"{s} 4H:{bias}",flush=True)
        if bias=="RANGE": continue
        fbs,is_buy,_=fbs_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: print(f"{s} -> no 15M BOS",flush=True); continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue
        ok_1h,smc_reason=check_1h_confluence(d60,is_buy,is_slow=is_slow); print(f"{s} 1H:{smc_reason} ok={ok_1h}",flush=True)
        if not ok_1h: continue
        ph=d5["h"][-2]; pl=d5["l"][-2]
        entry=pl+(ph-pl)*0.50
        cfg=PER_COIN_TP[s]; sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"]); tp1=entry*(1+cfg["tp1"]) if is_buy else entry*(1-cfg["tp1"])
        side="🟢 BUY" if is_buy else "🔴 SELL"; tag="FAST" if not is_slow else "SLOW"
        tg(f"{side} {s} {fbs} [{tag}]\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f}\n4H:{bias}\n1H:{smc_reason}\n{get_time()}")
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c(); found+=1
    print(f"Scan done. Found {found} signals. {get_time()}",flush=True)

if __name__=="__main__":
    fp=open(LOCK_FILE,"w")
    try: fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except:
        if "--once" not in sys.argv: print("Bot already running"); exit(1)
    print(f"🚀 BOT V46.2.1 FIXED 50% + LIQ GRAB + REVERSAL | {get_time()}",flush=True)
    if "--once" in sys.argv:
        try: scan()
        except Exception as e: print(f"SCAN ERROR {e}",flush=True)
        exit(0)
    while True:
        try: scan()
        except Exception as e: print(f"LOOP ERROR {e}",flush=True)
        time.sleep(60)
