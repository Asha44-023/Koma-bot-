import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {
    "GRASSUSDT": "GRASS_USDT",
    "TAOUSDT" : "TAO_USDT",
    "SANDUSDT" : "SAND_USDT",
    "SENTUSDT" : "SENT_USDT",
    "FARTCOINUSDT": "FARTCOIN_USDT",
    "JASMYUSDT": "JASMY_USDT",
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

STATS = {"touched":0,"almost":0,"sniper":0,"xxx":0}

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

ACTIVE = {}

def in_killzone():
    return True # ALWAYS ACTIVE - market builds momentum then BOOM

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

def detect_xxx_sweep(lows, current_low):
    if len(lows)<2: return False
    l1=lows[-2][1]; l2=lows[-1][1]
    equal = abs(l1-l2)/l1 < 0.0015
    swept = current_low < min(l1,l2)*0.998
    return equal and swept

def detect_xxx_sweep_high(highs, current_high):
    if len(highs)<2: return False
    h1=highs[-2][1]; h2=highs[-1][1]
    equal = abs(h1-h2)/h1 < 0.0015
    swept = current_high > max(h1,h2)*1.002
    return equal and swept

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

def get_fvgs(h, l, lookback=50):
    fvgs = []
    for i in range(max(2, len(h)-lookback), len(h)-1):
        if l[i] > h[i-2]: fvgs.append(('bull', h[i-2], l[i]))
        if h[i] < l[i-2]: fvgs.append(('bear', l[i-2], h[i]))
    return fvgs

def get_last_ob(o,h,l,c, bullish=True, lookback=20):
    atr = sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2, len(c)-lookback, -1):
        body = c[i+1]-o[i+1]
        is_impulse = body > atr*0.5 if atr else body > 0
        if bullish:
            if c[i] < o[i] and is_impulse and c[i+1] > o[i+1]: return (l[i], h[i])
        else:
            if c[i] > o[i] and is_impulse and c[i+1] < o[i+1]: return (l[i], h[i])
    return None

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

def detect_strong_candles(o,h,l,c):
    if len(c)<3: return {"buy":False,"sell":False,"name":"none","is_harami":False}
    prev_o, prev_h, prev_l, prev_c = o[-2], h[-2], l[-2], c[-2]
    cur_o, cur_h, cur_l, cur_c = o[-1], h[-1], l[-1], c[-1]
    c1_o,c1_h,c1_l,c1_c = o[-3], h[-3], l[-3], c[-3]
    body_cur = abs(cur_c - cur_o) + 1e-9
    body_prev = abs(prev_c - prev_o) + 1e-9
    bullish_engulfing = prev_c < prev_o and cur_c > cur_o and cur_o < prev_c and cur_c > prev_o and body_cur > body_prev*1.1
    morning_star = c1_c < c1_o and abs(prev_c-prev_o) < (c1_h-c1_l)*0.3 and cur_c > cur_o and cur_c > (c1_o+c1_c)/2
    bullish_harami = prev_c < prev_o and cur_c > cur_o and cur_o > prev_c and cur_c < prev_o and body_cur < body_prev*0.6
    bearish_engulfing = prev_c > prev_o and cur_c < cur_o and cur_o > prev_c and cur_c < prev_o and body_cur > body_prev*1.1
    evening_star = c1_c > c1_o and abs(prev_c-prev_o) < (c1_h-c1_l)*0.3 and cur_c < cur_o and cur_c < (c1_o+c1_c)/2
    bearish_harami = prev_c > prev_o and cur_c < cur_o and cur_o < prev_c and cur_c > prev_o and body_cur < body_prev*0.6
    buy = bullish_engulfing or morning_star or bullish_harami
    sell = bearish_engulfing or evening_star or bearish_harami
    name = "BULL_HARAMI" if bullish_harami else "BULLISH_ENGULFING" if bullish_engulfing else "MORNING_STAR" if morning_star else "BEAR_HARAMI" if bearish_harami else "BEARISH_ENGULFING" if bearish_engulfing else "EVENING_STAR" if evening_star else "none"
    is_harami = bullish_harami or bearish_harami
    return {"buy":buy,"sell":sell,"name":name,"is_harami":is_harami}

def market_state(c, vp):
    e20=ema(c,20)
    price=c[-1]
    rng=max(c[-10:])-min(c[-10:])
    atr=statistics.mean([abs(c[i]-c[i-1]) for i in range(-14,0)]) or 1e-9
    consolidating = rng < atr*3
    if consolidating and vp["vol_x"]<1.5: return "CONSOLIDATING"
    if price>e20 and vp["buy_pct"]>60 and vp["vol_x"]>1.1: return "PUMPING"
    if price<e20 and vp["sell_pct"]>60 and vp["vol_x"]>1.1: return "DUMPING"
    return "TRENDING"

def get_bsl_ssl_auto(h, l, c, is_buy):
    highs, lows = swing_points(h, l, look=2)
    price = c[-1]
    if is_buy:
        above = [x[1] for x in highs if x[1] > price*1.0005]
        if not above: above = [max(h[-20:])]
        above = sorted(set(above))
        bsl1 = above[0]
        bsl2 = above[1] if len(above) > 1 else above[0]*1.008
        return bsl1*0.999, bsl2*0.998
    else:
        below = [x[1] for x in lows if x[1] < price*0.9995]
        if not below: below = [min(l[-20:])]
        below = sorted(set(below), reverse=True)
        ssl1 = below[0]
        ssl2 = below[1] if len(below) > 1 else below[0]*0.992
        return ssl1*1.001, ssl2*1.002

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15"); h1=kl(p,"Min60")
    if not d5 or not d15 or not h1: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30 or len(d15["c"])<50 or len(h1["c"])<50: return
    price=c[-1]

    dir1h = 1 if h1["c"][-1] > ema(h1["c"],50) else -1
    dir15 = 1 if d15["c"][-1] > ema(d15["c"],50) else -1
    if dir1h!= dir15: return
    is_buy = dir1h==1

    h1_highs, h1_lows = swing_points(h1["h"], h1["l"])
    if len(h1_highs) >= 2 and len(h1_lows) >= 2:
        if is_buy and h1_highs[-1][1] < h1_highs[-2][1]: return
        if not is_buy and h1_lows[-1][1] > h1_lows[-2][1]: return

    bos = detect_bos(d5["h"], d5["l"], d5["c"]) or detect_bos(d15["h"], d15["l"], d15["c"])
    pat = pattern(d5["h"], d5["l"])
    if pat=="none": pat = pattern(d15["h"], d15["l"])

    highs_5, lows_5 = swing_points(d5["h"], d5["l"])
    sweep_low = detect_xxx_sweep(lows_5, l[-1]) if lows_5 else False
    sweep_high = detect_xxx_sweep_high(highs_5, h[-1]) if highs_5 else False
    if sweep_low or sweep_high: STATS["xxx"]+=1

    bull_pats = ["double_bottom", "triple_bottom"]
    bear_pats = ["double_top", "triple_top"]
    valid_bos = (is_buy and bos == "BOS_UP") or (not is_buy and bos == "BOS_DOWN")
    valid_pat = (is_buy and pat in bull_pats) or (not is_buy and pat in bear_pats)
    if not (valid_bos or valid_pat): return

    vp5 = volume_pressure(o,h,l,c,v)
    vp15 = volume_pressure(d15["o"],d15["h"],d15["l"],d15["c"],d15["v"])
    vp = vp5 if vp5["vol_x"]>=vp15["vol_x"] else vp15
    state = market_state(c, vp)

    fvgs_1h = get_fvgs(h1["h"], h1["l"])
    has_bull_fvg = any(f[0]=='bull' for f in fvgs_1h[-5:])
    has_bear_fvg = any(f[0]=='bear' for f in fvgs_1h[-5:])
    ob = get_last_ob(o,h,l,c, bullish=is_buy)
    if not ob: return
    if is_buy and not has_bull_fvg: return
    if not is_buy and not has_bear_fvg: return

    ob_low, ob_high = ob
    if ob_low*0.99 <= price <= ob_high*1.01:
        STATS["touched"]+=1
        print(f"EYE {s} TOUCHED OB {ob} BOS:{bos} Sweep:{sweep_low if is_buy else sweep_high} | T:{STATS['touched']} X:{STATS['xxx']} A:{STATS['almost']} S:{STATS['sniper']}", flush=True)

    if is_buy:
        if price > ob_high * 1.008: return
        if price < ob_low * 0.99: return
    else:
        if price < ob_low * 0.992: return
        if price > ob_high * 1.01: return

    e20_5m = ema(c, 20)
    dist = (price - e20_5m) / e20_5m * 100 if e20_5m else 0
    if is_buy and dist > 1.5: return
    if not is_buy and dist < -1.5: return

    candles = detect_strong_candles(o,h,l,c)
    if is_buy and not candles["buy"]:
        if ob_low*0.99 <= price <= ob_high*1.01: STATS["almost"]+=1
        return
    if not is_buy and not candles["sell"]:
        if ob_low*0.99 <= price <= ob_high*1.01: STATS["almost"]+=1
        return

    if candles["is_harami"]:
        if is_buy and not sweep_low:
            print(f"FILTERED {s} Bull Harami but no XXX sweep", flush=True)
            STATS["almost"]+=1; return
        if not is_buy and not sweep_high:
            print(f"FILTERED {s} Bear Harami but no XXX sweep", flush=True)
            STATS["almost"]+=1; return

    if is_buy and vp["buy_pct"]<55: return
    if not is_buy and vp["sell_pct"]<55: return
    if vp["vol_x"]<1.1:
        print(f"quiet {s} {vp['vol_x']:.2f}x {state}", flush=True)
        return

    now=time.time(); prev=COOLDOWN["signals"].get(s,{})
    if now-prev.get("t",0)<60*60 and prev.get("dir")==is_buy: return

    trs=[max(h[i]-l[i], abs(h[i]-c[i-1])) for i in range(-14,0)]
    atr=sum(trs)/len(trs) if trs else price*0.01
    risk=min(atr*1.5, price*0.03)
    sl=price-risk if is_buy else price+risk

    auto_tp1, auto_tp2 = get_bsl_ssl_auto(d5["h"], d5["l"], d5["c"], is_buy)
    rr1 = abs(auto_tp1 - price) / (risk or 1e-9)
    if 0.8 <= rr1 <= 4.0:
        tp1, tp2 = auto_tp1, auto_tp2
        tp_src = f"BSL/SSL {rr1:.2f}R"
    else:
        tp1=price+risk*1.5 if is_buy else price-risk*1.5
        tp2=price+risk*2 if is_buy else price-risk*2
        tp_src = f"FIXED {rr1:.2f}R"

    COOLDOWN["signals"][s]={"t":now,"dir":is_buy}; save()
    ACTIVE[s]={"entry":price,"is_buy":is_buy,"t":now,"atr":atr,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl}
    STATS["sniper"]+=1
    nai=datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
    sweep_txt = f"XXX SWEEP {lows_5[-2:]}" if is_buy else f"XXX SWEEP {highs_5[-2:]}"
    tg(f"{'🟢' if is_buy else '🔴'} <b>{s} {'BUY DIP' if is_buy else 'SELL TOP'} SNIPER V25 ALWAYS-ON</b> [{state}]\n"
       f"{bos or ''} {pat} + {candles['name']}\n{sweep_txt}\n"
       f"Vol {vp['vol_x']:.2f}x Buy {vp['buy_pct']:.0f}% Sell {vp['sell_pct']:.0f}%\n"
       f"OB {ob_low:.4f}-{ob_high:.4f} Price: {price}\n"
       f"SL:{sl:.6f} TP1:{tp1:.6f} TP2:{tp2:.6f} [{tp_src}]\n"
       f"[{nai}] | T:{STATS['touched']} X:{STATS['xxx']} A:{STATS['almost']} S:{STATS['sniper']}")

def check_exits():
    now=time.time()
    for s in list(ACTIVE.keys()):
        pos=ACTIVE[s]
        p=pos.get("perp", SYMBOL_MAP.get(s, s))
        d=kl(p,"Min1")
        if not d: continue
        cur=d["c"][-1]
        entry=pos["entry"]; is_buy=pos["is_buy"]
        sl=pos.get("sl", entry*0.99 if is_buy else entry*1.01)
        tp1=pos.get("tp1", entry*1.01)
        tp2=pos.get("tp2", entry*1.015)
        if is_buy:
            if cur>=tp2: tg(f"🎯 TP2 HIT {s} BSL"); ACTIVE.pop(s); continue
            if cur>=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 TP1 HIT {s} BSL -> SL BE")
            if cur<=sl: tg(f"🛑 SL HIT {s}"); ACTIVE.pop(s); continue
        else:
            if cur<=tp2: tg(f"🎯 TP2 HIT {s} SSL"); ACTIVE.pop(s); continue
            if cur<=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 TP1 HIT {s} SSL -> SL BE")
            if cur>=sl: tg(f"🛑 SL HIT {s}"); ACTIVE.pop(s); continue
        if now-pos["t"]>15*60:
            tg(f"⏰ TIMEOUT {s}"); ACTIVE.pop(s)

print("=== BOT V25 ALWAYS-ON OB-TO-OB SNIPER - HARAMI+XXX+ BSL AUTO ===", flush=True)
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
