# BOT V42.2 FINAL - BOTH WAYS GRAB + 58/35 SYMMETRIC
import time, json, os, requests
from datetime import datetime
from zoneinfo import ZoneInfo

VERBOSE=False
SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
FAST_SYMS=["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT","LABUSDT","SIRENUSDT"]

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

COOLDOWN_FILE="cooldown.json"; WALL_FILE="wall_alerts.json"; ACTIVE_FILE="active.json"
COOLDOWN={"signals":{}}; WALL_ALERTS={}; ACTIVE={}
for fp,ref in [(COOLDOWN_FILE,COOLDOWN),(WALL_FILE,WALL_ALERTS),(ACTIVE_FILE,ACTIVE)]:
    if os.path.exists(fp):
        try:
            d=json.load(open(fp))
            if fp==COOLDOWN_FILE: COOLDOWN=d
            elif fp==WALL_FILE: WALL_ALERTS=d
            else: ACTIVE=d
        except: pass
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_wall(): open(WALL_FILE,"w").write(json.dumps(WALL_ALERTS))
def save_active(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))

def get_time_12hr():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")
def tg(msg):
    print(msg,flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

def kl(sym,interval):
    def fetch(url_sym, inter):
        urls=[f"https://contract.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",f"https://futures.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}"]
        for u in urls:
            try:
                r=requests.get(u, timeout=10).json(); data=r.get("data",[])
                if not data: continue
                if isinstance(data,dict):
                    if len(data.get("close",[]))>10:
                        return {"o":[float(x) for x in data.get("open",[])],"h":[float(x) for x in data.get("high",[])],"l":[float(x) for x in data.get("low",[])],"c":[float(x) for x in data.get("close",[])],"v":[float(x) for x in data.get("vol",[])]}
                else:
                    o,h,l,c,v=[],[],[],[],[]
                    for k in data:
                        try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
                        except: continue
                    if len(c)>10: return {"o":o,"h":h,"l":l,"c":c,"v":v}
            except: continue
        return None
    res=fetch(sym, interval)
    if res: return res
    if interval=="Min240":
        d60=fetch(sym, "Min60")
        if not d60 or len(d60["c"])<200: return None
        o,h,l,c,v=[],[],[],[],[]
        for i in range(0, len(d60["c"])-3, 4):
            if len(d60["c"][i:i+4])<4: continue
            o.append(d60["o"][i]); h.append(max(d60["h"][i:i+4])); l.append(min(d60["l"][i:i+4])); c.append(d60["c"][i+3]); v.append(sum(d60["v"][i:i+4]))
        if len(c)>20: return {"o":o,"h":h,"l":l,"c":c,"v":v}
    return None

def get_4h_bias(d240):
    h,l,c=d240["h"],d240["l"],d240["c"]
    if len(c)<50: return None,0,0
    crt_low=min(l[-48:]); crt_high=max(h[-48:]); mid=(crt_low+crt_high)/2; ema50=sum(c[-50:])/50
    bias="BULL" if c[-1]>mid and c[-1]>ema50 else "BEAR" if c[-1]<mid and c[-1]<ema50 else "RANGE"
    return bias,crt_low,crt_high

# === BOTH WAYS GRAB LOGIC ===
def is_liquidity_grab(h,l,c,o, crt_low, crt_high):
    # wick based
    if h[-2] > crt_high*1.001 and c[-1] < crt_high*0.999: # bear grab up
        return "BEAR_GRAB"
    if l[-2] < crt_low*0.999 and c[-1] > crt_low*1.001: # bull grab down
        return "BULL_GRAB"
    return None

def confirm_grab_both_ways(h,l,c,o, grab_type, ob_56):
    live=c[-1]; prange=h[-2]-l[-2] or 1
    p35_zone = l[-2] + prange*0.35
    p58_zone = l[-2] + prange*0.58
    if grab_type=="BEAR_GRAB": # was UP, wicked above
        if live >= p35_zone and c[-1] > o[-1]: # reclaimed OB 56
            return "FAKE_CONTINUE_BUY" # go back UP
        else:
            return "REAL_REVERSE_SELL" # real reversal DOWN
    if grab_type=="BULL_GRAB": # was DOWN, wicked below
        if live <= p58_zone and c[-1] < o[-1]: # reclaimed from below
            return "FAKE_CONTINUE_SELL" # go back DOWN
        else:
            return "REAL_REVERSE_BUY" # real reversal UP
    return None

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35; p22=pl+pr*0.22
    if pc>=p58 and cc>=p35 and cl>=p22 and cc>co: return "BOS_UP_STRONG"
    if pc<=p35 and cc<=p58 and ch<=pl+pr*0.78 and cc<co: return "BOS_DOWN_STRONG"
    if pc>po and (ph-max(pc,po))>abs(pc-po)*1.2 and cc<pl+pr*0.78: return "WEAK_BULL_TRAP"
    if pc<po and (min(pc,po)-pl)>abs(pc-po)*1.2 and cc>pl+pr*0.22: return "WEAK_BEAR_TRAP"
    return None

def get_1h_structure(d60):
    h,l,c=d60["h"],d60["l"],d60["c"]
    if len(c)<50: return "none","none"
    up=sum(1 for i in range(-20,-1) if c[i]>c[i-1])
    trend="UP" if up>=13 else "DOWN" if up<=7 else "RANGE"
    last_high=max(h[-20:-1]); last_low=min(l[-20:-1])
    breaks="BOS_UP" if c[-1]>last_high else "BOS_DOWN" if c[-1]<last_low else "none"
    return trend,breaks

def is_fake_pump_body(h,l,c,o,is_buy):
    if len(c)<3: return True
    ph,pl=h[-2],l[-2]; pr=ph-pl or 1; p35=pl+pr*0.35; p58=pl+pr*0.58
    ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]; body=abs(cc-co); rng=ch-cl or 1
    if body/rng < 0.30: return True
    if is_buy and cc < p35: return True
    if not is_buy and cc > p58: return True
    return False

def get_perfect_entry(c,h,l,o):
    ph,pl=h[-2],l[-2]; pr=ph-pl or 1
    ob_56 = pl+pr*0.56; ob_50 = pl+pr*0.50
    return ob_56, ob_50, ph, pl

def calc_sl_tp_live(c, tp_config, is_buy, sl, entry):
    # your existing calc
    if is_buy:
        sl_price=entry*(1-sl); tp1=entry*(1+tp_config["tp1"]); tp2=entry*(1+tp_config["tp2"]); tp3=entry*(1+tp_config["tp3"]); tp4=entry*(1+tp_config["tp4"])
    else:
        sl_price=entry*(1+sl); tp1=entry*(1-tp_config["tp1"]); tp2=entry*(1-tp_config["tp2"]); tp3=entry*(1-tp_config["tp3"]); tp4=entry*(1-tp_config["tp4"])
    return sl_price,tp1,tp2,tp3,tp4

def full_scan():
    for s in SYMBOLS:
        perp=SYMBOL_MAP[s]
        d60=kl(perp,"Min60"); d5=kl(perp,"Min15")
        d240=kl(perp,"Min240")
        if not d60 or not d5 or not d240: continue
        bias_4h,crt_low,crt_high=get_4h_bias(d240)
        trend_1h,breaks_1h=get_1h_structure(d60)
        fbs=fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: continue
        is_buy = "UP" in fbs or "BULL" in str(fbs)
        if "DOWN" in fbs or "BEAR" in str(fbs): is_buy=False

        # === BOTH WAYS GRAB OVERRIDE ===
        grab = is_liquidity_grab(d5["h"],d5["l"],d5["c"],d5["o"], crt_low, crt_high)
        ob_56,_,_,_=get_perfect_entry(d5["c"],d5["h"],d5["l"],d5["o"])
        if grab:
            confirm = confirm_grab_both_ways(d5["h"],d5["l"],d5["c"],d5["o"], grab, ob_56)
            if confirm=="FAKE_CONTINUE_BUY":
                is_buy=True; fbs=f"GRAB_FAKE_CONTINUE_BUY ({grab})"
            elif confirm=="FAKE_CONTINUE_SELL":
                is_buy=False; fbs=f"GRAB_FAKE_CONTINUE_SELL ({grab})"
            elif confirm=="REAL_REVERSE_SELL":
                is_buy=False; fbs=f"GRAB_REAL_SELL ({grab})"
            elif confirm=="REAL_REVERSE_BUY":
                is_buy=True; fbs=f"GRAB_REAL_BUY ({grab})"
            # grab overrides body fake check
            is_fake=False
        else:
            is_fake=is_fake_pump_body(d5["h"],d5["l"],d5["c"],d5["o"], is_buy)
            if is_fake: continue

        # trend filter but allow real reversal
        if trend_1h=="UP" and not is_buy and "REAL" not in str(fbs): continue
        if trend_1h=="DOWN" and is_buy and "REAL" not in str(fbs): continue

        # === ENTRY ===
        entry,_,_,_=get_perfect_entry(d5["c"],d5["h"],d5["l"],d5["o"])
        cfg=PER_COIN_TP[s]
        sl,tp1,tp2,tp3,tp4=calc_sl_tp_live(d5["c"],cfg,is_buy,cfg["sl"],entry)
        side="🟢 BUY" if is_buy else "🔴 SELL"
        tg(f"{side} {s} {fbs}\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f}/{tp2:.5f} | {get_time_12hr()} | 4H {bias_4h} 1H {trend_1h}")

if __name__=="__main__":
    while True:
        try: full_scan()
        except Exception as e: print(e)
        time.sleep(60)
