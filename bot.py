# V28.5 FINAL QUALITY - FIXED WHALE DIRECTION + ANTI-SPAM
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {"GRASSUSDT":"GRASS_USDT","TAOUSDT":"TAO_USDT","SANDUSDT":"SAND_USDT","SENTUSDT":"SENT_USDT","FARTCOINUSDT":"FARTCOIN_USDT","JASMYUSDT":"JASMY_USDT","KOMAUSDT":"KOMA_USDT",}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
COOLDOWN_FILE="cooldown.json"; COOLDOWN={"signals":{}}
if os.path.exists(COOLDOWN_FILE):
    try:
        d=json.load(open(COOLDOWN_FILE))
        if d.get("signals"):
            k=list(d["signals"].keys())[0]
            if "_" not in k: d={"signals":{}}
        COOLDOWN=d
    except: COOLDOWN={"signals":{}}

def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
STATS={"touched":0,"sniper":0,"xxx":0}
WHALE_TRACKER={}; VOL_HISTORY={}
LAST_SIGNAL_TIME={}

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

ACTIVE={}
COOLDOWN_NORMAL=30*60
COOLDOWN_AFTER_SL=45*60
COOLDOWN_WHALE_FLASH=3*60

def get_session():
    h=datetime.now(ZoneInfo("UTC")).hour
    if 0<=h<7: return "ASIAN","🟡"
    if 7<=h<12: return "LONDON","🔵"
    if 12<=h<21: return "NY","🟢"
    return "OFF","⚫"

def kl(sym,interval):
    try:
        r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}", params={"interval":interval}, timeout=10).json()
        data=r.get("data",[]);
        if not data: return None
        if isinstance(data,dict):
            def f(x):
                try: return float(x)
                except: return 0.0
            return {"o":[f(x) for x in data.get("open",[])], "h":[f(x) for x in data.get("high",[])], "l":[f(x) for x in data.get("low",[])], "c":[f(x) for x in data.get("close",[])], "v":[f(x) for x in data.get("vol",[])]}
        o,h,l,c,v=[],[],[],[],[]
        for k in data: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
        return {"o":o,"h":h,"l":l,"c":c,"v":v}
    except: return None

def ema(v,n):
    if not v: return 0
    k=2/(n+1); e=v[0]
    for x in v[1:]: e=x*k+e*(1-k)
    return e

def swing_points(h,l,look=3):
    highs=[]; lows=[]; n=len(h)
    for i in range(look,n-look):
        if all(h[i]>=h[j] for j in range(i-look,i+look+1) if j!=i): highs.append((i,h[i]))
        if all(l[i]<=l[j] for j in range(i-look,i+look+1) if j!=i): lows.append((i,l[i]))
    return highs,lows

def detect_bos(h,l,c):
    highs,lows=swing_points(h,l)
    if len(highs)<2 or len(lows)<2: return None
    price=c[-1]
    if price>highs[-1][1] and highs[-1][1]>highs[-2][1]: return "BOS_UP"
    if price<lows[-1][1] and lows[-1][1]<lows[-2][1]: return "BOS_DOWN"
    return None

def detect_out_in(o,h,l,c,side):
    if len(c)<6: return False
    if side=="BUY": lvl=min(l[-6:-1]); return c[-2]<lvl*0.997 and c[-1]>lvl and c[-1]>o[-1]
    else: lvl=max(h[-6:-1]); return c[-2]>lvl*1.003 and c[-1]<lvl and c[-1]<o[-1]

def pattern(h,l):
    tops=[];bots=[]
    for i in range(2,len(h)-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: bots.append(l[i])
    tops=tops[-3:];bots=bots[-3:]
    if len(tops)>=3 and max(tops)-min(tops)<sum(tops)/3*0.015: return "triple_top"
    if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.015: return "double_top"
    if len(bots)>=3 and max(bots)-min(bots)<sum(bots)/3*0.015: return "triple_bottom"
    if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.015: return "double_bottom"
    return "none"

def get_last_ob(o,h,l,c,bullish=True,lookback=40):
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2, len(c)-lookback, -1):
        body=c[i+1]-o[i+1]; is_impulse=abs(body)>atr*0.3 if atr else True
        if bullish and c[i]<o[i] and is_impulse and c[i+1]>o[i+1]: return (l[i],h[i])
        if not bullish and c[i]>o[i] and is_impulse and c[i+1]<o[i+1]: return (l[i],h[i])
    return None

def volume_pressure(o,h,l,c,v,n=20):
    if len(v)<n: return {"vol_x":1,"buy_pct":50,"sell_pct":50}
    avg=statistics.mean(v[-n:]); cur=v[-1]; bp=sp=0
    for i in range(-n,0): rng=h[i]-l[i] or 1e-9; delta=(c[i]-o[i])/rng*v[i]; bp+=delta if delta>0 else 0; sp+=-delta if delta<0 else 0
    total=bp+sp or 1; return {"vol_x":cur/(avg or 1),"buy_pct":bp/total*100,"sell_pct":sp/total*100}

def get_wick_levels(h,l,lookback=20):
    return max(h[-lookback:]), min(l[-lookback:])

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy):
    ob_low, ob_high = ob
    ob_50 = (ob_low + ob_high)/2
    recent_high, recent_low = get_wick_levels(h,l,20)
    if is_buy:
        entry = ob_50
        sl = min(min(l[-7:]), ob_low) * 0.997
        tp1 = recent_high * 0.995
        tp2 = recent_high * 1.01
        tp3 = tp2 * 1.02
    else:
        entry = ob_50
        sl = max(max(h[-7:]), ob_high) * 1.003
        tp1 = recent_low * 1.005
        tp2 = recent_low * 0.99
        tp3 = tp2 * 0.98
    risk = abs(entry - sl); rr2 = abs(tp2 - entry)/(risk or 1e-9)
    return entry, sl, tp1, tp2, tp3, rr2

def get_volume_phase(p, vol_x, price):
    now=time.time()
    if vol_x >= 1.7:
        if p not in WHALE_TRACKER or "exit_time" in WHALE_TRACKER[p]:
            WHALE_TRACKER[p] = {"enter_time": now}
            return "WHALE_FLASH_ENTER", 0
        if now - WHALE_TRACKER[p]["enter_time"] <= 15*60:
            return "WHALE_FLASH_ACTIVE", now - WHALE_TRACKER[p]["enter_time"]
    if vol_x >= 1.0: return "BUILDING", 0
    return "WATCH", 0

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    price=c[-1]
    session_name,session_emoji=get_session()
    if session_name=="OFF": return
    if s in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[s] < 30*60: return

    bos=detect_bos(d5["h"],d5["l"],d5["c"]) or detect_bos(d15["h"],d15["l"],d15["c"])
    pat=pattern(d5["h"],d5["l"])
    if pat=="none": pat=pattern(d15["h"],d15["l"])
    vp=volume_pressure(o,h,l,c,v)
    phase, _ = get_volume_phase(p, vp["vol_x"], price)
    is_whale = "WHALE" in phase

    if vp["vol_x"] < 1.0 and not is_whale: return

    candidates = []
    for is_buy in [True, False]:
        side="BUY" if is_buy else "SELL"
        if is_buy and pat in ["double_top","triple_top"]: continue
        if not is_buy and pat in ["double_bottom","triple_bottom"]: continue
        if bos=="BOS_UP" and not is_buy: continue
        if bos=="BOS_DOWN" and is_buy: continue
        # FIXED: EVEN WHALE NEEDS CORRECT DOMINANCE
        if is_buy and vp["buy_pct"]<58: continue
        if not is_buy and vp["sell_pct"]<58: continue

        ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=40)
        if not ob: continue
        ob_low,ob_high=ob
        inside = ob_low*0.98 <= price <= ob_high*1.02
        if not inside and not is_whale: continue

        entry, sl, tp1, tp2, tp3, rr2 = get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy)
        if rr2<1.5 and not is_whale: continue
        if rr2<1.2 and is_whale: continue

        score = rr2 + (vp["buy_pct"] if is_buy else vp["sell_pct"])/100
        candidates.append((score, is_buy, side, ob, entry, sl, tp1, tp2, tp3, rr2))

    if not candidates: return
    candidates.sort(reverse=True, key=lambda x: x[0])
    score, is_buy, side, ob, entry, sl, tp1, tp2, tp3, rr2 = candidates[0]

    key=f"{s}_{side}"; now=time.time(); prev=COOLDOWN["signals"].get(key,{})
    cd_need=COOLDOWN_WHALE_FLASH if is_whale else COOLDOWN_NORMAL
    if prev.get("result")=="SL": cd_need=COOLDOWN_AFTER_SL
    if now-prev.get("t",0) < cd_need: return

    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"normal"}; save()
    LAST_SIGNAL_TIME[s]=now
    ACTIVE[s]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl,"side_key":key}
    STATS["sniper"]+=1

    emoji = "🟢" if is_buy else "🔴"
    phase_txt = f"⚡ WHALE {vp['vol_x']:.1f}x" if is_whale else f"🏗️ BUILD {vp['vol_x']:.1f}x"

    tg(
f"{emoji} <b>{s} {side}</b> {session_emoji} {session_name}\n"
f"{phase_txt} RR:{rr2:.1f}R\n"
f"Entry: {entry:.6f} (50% OB)\n"
f"SL: {sl:.6f}\n"
f"TP1: {tp1:.6f}\n"
f"TP2: {tp2:.6f}\n"
f"{pat} {bos or ''} | {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}%"
    )

print("=== BOT V28.5 FINAL FIXED ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"FINAL STATS SNIPER:{STATS['sniper']} ACTIVE:{list(ACTIVE.keys())}", flush=True)
