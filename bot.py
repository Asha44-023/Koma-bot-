# BOT V42.9 MINIMAL - NO HOLD SPAM - NO DUPLICATE - STRICT TREND
import time, json, os, requests, fcntl
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
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

def kl(sym,interval):
    try:
        r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval={interval}",timeout=10).json()
        data=r.get("data",[])
        if isinstance(data,dict) and len(data.get("close",[]))>10:
            return {"o":[float(x) for x in data["open"]],"h":[float(x) for x in data["high"]],"l":[float(x) for x in data["low"]],"c":[float(x) for x in data["close"]]}
        if isinstance(data,list) and len(data)>10:
            o,h,l,c=[],[],[],[]
            for k in data:
                try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4]))
                except: continue
            return {"o":o,"h":h,"l":l,"c":c}
    except: return None
    return None

def get_bias(d):
    if len(d["c"])<50: return "RANGE"
    lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2; ema=sum(d["c"][-50:])/50
    if d["c"][-1]>mid and d["c"][-1]>ema: return "BULL"
    if d["c"][-1]<mid and d["c"][-1]<ema: return "BEAR"
    return "RANGE"

def fbs_logic(h,l,c,o):
    if len(c)<3: return None,None
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; cc=c[-1]; co=o[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35; p22=pl+pr*0.22; p78=pl+pr*0.78
    if pc>=p58 and cc>=p35 and cc>co: return "BOS_UP",True
    if pc<=p35 and cc<=p58 and cc<co: return "BOS_DOWN",False
    return None,None

def is_close(d5,is_buy):
    if len(d5["c"])<4: return False,""
    ph,pl=d5["h"][-2],d5["l"][-2]; pr=ph-pl or 1
    p58=pl+pr*0.58; p56=pl+pr*0.56; p35=pl+pr*0.35; cc=d5["c"][-1]
    if is_buy and cc<p35: return True,f"lost p35 {cc:.5f}<{p35:.5f}"
    if not is_buy and cc>p58: return True,f"lost p58 {cc:.5f}>{p58:.5f}"
    return False,""

def manage():
    global ACTIVE
    if not ACTIVE: return
    now=time.time()
    for s in list(ACTIVE.keys()):
        d5=kl(SYMBOL_MAP[s],"Min15")
        if not d5: continue
        pos=ACTIVE[s]; is_buy=pos["is_buy"]; cur=d5["c"][-1]; entry=pos["entry"]
        pnl=(cur-entry)/entry if is_buy else (entry-cur)/entry
        age=(now-pos["time"])/60
        rev,reason=is_close(d5,is_buy)
        if rev and age>8 and pnl<0.01:
            tg(f"🔵 CLOSE BOTH 58/35 {s} {'BUY' if is_buy else 'SELL'} {pnl*100:+.1f}% | {reason} | {age:.0f}m | {get_time()}")
            del ACTIVE[s]; save_a(); continue
        cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            tg(f"🔴 SL {s} {pnl*100:.1f}% | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if pnl>=cfg["tp4"]:
            tg(f"🟢 TP4 {s} +{pnl*100:.1f}% CLOSE | {get_time()}"); del ACTIVE[s]; save_a()

def scan():
    global COOLDOWN, ACTIVE
    if os.path.exists(COOLDOWN_FILE):
        try: COOLDOWN=json.load(open(COOLDOWN_FILE))
        except: pass
    if os.path.exists(ACTIVE_FILE):
        try: ACTIVE=json.load(open(ACTIVE_FILE))
        except: pass
    manage()
    for s in SYMBOLS:
        if s in ACTIVE: continue
        if time.time()-COOLDOWN["signals"].get(s,0) < 1800: continue
        d240=kl(SYMBOL_MAP[s],"Min240"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d5: continue
        bias=get_bias(d240)
        fbs,is_buy=fbs_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: continue
        # STRICT TREND - NO SELL IN BULL, NO BUY IN BEAR
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue
        entry=d5["l"][-2]+(d5["h"][-2]-d5["l"][-2])*0.56
        cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        tp1=entry*(1+cfg["tp1"]) if is_buy else entry*(1-cfg["tp1"])
        side="🟢 BUY" if is_buy else "🔴 SELL"
        tg(f"{side} {s} {fbs}\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f} | {get_time()} | 4H {bias}")
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()

if __name__=="__main__":
    fp=open(LOCK_FILE,"w")
    try: fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except: print("Bot already running"); exit(1)
    tg(f"🚀 BOT V42.9 MINIMAL | {get_time()}")
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(60)
