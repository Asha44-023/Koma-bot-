# V28.2 ULTRA LOOSE - FIXED SNIPER:0 - WICK TP/SL + BUILDING+WHALE+FOMO
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

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

ACTIVE={}; COOLDOWN_NORMAL=12*60; COOLDOWN_AFTER_SL=25*60; COOLDOWN_AFTER_TP2=5*60
COOLDOWN_BUILDING=12*60; COOLDOWN_WHALE_FLASH=2*60; COOLDOWN_RETAIL_FOMO=15*60

def get_session():
    h=datetime.now(ZoneInfo("UTC")).hour
    if 0<=h<7: return "ASIAN","🟡","BUILDING"
    if 7<=h<12: return "LONDON","🔵","FAKE SWEEP"
    if 12<=h<21: return "NY","🟢","REAL + FOMO"
    return "OFF","⚫","Off"

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
    if side=="BUY": lvl=min(l[-6:-1]); return c[-2]<lvl*0.997 and c[-1]>lvl and c[-1]>o[-1] and 0.1<=(lvl-min(l[-2],l[-3]))/lvl*100<=1.0
    else: lvl=max(h[-6:-1]); return c[-2]>lvl*1.003 and c[-1]<lvl and c[-1]<o[-1] and 0.1<=(max(h[-2],h[-3])-lvl)/lvl*100<=1.0

def detect_deep_WM(h,l,side):
    if len(h)<8: return False
    if side=="BUY": _,lows=swing_points(h,l,look=2); return len(lows)>=2 and lows[-1][1]<lows[-2][1] and (lows[-2][1]-lows[-1][1])/lows[-2][1]*100>=0.08
    else: highs,_=swing_points(h,l,look=2); return len(highs)>=2 and highs[-1][1]>highs[-2][1] and (highs[-1][1]-highs[-2][1])/highs[-2][1]*100>=0.08

def detect_xxx_sweep(lows,cur): return len(lows)>=2 and abs(lows[-2][1]-lows[-1][1])/lows[-2][1]<0.005 and cur<min(lows[-2][1],lows[-1][1])*0.996
def detect_xxx_sweep_high(highs,cur): return len(highs)>=2 and abs(highs[-2][1]-highs[-1][1])/highs[-2][1]<0.005 and cur>max(highs[-2][1],highs[-1][1])*1.004

def pattern(h,l):
    tops=[];bots=[]
    for i in range(2,len(h)-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: bots.append(l[i])
    tops=tops[-3:];bots=bots[-3:]
    if len(tops)>=3 and max(tops)-min(tops)<sum(tops)/3*0.018: return "triple_top"
    if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.018: return "double_top"
    if len(bots)>=3 and max(bots)-min(bots)<sum(bots)/3*0.018: return "triple_bottom"
    if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.018: return "double_bottom"
    return "none"

def get_last_ob(o,h,l,c,bullish=True,lookback=50):
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2, len(c)-lookback, -1):
        body=c[i+1]-o[i+1]; is_impulse=abs(body)>atr*0.25 if atr else True
        if bullish and c[i]<o[i] and is_impulse and c[i+1]>o[i+1]: return (l[i],h[i])
        if not bullish and c[i]>o[i] and is_impulse and c[i+1]<o[i+1]: return (l[i],h[i])
    return None

def volume_pressure(o,h,l,c,v,n=20):
    if len(v)<n: return {"vol_x":1,"buy_pct":50,"sell_pct":50}
    avg=statistics.mean(v[-n:]); cur=v[-1]; bp=sp=0
    for i in range(-n,0): rng=h[i]-l[i] or 1e-9; delta=(c[i]-o[i])/rng*v[i]; bp+=delta if delta>0 else 0; sp+=-delta if delta<0 else 0
    total=bp+sp or 1; return {"vol_x":cur/(avg or 1),"buy_pct":bp/total*100,"sell_pct":sp/total*100}

def detect_strong_candles(o,h,l,c):
    if len(c)<3: return {"buy":True,"sell":True,"name":"ANY"} # ULTRA LOOSE - allow all
    prev_o,prev_c=o[-2],c[-2]; cur_o,cur_c=o[-1],c[-1]; c1_o,c1_c=o[-3],c[-3]
    body_cur=abs(cur_c-cur_o)+1e-9; body_prev=abs(prev_c-prev_o)+1e-9
    bullish_engulfing=prev_c<prev_o and cur_c>cur_o and cur_c>prev_o and body_cur>body_prev*0.5
    bearish_engulfing=prev_c>prev_o and cur_c<cur_o and cur_c<prev_o and body_cur>body_prev*0.5
    buy=bullish_engulfing or (cur_c>cur_o); sell=bearish_engulfing or (cur_c<cur_o)
    name="ENGULF" if bullish_engulfing or bearish_engulfing else "MOM"
    return {"buy":buy,"sell":sell,"name":name}

def market_state(c,vp):
    e20=ema(c,20); price=c[-1]
    if price>e20 and vp["buy_pct"]>55: return "PUMP"
    if price<e20 and vp["sell_pct"]>55: return "DUMP"
    return "TREND"

def get_wick_levels(h,l,lookback=20):
    recent_high_wick = max(h[-lookback:])
    recent_low_wick = min(l[-lookback:])
    swing_highs = sorted(h[-lookback:], reverse=True)[:3]
    swing_lows = sorted(l[-lookback:])[:3]
    return recent_high_wick, recent_low_wick, swing_highs, swing_lows

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy):
    ob_low, ob_high = ob
    ob_50 = (ob_low + ob_high)/2
    recent_high_wick, recent_low_wick, swing_highs, swing_lows = get_wick_levels(h,l,20)
    if is_buy:
        entry = ob_50
        sl = min(min(l[-5:]), ob_low) * 0.996
        tp1 = swing_highs[0] * 0.997 if swing_highs else recent_high_wick*0.995
        tp2 = recent_high_wick * 0.996
        tp3 = tp2 * 1.02
    else:
        entry = ob_50
        sl = max(max(h[-5:]), ob_high) * 1.004
        tp1 = swing_lows[0] * 1.003 if swing_lows else recent_low_wick*1.005
        tp2 = recent_low_wick * 1.004
        tp3 = tp2 * 0.98
    risk = abs(entry - sl); rr2 = abs(tp2 - entry)/(risk or 1e-9)
    return entry, sl, tp1, tp2, tp3, rr2

def get_volume_phase(p, vol_x, price):
    now=time.time()
    if p not in VOL_HISTORY: VOL_HISTORY[p]=[]
    VOL_HISTORY[p].append(vol_x)
    if len(VOL_HISTORY[p])>10: VOL_HISTORY[p].pop(0)
    if vol_x >= 1.7:
        if p not in WHALE_TRACKER or "exit_time" in WHALE_TRACKER[p]:
            WHALE_TRACKER[p] = {"enter_time": now, "enter_vol": vol_x, "enter_price": price}
            return "WHALE_FLASH_ENTER", 0
        time_in = now - WHALE_TRACKER[p]["enter_time"]
        if time_in <= 15*60: return "WHALE_FLASH_ACTIVE", time_in
        else:
            WHALE_TRACKER[p] = {"exit_time": now, "exit_price": price, "last_enter": WHALE_TRACKER[p]}
            return "WHALE_EXITED", time_in
    if p in WHALE_TRACKER and "exit_time" in WHALE_TRACKER[p]:
        if now - WHALE_TRACKER[p]["exit_time"] <= 60*60 and 1.0 <= vol_x <= 1.7: return "RETAIL_FOMO", now-WHALE_TRACKER[p]["exit_time"]
    if vol_x >= 1.0: return "BUILDING", 0
    if vol_x >= 0.7: return "WATCH", 0
    return "DEAD", 0

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15"); h1=kl(p,"Min60")
    if not d5 or not d15 or not h1: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    price=c[-1]
    session_name,session_emoji,_=get_session()
    bos=detect_bos(d5["h"],d5["l"],d5["c"]) or detect_bos(d15["h"],d15["l"],d15["c"])
    pat=pattern(d5["h"],d5["l"])
    if pat=="none": pat=pattern(d15["h"],d15["l"])
    highs_5,lows_5=swing_points(d5["h"],d5["l"]); vp=volume_pressure(o,h,l,c,v); state=market_state(c,vp)
    phase, phase_time = get_volume_phase(p, vp["vol_x"], price)
    is_whale = "WHALE_FLASH" in phase or vp["vol_x"]>=1.7

    for is_buy in [True,False]:
        side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"; now=time.time(); prev=COOLDOWN["signals"].get(key,{}); elapsed=now-prev.get("t",0)
        cd_need=COOLDOWN_BUILDING if phase=="BUILDING" else COOLDOWN_WHALE_FLASH if "WHALE" in phase else COOLDOWN_RETAIL_FOMO if phase=="RETAIL_FOMO" else COOLDOWN_NORMAL
        if prev.get("result")=="SL": cd_need=max(cd_need, COOLDOWN_AFTER_SL)
        if elapsed<cd_need: continue
        if vp["vol_x"] < 0.7 and not is_whale: continue

        out_in=detect_out_in(o,h,l,c,side); deep=detect_deep_WM(h,l,side)
        sweep_ok=(detect_xxx_sweep(lows_5,l[-1]) if is_buy else detect_xxx_sweep_high(highs_5,h[-1])) if (highs_5 and lows_5) else False
        has_reason = out_in or deep or sweep_ok or pat!="none" or bos is not None
        if not has_reason and not is_whale: continue
        STATS["xxx"]+=1

        ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=50)
        if not ob: continue
        ob_low,ob_high=ob
        near = abs(price-(ob_high if is_buy else ob_low))/price < 0.06
        inside = ob_low*0.95 <= price <= ob_high*1.05
        if not (inside or near or is_whale): continue
        STATS["touched"]+=1

        # ULTRA LOOSE - NO CANDLE BLOCK
        candles=detect_strong_candles(o,h,l,c)

        entry, sl, tp1, tp2, tp3, rr2 = get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy)
        if rr2<0.8: continue # FIXED from 1.2

        COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"normal"}; save()
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl,"side_key":key}
        STATS["sniper"]+=1
        reason=f"{pat} {candles['name']} {bos or ''} {'SWEEP' if out_in else ''} {'DEEP' if deep else ''}".strip()
        emoji = "🟢" if is_buy else "🔴"
        if phase=="WHALE_FLASH_ENTER": phase_txt=f"⚡ WHALE ENTER {vp['vol_x']:.2f}x"
        elif phase=="WHALE_FLASH_ACTIVE": phase_txt=f"⚡ WHALE ACTIVE {phase_time/60:.0f}m {vp['vol_x']:.2f}x"
        elif phase=="RETAIL_FOMO": phase_txt=f"🔥 FOMO {vp['vol_x']:.2f}x"
        else: phase_txt=f"🏗️ BUILDING {vp['vol_x']:.2f}x"

        tg(
f"{emoji} <b>{s} {side}</b> {session_emoji} {session_name}\n"
f"{phase_txt}\n"
f"Entry: {entry:.6f} (50% OB)\n"
f"Now: {price:.6f}\n"
f"SL: {sl:.6f}\n"
f"TP1: {tp1:.6f}\n"
f"TP2: {tp2:.6f} RR:{rr2:.1f}R\n"
f"TP3: {tp3:.6f}\n"
f"{reason} | {state} {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}%"
        )

def check_exits():
    now=time.time()
    for s in list(ACTIVE.keys()):
        pos=ACTIVE[s]; p=pos.get("perp"); d=kl(p,"Min1")
        if not d: continue
        cur=d["c"][-1]; entry=pos["entry"]; is_buy=pos["is_buy"]; sl=pos["sl"]; tp1=pos["tp1"]; tp2=pos["tp2"]; key=pos["side_key"]
        if is_buy:
            if cur>=tp2: tg(f"✅ {s} TP2 HIT {cur:.6f}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"TP2"}; save(); ACTIVE.pop(s); continue
            if cur>=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 {s} TP1 BE {cur:.6f}"); pos["sl"]=entry
            if cur<=sl: tg(f"❌ {s} SL {cur:.6f}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"SL"}; save(); ACTIVE.pop(s); continue
        else:
            if cur<=tp2: tg(f"✅ {s} TP2 HIT {cur:.6f}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"TP2"}; save(); ACTIVE.pop(s); continue
            if cur<=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 {s} TP1 BE {cur:.6f}"); pos["sl"]=entry
            if cur>=sl: tg(f"❌ {s} SL {cur:.6f}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"SL"}; save(); ACTIVE.pop(s); continue
        if now-pos["t"]>30*60: tg(f"⏰ {s} TIMEOUT"); ACTIVE.pop(s)

print("=== BOT V28.2 ULTRA LOOSE ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"FINAL STATS T:{STATS['touched']} SNIPER:{STATS['sniper']} XXX:{STATS['xxx']} ACTIVE:{list(ACTIVE.keys())}", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except: pass
        check_exits(); time.sleep(60)
