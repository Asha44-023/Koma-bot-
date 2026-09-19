import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {
    "GRASSUSDT": "GRASS_USDT",
    "VELVETUSDT": "VELVET_USDT",
    "HEIUSDT": "HEI_USDT",
    "SENTUSDT": "SENT_USDT",
    "SIRENUSDT": "SIREN_USDT",
    "LABUSDT": "LAB_USDT",
    "KOMAUSDT": "KOMA_USDT",
}
SYMBOLS = list(SYMBOL_MAP.keys())
PERPS = list(SYMBOL_MAP.values())

COOLDOWN_FILE="cooldown.json"
COOLDOWN={"signals":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: pass
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

ACTIVE = {}

def kl(sym, interval):
    try:
        r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}",
            params={"interval":interval}, timeout=10).json()
        data=r.get("data", [])
        if not data: return None
        if isinstance(data, dict):
            def f(x):
                try: return float(x)
                except: return 0.0
            return {
                "o": [f(x) for x in data.get("open",[])],
                "h": [f(x) for x in data.get("high",[])],
                "l": [f(x) for x in data.get("low",[])],
                "c": [f(x) for x in data.get("close",[])],
                "v": [f(x) for x in data.get("vol",[])]
            }
        o,h,l,c,v=[],[],[],[],[]
        for k in data:
            o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
        return {"o":o,"h":h,"l":l,"c":c,"v":v}
    except Exception as e:
        print(f"kl err {sym} {e}", flush=True); return None

def ema(vals, n):
    if not vals: return 0
    k=2/(n+1); e=vals[0]
    for v in vals[1:]: e=v*k+e*(1-k)
    return e

def swing_points(h,l, look=3):
    highs=[]; lows=[]
    n=len(h)
    for i in range(look, n-look):
        if all(h[i]>=h[j] for j in range(i-look,i+look+1) if j!=i): highs.append((i,h[i]))
        if all(l[i]<=l[j] for j in range(i-look,i+look+1) if j!=i): lows.append((i,l[i]))
    return highs, lows

def detect_bos(h,l,c):
    highs,lows=swing_points(h,l)
    if len(highs)<2 or len(lows)<2: return None
    last_h=highs[-1][1]; prev_h=highs[-2][1]
    last_l=lows[-1][1]; prev_l=lows[-2][1]
    price=c[-1]
    if price>last_h and last_h>prev_h: return "BOS_UP"
    if price<last_l and last_l<prev_l: return "BOS_DOWN"
    return None

def pattern(h,l):
    tops=[];bots=[]
    for i in range(2,len(h)-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: bots.append(l[i])
    tops=tops[-3:];bots=bots[-3:]
    if len(tops)>=3 and max(tops)-min(tops)<sum(tops)/3*0.008: return "triple_top"
    if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.008: return "double_top"
    if len(bots)>=3 and max(bots)-min(bots)<sum(bots)/3*0.008: return "triple_bottom"
    if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.008: return "double_bottom"
    return "none"

def volume_pressure(o,h,l,c,v, n=20):
    if len(v)<n: return {"vol_x":1,"buy_pct":50,"sell_pct":50}
    avg=statistics.mean(v[-n:])
    cur=v[-1]
    bp=sp=0
    for i in range(-n,0):
        rng=h[i]-l[i] or 1e-9
        delta=(c[i]-o[i])/rng * v[i]
        if delta>0: bp+=delta
        else: sp+=-delta
    total=bp+sp or 1
    return {"vol_x":cur/(avg or 1), "buy_pct":bp/total*100, "sell_pct":sp/total*100}

def detect_liquidity_grab(o,h,l,c,v):
    if len(c)<25: return None
    avg=statistics.mean(v[-20:])
    k_idx=-2
    body=abs(c[k_idx]-o[k_idx])+1e-9
    rng=h[k_idx]-l[k_idx] or 1e-9
    uw=h[k_idx]-max(o[k_idx],c[k_idx])
    lw=min(o[k_idx],c[k_idx])-l[k_idx]
    vol_x=v[k_idx]/(avg or 1)
    if lw>body*2 and lw>rng*0.6 and vol_x>2.5 and c[k_idx]>o[k_idx]:
        return f"LIQUIDITY GRAB DOWN {vol_x:.1f}x - bear trap"
    if uw>body*2 and uw>rng*0.6 and vol_x>2.5 and c[k_idx]<o[k_idx]:
        return f"LIQUIDITY GRAB UP {vol_x:.1f}x - bull trap"
    return None

def detect_whale(o,h,l,c,v):
    if len(c)<25: return None
    avg=statistics.mean(v[-20:])
    atr=statistics.mean([h[i]-l[i] for i in range(-14,0)])
    rng=h[-1]-l[-1]
    vol_x=v[-1]/(avg or 1)
    rp=(c[-1]-o[-1])/(rng or 1e-9)
    if vol_x>4 and rng>atr*2:
        if rp>0.5: return f"WHALE BUY {vol_x:.1f}x - manipulation up"
        if rp<-0.5: return f"WHALE SELL {vol_x:.1f}x - manipulation down"
    if vol_x>3 and rng<atr*0.7:
        return f"ABSORPTION {vol_x:.1f}x - big move coming"
    return None

def market_state(c, vp):
    e20=ema(c,20)
    price=c[-1]
    rng=max(c[-10:])-min(c[-10:])
    atr=statistics.mean([abs(c[i]-c[i-1]) for i in range(-14,0)]) or 1e-9
    consolidating = rng < atr*3
    if consolidating and vp["vol_x"]<1.5:
        return "CONSOLIDATING JUNCTION"
    if price>e20 and vp["buy_pct"]>60 and vp["vol_x"]>1.5:
        return "PUMPING - high volume buying pressure"
    if price<e20 and vp["sell_pct"]>60 and vp["vol_x"]>1.5:
        return "DUMPING - high volume selling pressure"
    return "TREND CONTINUING"

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15"); h1=kl(p,"Min60")
    if not d5 or not d15 or not h1: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30 or len(d15["c"])<50 or len(h1["c"])<50: return
    price=c[-1]

    dir1h = 1 if h1["c"][-1] > ema(h1["c"],50) else -1
    dir15 = 1 if d15["c"][-1] > ema(d15["c"],50) else -1
    if dir1h!= dir15:
        return
    is_buy = dir1h==1

    bos = detect_bos(d5["h"], d5["l"], d5["c"]) or detect_bos(d15["h"], d15["l"], d15["c"])
    pat = pattern(d5["h"], d5["l"])
    if pat=="none": pat = pattern(d15["h"], d15["l"])

    vp5 = volume_pressure(o,h,l,c,v)
    vp15 = volume_pressure(d15["o"],d15["h"],d15["l"],d15["c"],d15["v"])
    vp = vp5 if vp5["vol_x"]>=vp15["vol_x"] else vp15
    state = market_state(c, vp)

    liq = detect_liquidity_grab(o,h,l,c,v)
    whale = detect_whale(o,h,l,c,v)
    if liq or whale:
        tg(f"🐋 <b>{s}</b>\n{liq or ''}\n{whale or ''}\nPrice: {price}")

    if not (bos or pat!="none"): return
    if is_buy and vp["buy_pct"]<55: return
    if not is_buy and vp["sell_pct"]<55: return

    if vp["vol_x"]<1.2:
        print(f"quiet {s} {vp['vol_x']:.2f}x {state}", flush=True)
        return

    now=time.time(); prev=COOLDOWN["signals"].get(s,{})
    if now-prev.get("t",0)<30*60 and prev.get("dir")==is_buy: return

    trs=[max(h[i]-l[i], abs(h[i]-c[i-1])) for i in range(-14,0)]
    atr=sum(trs)/len(trs) if trs else price*0.01
    risk=min(atr*1.5, price*0.03)
    sl=price-risk if is_buy else price+risk
    tp1=price+risk*1.5 if is_buy else price-risk*1.5
    tp2=price+risk*2 if is_buy else price-risk*2

    COOLDOWN["signals"][s]={"t":now,"dir":is_buy}; save()
    ACTIVE[s]={"entry":price,"is_buy":is_buy,"t":now,"atr":atr,"perp":p}
    nai=datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
    tg(f"{'🟢' if is_buy else '🔴'} <b>{s} {'BUY' if is_buy else 'SELL'}</b> [{state}]\n"
       f"Structure: {bos or ''} {pat}\n"
       f"15m/1h: {'UP' if is_buy else 'DOWN'}\n"
       f"Price: {price} Vol: {vp['vol_x']:.2f}x Buy {vp['buy_pct']:.0f}% Sell {vp['sell_pct']:.0f}%\n"
       f"SL:{sl:.6f} TP1:{tp1:.6f} TP2:{tp2:.6f}\n[{nai}]")

def check_exits():
    now=time.time()
    for s in list(ACTIVE.keys()):
        pos=ACTIVE[s]
        p=pos.get("perp", SYMBOL_MAP.get(s, s))
        d=kl(p,"Min1")
        if not d: continue
        cur=d["c"][-1]; atr=pos["atr"]; entry=pos["entry"]; is_buy=pos["is_buy"]
        risk=atr*1.5
        tp1=entry+risk*1.5 if is_buy else entry-risk*1.5
        tp2=entry+risk*2 if is_buy else entry-risk*2
        sl=entry-risk if is_buy else entry+risk
        if is_buy:
            if cur>=tp2: tg(f"🎯 TP2 HIT {s}"); ACTIVE.pop(s); continue
            if cur>=tp1 and not pos.get("tp1"): pos["tp1"]=True; tg(f"🎯 TP1 HIT {s} -> move SL to BE")
            if cur<=sl: tg(f"🛑 SL HIT {s}"); ACTIVE.pop(s); continue
        else:
            if cur<=tp2: tg(f"🎯 TP2 HIT {s}"); ACTIVE.pop(s); continue
            if cur<=tp1 and not pos.get("tp1"): pos["tp1"]=True; tg(f"🎯 TP1 HIT {s} -> move SL to BE")
            if cur>=sl: tg(f"🛑 SL HIT {s}"); ACTIVE.pop(s); continue
        if now-pos["t"]>15*60:
            tg(f"⏰ TIMEOUT {s}"); ACTIVE.pop(s)

print("=== BOT V20.2 - 15m+1h QUIET ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS, PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS, PERPS):
            try: full_scan(s,p)
            except: pass
        check_exits()
        time.sleep(60)
