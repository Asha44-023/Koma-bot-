# BOT V43 FULL - 4H -> 1H OB/FVG/LIQ -> 15M 58/35 BOS - NO SPAM
import time, json, os, requests, fcntl, sys
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
    try:
        token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
    except: pass

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

# --- 4H BIAS (Direction + Supply/Demand) ---
def get_bias_4h(d):
    if len(d["c"])<50: return "RANGE",""
    LOOKBACK=48
    lo=min(d["l"][-LOOKBACK:]); hi=max(d["h"][-LOOKBACK:]); mid=(lo+hi)/2; ema=sum(d["c"][-50:])/50
    if d["c"][-1]>mid and d["c"][-1]>ema: return "BULL",f"Above 4H SD mid+EMA"
    if d["c"][-1]<mid and d["c"][-1]<ema: return "BEAR",f"Below 4H SD mid+EMA"
    return "RANGE","4H Range"

# --- 1H SMC: OB, FVG, Liquidity ---
def detect_fvg_1h(d):
    # FVG: gap between candle 3 high/low and candle 1 low/high
    bull_fvg=False; bear_fvg=False
    if len(d["c"])<10: return False,False
    for i in range(-10,-2):
        if d["l"][i] > d["h"][i-2]: bull_fvg=True
        if d["h"][i] < d["l"][i-2]: bear_fvg=True
    return bull_fvg, bear_fvg

def detect_ob_1h(d):
    # OB: last opposite color before strong move
    bull_ob=False; bear_ob=False
    if len(d["c"])<10: return False,False
    # bullish OB = bearish candle then strong bullish close above its high
    for i in range(-6,-1):
        body = abs(d["c"][i]-d["o"][i]); rng = d["h"][i]-d["l"][i] or 1
        if d["c"][i] < d["o"][i] and d["c"][-1] > d["h"][i] and body/rng>0.4:
            bull_ob=True
        if d["c"][i] > d["o"][i] and d["c"][-1] < d["l"][i] and body/rng>0.4:
            bear_ob=True
    return bull_ob, bear_ob

def detect_liquidity_1h(d):
    # Liquidity sweep: took recent high/low then closed back
    bull_liq=False; bear_liq=False
    if len(d["c"])<20: return False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2])
    if d["h"][-2] > recent_high and d["c"][-1] < recent_high: bear_liq=True # sweep highs = bearish reversal liquidity
    if d["l"][-2] < recent_low and d["c"][-1] > recent_low: bull_liq=True # sweep lows = bullish
    return bull_liq, bear_liq

def check_1h_confluence(d1, is_buy):
    bull_fvg, bear_fvg = detect_fvg_1h(d1)
    bull_ob, bear_ob = detect_ob_1h(d1)
    bull_liq, bear_liq = detect_liquidity_1h(d1)

    if is_buy:
        # For BUY need at least 2 of 3: bullish FVG, bullish OB, bullish LIQ sweep
        score = int(bull_fvg) + int(bull_ob) + int(bull_liq)
        reason = f"FVG:{bull_fvg} OB:{bull_ob} LIQ:{bull_liq}"
        return score>=1, reason # 1 confluence enough to not be too strict
    else:
        score = int(bear_fvg) + int(bear_ob) + int(bear_liq)
        reason = f"FVG:{bear_fvg} OB:{bear_ob} LIQ:{bear_liq}"
        return score>=1, reason

# --- 15M FBS BOS 58/35 (Image 2) ---
def fbs_logic(h,l,c,o):
    if len(c)<3: return None,None,None
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; cc=c[-1]; co=o[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35
    # STRONG BREAKOUT from image: close above 38% = BOS
    if pc>=p58 and cc>=p35 and cc>co: return "BOS_UP",True,f"Prev>58%({pc:.4f}>={p58:.4f}) Curr>35%({cc:.4f}>={p35:.4f})"
    if pc<=p35 and cc<=p58 and cc<co: return "BOS_DOWN",False,f"Prev<35%({pc:.4f}<={p35:.4f}) Curr<58%({cc:.4f}<={p58:.4f})"
    return None,None,None

def is_close(d5,is_buy):
    if len(d5["c"])<4: return False,""
    ph,pl=d5["h"][-2],d5["l"][-2]; pr=ph-pl or 1
    p58=pl+pr*0.58; p35=pl+pr*0.35; cc=d5["c"][-1]
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

        d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d5: continue

        # 4H BIAS
        bias, bias_reason = get_bias_4h(d240)
        if bias=="RANGE": continue

        # 15M BOS
        fbs,is_buy, fbs_reason = fbs_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue

        # 1H CONFIRMATION - OB/FVG/Liquidity (NEW!)
        ok_1h, smc_reason = check_1h_confluence(d60, is_buy)
        if not ok_1h: continue

        entry=d5["l"][-2]+(d5["h"][-2]-d5["l"][-2])*0.56
        cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        tp1=entry*(1+cfg["tp1"]) if is_buy else entry*(1-cfg["tp1"])
        side="🟢 BUY" if is_buy else "🔴 SELL"
        tg(f"{side} {s} {fbs}\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f}\n4H:{bias} {bias_reason}\n1H SMC:{smc_reason}\n15M:{fbs_reason}\n{get_time()}")

        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()

if __name__=="__main__":
    fp=open(LOCK_FILE,"w")
    try: fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except:
        if "--once" not in sys.argv:
            print("Bot already running"); exit(1)
    # NO SPAM HEARTBEAT - only print
    print(f"🚀 BOT V43 FULL 4H->1H->15M | {get_time()}", flush=True)
    if "--once" in sys.argv:
        try: scan()
        except Exception as e: print(e)
        exit(0)
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(60)
