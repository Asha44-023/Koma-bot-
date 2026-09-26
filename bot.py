# BOT V42.8 FINAL - BOTH 58/35 + TREND FILTER + CLOSE NOW 10MIN + NO DUPLICATE
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
for fp in [COOLDOWN_FILE, ACTIVE_FILE]:
    if os.path.exists(fp):
        try:
            d=json.load(open(fp))
            if "cooldown" in fp: COOLDOWN=d
            else: ACTIVE=d
        except: pass

def save_c(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_a(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))

def get_time_12hr():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")

def tg(msg):
    print(msg,flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or ""; chat=os.getenv("TELEGRAM_CHAT_ID") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
        except: pass

def kl(sym,interval):
    def fetch(u_sym, inter):
        try:
            r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{u_sym}?interval={inter}", timeout=10).json()
            data=r.get("data",[])
            if isinstance(data,dict) and len(data.get("close",[]))>10:
                return {"o":[float(x) for x in data["open"]],"h":[float(x) for x in data["high"]],"l":[float(x) for x in data["low"]],"c":[float(x) for x in data["close"]]}
            elif isinstance(data,list) and len(data)>10:
                o,h,l,c=[],[],[],[]
                for k in data:
                    try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4]))
                    except: continue
                return {"o":o,"h":h,"l":l,"c":c}
        except: return None
    res=fetch(sym,interval)
    if res: return res
    if interval=="Min240":
        d60=fetch(sym,"Min60")
        if not d60 or len(d60["c"])<200: return None
        o,h,l,c=[],[],[],[]
        for i in range(0,len(d60["c"])-3,4):
            if len(d60["c"][i:i+4])<4: continue
            o.append(d60["o"][i]); h.append(max(d60["h"][i:i+4])); l.append(min(d60["l"][i:i+4])); c.append(d60["c"][i+3])
        return {"o":o,"h":h,"l":l,"c":c}
    return None

def get_4h_bias(d240):
    h,l,c=d240["h"],d240["l"],d240["c"]
    if len(c)<50: return "RANGE",0,0
    crt_low=min(l[-48:]); crt_high=max(h[-48:]); mid=(crt_low+crt_high)/2; ema50=sum(c[-50:])/50
    bias="BULL" if c[-1]>mid and c[-1]>ema50 else "BEAR" if c[-1]<mid and c[-1]<ema50 else "RANGE"
    return bias,crt_low,crt_high

def is_grab(h,l,c,crt_low,crt_high):
    if h[-2] > crt_high*1.001 and c[-1] < crt_high*0.999: return "BEAR_GRAB"
    if l[-2] < crt_low*0.999 and c[-1] > crt_low*1.001: return "BULL_GRAB"
    return None

def confirm_grab(h,l,c,o,grab):
    pr=h[-2]-l[-2] or 1; p35=l[-2]+pr*0.35; p58=l[-2]+pr*0.58
    if grab=="BEAR_GRAB":
        return ("FAKE_CONTINUE_BUY",True) if c[-1]>=p35 and c[-1]>o[-1] else ("REAL_REVERSE_SELL",False)
    if grab=="BULL_GRAB":
        return ("FAKE_CONTINUE_SELL",False) if c[-1]<=p58 and c[-1]<o[-1] else ("REAL_REVERSE_BUY",True)
    return None,None

def is_consolidation_face(h,l,c):
    if len(c) < 20: return False
    recent_range = max(h[-8:]) - min(l[-8:])
    avg_range = sum([h[i]-l[i] for i in range(-20,-1)])/20
    up = sum(1 for i in range(-8,-1) if c[i] > c[i-1])
    return recent_range < avg_range*0.85 and 2 <= up <= 6

def range_logic(h,l,c,o):
    if len(c) < 3: return None,None
    ph,pl=h[-2],l[-2]; pr=ph-pl or 1
    p58=pl+pr*0.58; p35=pl+pr*0.35; p56=pl+pr*0.56
    cc=c[-1]; co=o[-1]; cl=l[-1]; ch=h[-1]
    if cl < p35 and cc > p35 and cc > co and cc >= p56*0.999:
        return f"RANGE_BEAR_TRAP_BUY 35/58", True
    if ch > p58 and cc < p58 and cc < co and cc <= p56*1.001:
        return f"RANGE_BULL_TRAP_SELL 58/35", False
    return None,None

def fbs_logic(h,l,c,o):
    if is_consolidation_face(h,l,c):
        r_side, r_buy = range_logic(h,l,c,o)
        if r_side: return r_side, r_buy
        return None,None
    if len(c)<3: return None,None
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; cc=c[-1]; co=o[-1]; ch=h[-1]; cl=l[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35; p22=pl+pr*0.22; p78=pl+pr*0.78
    if pc>=p58 and cc>=p35 and cl>=p22 and cc>co: return "BOS_UP_STRONG",True
    if pc<=p35 and cc<=p58 and ch<=p78 and cc<co: return "BOS_DOWN_STRONG",False
    if pc>po and (ph-max(pc,po))>abs(pc-po)*1.2 and cc<p78: return "WEAK_BULL_TRAP",False
    if pc<po and (min(pc,po)-pl)>abs(pc-po)*1.2 and cc>p22: return "WEAK_BEAR_TRAP",True
    return None,None

def is_fake_body(h,l,c,o,is_buy):
    ph,pl=h[-2],l[-2]; pr=ph-pl or 1; p35=pl+pr*0.35; p58=pl+pr*0.58
    body=abs(c[-1]-o[-1]); rng=h[-1]-l[-1] or 1
    if body/rng < 0.25: return True
    if is_buy and c[-1] < p35: return True
    if not is_buy and c[-1] > p58: return True
    return False

def is_close_now_both_5835(d5, is_buy):
    h,l,c,o=d5["h"],d5["l"],d5["c"],d5["o"]
    if len(c) < 4: return False,""
    ph,pl=h[-2],l[-2]; pr=ph-pl or 1
    p58=pl+pr*0.58; p56=pl+pr*0.56; p35=pl+pr*0.35
    cc=c[-1]
    if is_buy:
        if cc < p35: return True, f"BUY->SELL 35/58 lost p35 {cc:.5f}<{p35:.5f}"
        if cc < p56 and c[-1] < c[-2]: return True, f"BUY->SELL towards 35/58 below p56"
    else:
        if cc > p58: return True, f"SELL->BUY 58/35 lost p58 {cc:.5f}>{p58:.5f}"
        if cc > p56 and c[-1] > c[-2]: return True, f"SELL->BUY towards 58/35 above p56"
    return False,""

def manage_active():
    global ACTIVE
    if not ACTIVE: return
    now=time.time()
    for s in list(ACTIVE.keys()):
        perp=SYMBOL_MAP.get(s)
        d5=kl(perp,"Min15")
        if not d5: continue
        pos=ACTIVE[s]; entry=pos["entry"]; is_buy=pos["is_buy"]; cur=d5["c"][-1]
        cfg=PER_COIN_TP[s]
        pnl = (cur-entry)/entry if is_buy else (entry-cur)/entry
        pnl_pct=pnl*100
        age_min = (now-pos.get("time",now))/60
        rev,reason = is_close_now_both_5835(d5, is_buy)
        if rev and age_min <= 12:
            tg(f"🔵 CLOSE NOW BOTH 58/35 {s} {'BUY' if is_buy else 'SELL'} {pnl_pct:+.1f}% | {reason} | {age_min:.0f}m | {get_time_12hr()}")
            del ACTIVE[s]; save_a(); continue
        if rev and age_min>12 and pnl<0.01:
            tg(f"🔵 CLOSE 10MIN+ BOTH 58/35 {s} {'BUY' if is_buy else 'SELL'} {pnl_pct:+.1f}% | {reason} | {age_min:.0f}m | {get_time_12hr()}")
            del ACTIVE[s]; save_a(); continue
        if pos.get("be_price"):
            be=pos["be_price"]
            if (is_buy and cur <= be) or (not is_buy and cur >= be):
                tg(f"🟡 BE HIT {s} {pos['side']} {pnl_pct:+.1f}% | {get_time_12hr()}")
                del ACTIVE[s]; save_a(); continue
        sl_price = entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        if (is_buy and cur <= sl_price) or (not is_buy and cur >= sl_price):
            tg(f"🔴 SL HIT {s} {pos['side']} {pnl_pct:.1f}% | {get_time_12hr()}")
            del ACTIVE[s]; save_a(); continue
        side="BUY" if is_buy else "SELL"
        if pnl >= cfg["tp4"]:
            tg(f"🟢 TP4 HIT {s} {side} +{pnl_pct:.1f}% CLOSE | {get_time_12hr()}")
            del ACTIVE[s]; save_a()
        elif pnl >= cfg["tp3"] and not pos.get("tp3"):
            tg(f"🟢 TP3 HIT {s} {side} +{pnl_pct:.1f}% | {get_time_12hr()}")
            pos["tp3"]=True; save_a()
        elif pnl >= cfg["tp2"] and not pos.get("tp2"):
            tg(f"🟢 TP2 HIT {s} {side} +{pnl_pct:.1f}% | {get_time_12hr()}")
            pos["tp2"]=True; save_a()
        elif pnl >= cfg["tp1"] and not pos.get("tp1"):
            tg(f"🟡 TP1 HIT + BE {s} {side} +{pnl_pct:.1f}% SL→BE | {get_time_12hr()}")
            pos["tp1"]=True; pos["be_price"]=entry; save_a()

def full_scan():
    global COOLDOWN, ACTIVE
    # === FIX 1: RELOAD FROM DISK EVERY LOOP - STOPS DUPLICATES ===
    if os.path.exists(COOLDOWN_FILE):
        try: COOLDOWN=json.load(open(COOLDOWN_FILE))
        except: pass
    if os.path.exists(ACTIVE_FILE):
        try: ACTIVE=json.load(open(ACTIVE_FILE))
        except: pass

    manage_active()
    for s in SYMBOLS:
        if s in ACTIVE: continue
        perp=SYMBOL_MAP[s]
        d60=kl(perp,"Min60"); d5=kl(perp,"Min15"); d240=kl(perp,"Min240")
        if not d60 or not d5 or not d240: continue
        bias_4h,crt_low,crt_high=get_4h_bias(d240)
        fbs,is_buy = fbs_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: continue
        now=time.time()
        if now-COOLDOWN["signals"].get(s,0) < 1800: continue

        # === TREND FILTER STRICT ===
        if bias_4h=="BULL" and not is_buy: continue
        if bias_4h=="BEAR" and is_buy: continue

        grab=is_grab(d5["h"],d5["l"],d5["c"],crt_low,crt_high)
        if grab:
            fbs,is_buy = confirm_grab(d5["h"],d5["l"],d5["c"],d5["o"],grab)
            if not fbs: continue
            if bias_4h=="BULL" and not is_buy: continue
            if bias_4h=="BEAR" and is_buy: continue
        else:
            if is_fake_body(d5["h"],d5["l"],d5["c"],d5["o"],is_buy): continue

        entry=d5["l"][-2] + (d5["h"][-2]-d5["l"][-2])*0.56
        cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        tp1=entry*(1+cfg["tp1"]) if is_buy else entry*(1-cfg["tp1"])
        tp2=entry*(1+cfg["tp2"]) if is_buy else entry*(1-cfg["tp2"])
        side="🟢 BUY" if is_buy else "🔴 SELL"
        tg(f"{side} {s} {fbs}\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f}/{tp2:.5f} | {get_time_12hr()} | 4H {bias_4h}")
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"side":side,"time":now,"tp1":False,"tp2":False,"tp3":False}
        save_a(); COOLDOWN["signals"][s]=now; save_c()

if __name__=="__main__":
    # === FIX 2: SINGLE INSTANCE LOCK - STOPS x2/x3 DUPLICATES ===
    lock_fp=open(LOCK_FILE,"w")
    try: fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except: print("Another bot already running! Run: pkill -9 -f bot"); exit(1)

    tg(f"🚀 BOT V42.8 FINAL BOTH 58/35 ALL CORRECTIONS + NODUP 9coins | {get_time_12hr()}")
    while True:
        try: full_scan()
        except Exception as e: print(e)
        time.sleep(60)
