# V28.8.3 DUAL SIDE - 62% FIRST - VOL 0.01x SECOND - FIXED SPAM + LIQ TP
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {"GRASSUSDT":"GRASS_USDT","TAOUSDT":"TAO_USDT","SANDUSDT":"SAND_USDT","SENTUSDT":"SENT_USDT","FARTCOINUSDT":"FARTCOIN_USDT","JASMYUSDT":"JASMY_USDT","KOMAUSDT":"KOMA_USDT",}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"
COOLDOWN={"signals":{}}; ACTIVE={}
if os.path.exists(COOLDOWN_FILE):
    try:
        d=json.load(open(COOLDOWN_FILE))
        if d.get("signals"):
            k=list(d["signals"].keys())[0]
            if "_" not in k: d={"signals":{}}
        COOLDOWN=d
    except: COOLDOWN={"signals":{}}
if os.path.exists(ACTIVE_FILE):
    try: ACTIVE=json.load(open(ACTIVE_FILE))
    except: ACTIVE={}
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_active(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
STATS={"touched":0,"sniper":0,"xxx":0}
WHALE_TRACKER={}
# NEW MEMORY FOR LIQ + SPAM FIX
LAST_TOP = {} # symbol -> last top level sent

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass
COOLDOWN_NORMAL=60*60
COOLDOWN_AFTER_SL=90*60
COOLDOWN_WHALE_FLASH=10*60
COOLDOWN_SAME_LIQ=30*60 # FIX: 30min block for same liquidity
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
def fbs_62_first(h,l,c):
    if len(c)<3: return None, "no data", 0
    prev_high = h[-2]; prev_low = l[-2]
    curr_close = c[-1]; curr_low = l[-1]; curr_high = h[-1]
    prev_range = prev_high - prev_low
    if prev_range == 0: return None, "no range", 0
    l75 = prev_low + prev_range*0.75
    l62 = prev_low + prev_range*0.62
    l38 = prev_low + prev_range*0.38
    l25 = prev_low + prev_range*0.25
    if curr_close < l75 and c[-2] > c[-3]:
        return None, f"WEAK TOP-LEFT {curr_close:.4f}<75%", 0
    if curr_close > l25 and c[-2] < c[-3]:
        return None, f"WEAK BTM-LEFT {curr_close:.4f}>25%", 0
    if curr_close > l62 and curr_low > l38:
        return "BOS_UP_STRONG", f"STRONG BUY Top-Right >62% {l62:.4f}", l62
    if curr_close < l38 and curr_high < l62:
        return "BOS_DOWN_STRONG", f"STRONG SELL Btm-Right <38% {l38:.4f}", l38
    return None, "No 62% breakout", 0
def pattern(h,l):
    tops=[];bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]:
            tops.append((i,h[i]))
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]:
            bots.append((i,l[i]))
    if len(tops)>=3:
        if tops[-1][0]-tops[-2][0]>=5 and tops[-2][0]-tops[-3][0]>=5:
            prices=[tops[-1][1],tops[-2][1],tops[-3][1]]
            if max(prices)-min(prices)<sum(prices)/3*0.008: return "triple_top"
    if len(tops)>=2:
        if tops[-1][0]-tops[-2][0]>=5:
            if abs(tops[-1][1]-tops[-2][1])/tops[-2][1]<0.008: return "double_top"
    if len(bots)>=3:
        if bots[-1][0]-bots[-2][0]>=5 and bots[-2][0]-bots[-3][0]>=5:
            prices=[bots[-1][1],bots[-2][1],bots[-3][1]]
            if max(prices)-min(prices)<sum(prices)/3*0.008: return "triple_bottom"
    if len(bots)>=2:
        if bots[-1][0]-bots[-2][0]>=5:
            if abs(bots[-1][1]-bots[-2][1])/bots[-2][1]<0.008: return "double_bottom"
    return "none"
def get_last_ob(o,h,l,c,bullish=True,lookback=60):
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
def volume_delta(o,c,v,look=10):
    buy_v=sum(v[i] for i in range(-look,0) if c[i]>o[i])
    sell_v=sum(v[i] for i in range(-look,0) if c[i]<o[i])
    return buy_v, sell_v
def get_wick_levels(h,l,lookback=20):
    return max(h[-lookback:]), min(l[-lookback:])

# NEW: AUTO LIQUIDITY TP FINDER
def get_liquidity_tps(d5, d15, d60, entry, is_buy):
    """TP1 = first indecision/FVG tap, TP2 = next HTF liquidity pool"""
    try:
        liqs = []
        # Collect HTF highs/lows as liquidity
        for tf in [d5, d15, d60]:
            if not tf: continue
            hi = max(tf["h"][-20:])
            lo = min(tf["l"][-20:])
            liqs.append(hi)
            liqs.append(lo)
            # FVG / indecision wicks
            for i in range(-15,-1):
                if tf["h"][i] > tf["h"][i-1] * 1.005:
                    liqs.append(tf["h"][i])
                if tf["l"][i] < tf["l"][i-1] * 0.995:
                    liqs.append(tf["l"][i])
        liqs = sorted(list(set(liqs)))
        if is_buy:
            above = [x for x in liqs if x > entry * 1.002] # must be 0.2% above entry
            above = sorted(above)
            if len(above) >= 2:
                return above[0], above[1], above[0]*1.02
            elif len(above) == 1:
                return above[0], above[0]*1.015, above[0]*1.03
        else:
            below = [x for x in liqs if x < entry * 0.998]
            below = sorted(below, reverse=True)
            if len(below) >= 2:
                return below[0], below[1], below[0]*0.98
            elif len(below) == 1:
                return below[0], below[0]*0.985, below[0]*0.97
    except: pass
    return None, None, None

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy, d5=None, d15=None, d60=None):
    ob_low, ob_high = ob
    ob_50 = (ob_low + ob_high)/2
    recent_high, recent_low = get_wick_levels(h,l,20)
    if is_buy:
        entry = ob_50; sl = min(min(l[-7:]), ob_low) * 0.997
        tp1_liq, tp2_liq, tp3_liq = get_liquidity_tps(d5, d15, d60, entry, True)
        tp1 = tp1_liq if tp1_liq else recent_high * 0.995
        tp2 = tp2_liq if tp2_liq else recent_high * 1.01
        tp3 = tp3_liq if tp3_liq else tp2 * 1.02
    else:
        entry = ob_50; sl = max(max(h[-7:]), ob_high) * 1.003
        tp1_liq, tp2_liq, tp3_liq = get_liquidity_tps(d5, d15, d60, entry, False)
        tp1 = tp1_liq if tp1_liq else recent_low * 1.005
        tp2 = tp2_liq if tp2_liq else recent_low * 0.99
        tp3 = tp3_liq if tp3_liq else tp2 * 0.98
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
def detect_bos(h,l,c):
    highs=[]; lows=[]; look=3; n=len(h)
    for i in range(look,n-look):
        if all(h[i]>=h[j] for j in range(i-look,i+look+1) if j!=i): highs.append((i,h[i]))
        if all(l[i]<=l[j] for j in range(i-look,i+look+1) if j!=i): lows.append((i,l[i]))
    if len(highs)<2 or len(lows)<2: return None
    price=c[-1]
    if price>highs[-1][1] and highs[-1][1]>highs[-2][1]: return "BOS_UP"
    if price<lows[-1][1] and lows[-1][1]<lows[-2][1]: return "BOS_DOWN"
    return None
def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15"); d60=kl(p,"Min60")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    price=c[-1]
    session_name,session_emoji=get_session()
    if session_name=="OFF": return
    fbs_up=None; fbs_down=None; fbs_msg_up=""; fbs_msg_down=""; top_up=0; top_down=0
    for tf_data, tf_name in [(d5,"5m"),(d15,"15m")]:
        res,msg,top = fbs_62_first(tf_data["h"], tf_data["l"], tf_data["c"])
        if res and "UP" in res and not fbs_up: fbs_up=res; fbs_msg_up=f"{msg} ({tf_name})"; top_up=top
        if res and "DOWN" in res and not fbs_down: fbs_down=res; fbs_msg_down=f"{msg} ({tf_name})"; top_down=top
    if not fbs_up and not fbs_down:
        print(f"{s} SNIPER:0 - No 62% breakout", flush=True)
        return
    vp=volume_pressure(o,h,l,c,v)
    if vp["vol_x"] < 0.01:
        print(f"{s} VOL KILL {vp['vol_x']:.2f}x - but 62% OK {fbs_up or fbs_down}", flush=True)
        return
    buy_v, sell_v = volume_delta(o,c,v,10)
    bos=detect_bos(d5["h"],d5["l"],d5["c"]) or detect_bos(d15["h"],d15["l"],d15["c"])
    pat=pattern(d5["h"],d5["l"])
    if pat=="none": pat=pattern(d15["h"],d15["l"])
    phase, _ = get_volume_phase(p, vp["vol_x"], price)
    is_whale = "WHALE" in phase
    for is_buy in [True, False]:
        fbs_res = fbs_up if is_buy else fbs_down
        fbs_msg = fbs_msg_up if is_buy else fbs_msg_down
        top_level = top_up if is_buy else top_down
        if not fbs_res: continue
        side="BUY" if is_buy else "SELL"
        key=f"{s}_{side}"

        # === FIX 1: ANTI-SPAM SAME LIQUIDITY 30min ===
        last_top_key = f"{s}_{side}"
        if last_top_key in LAST_TOP:
            last_top, last_time = LAST_TOP[last_top_key]
            same_liq = abs(top_level - last_top) / (last_top or 1) < 0.005 # 0.5%
            if same_liq and (time.time() - last_time) < COOLDOWN_SAME_LIQ:
                print(f"{s} {side} SAME LIQ SKIP {int((COOLDOWN_SAME_LIQ-(time.time()-last_time))//60)}m Top:{top_level:.4f}", flush=True)
                continue

        if key in ACTIVE:
            age = int((time.time() - ACTIVE[key].get("t",0))//60)
            print(f"{s} {side} ACTIVE SKIP {age}m", flush=True)
            continue
        prev=COOLDOWN["signals"].get(key,{})
        now=time.time(); last_t=prev.get("t",0)
        cd_need=COOLDOWN_WHALE_FLASH if is_whale else COOLDOWN_NORMAL
        if prev.get("result")=="SL": cd_need=COOLDOWN_AFTER_SL
        if now-last_t < cd_need:
            # === FIX 2: SESSION DEDUP - TREND CONTINUING ===
            if prev.get("session") == "ASIAN" and session_name!= "ASIAN" and prev.get("dir")==is_buy:
                # Send trend continuing instead of new BUY
                last_entry = prev.get("entry", price)
                last_tp1 = prev.get("tp1", 0)
                last_tp2 = prev.get("tp2", 0)
                tg(f"🟡 <b>{s} {side} TREND CONTINUING</b> {prev.get('session','')}->{session_name}\nLast {side} {top_level:.4f} still >62% holding\nEntry {last_entry:.6f} tapping OB\nTP1 {last_tp1:.6f} TP2 {last_tp2:.6f} | {pat} | {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}%")
                COOLDOWN["signals"][key]["t"]=now - cd_need + 300 # allow next check in 5min but as continuing
                save()
                continue
            print(f"{s} {side} FILE CD SKIP {int((cd_need-(now-last_t))//60)}m", flush=True)
            continue
        if is_buy and vp["buy_pct"] < 60:
            print(f"{s} BUY PRESSURE LOW {vp['buy_pct']:.0f}%", flush=True)
            continue
        if not is_buy and vp["sell_pct"] < 60:
            print(f"{s} SELL PRESSURE LOW {vp['sell_pct']:.0f}%", flush=True)
            continue
        if is_buy and pat in ["double_top","triple_top"]: continue
        if not is_buy and pat in ["double_bottom","triple_bottom"]: continue
        ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=60)
        if not ob: ob = (min(l[-15:]), max(h[-15:]))
        entry, sl, tp1, tp2, tp3, rr2 = get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy, d5, d15, d60)
        if rr2 < 1.0:
            print(f"{s} {side} RR LOW {rr2:.1f}", flush=True)
            continue
        # SAVE WITH SESSION + TOP FOR DEDUP
        COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"normal","session":session_name,"top":top_level,"entry":entry,"tp1":tp1,"tp2":tp2}
        save()
        LAST_TOP[f"{s}_{side}"] = (top_level, now)
        ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl,"side_key":key}
        save_active(); STATS["sniper"]+=1
        emoji = "🟢" if is_buy else "🔴"
        phase_txt = f"⚡ WHALE {vp['vol_x']:.1f}x" if is_whale else f"🏗️ BUILD {vp['vol_x']:.1f}x"
        tg(f"{emoji} <b>{s} {side}</b> {session_emoji} {session_name}\n{phase_txt} {fbs_res} RR:{rr2:.1f}R\n{fbs_msg}\nEntry: {entry:.6f} (50% OB)\nSL: {sl:.6f}\nTP1: {tp1:.6f} (liq tap)\nTP2: {tp2:.6f} (liq sweep)\n{pat} {bos or ''} | {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}% | Δ B:{buy_v:.0f} S:{sell_v:.0f}")

print("=== BOT V28.8.3 62% FIRST + VOL 0.01x SECOND + ANTI-SPAM + LIQ TP ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"STATS SNIPER:{STATS['sniper']} ACTIVE:{list(ACTIVE.keys())}", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(e, flush=True)
        print(f"Sleep 60s... ACTIVE:{list(ACTIVE.keys())}", flush=True)
        time.sleep(60)
