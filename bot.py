# BOT V31.2 FINAL - INSTANT FLIP + ANTI-DUP + IMAGE LOGIC
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {"GRASSUSDT":"GRASS_USDT","TAOUSDT":"TAO_USDT","SANDUSDT":"SAND_USDT","SENTUSDT":"SENT_USDT","FARTCOINUSDT":"FARTCOIN_USDT","JASMYUSDT":"JASMY_USDT","KOMAUSDT":"KOMA_USDT",}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
VOLATILE_SYMS = ["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","LABUSDT","VELVETUSDT"]
COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"
COOLDOWN={"signals":{}}; ACTIVE={}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: COOLDOWN={"signals":{}}
if os.path.exists(ACTIVE_FILE):
    try: ACTIVE=json.load(open(ACTIVE_FILE))
    except: ACTIVE={}

def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_active(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
LAST_TOP={}

def tg(msg):
    print(msg,flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

COOLDOWN_NORMAL=30*60; COOLDOWN_SAME_LIQ=60*60

def get_session():
    h=datetime.now(ZoneInfo("UTC")).hour
    if 0<=h<7: return "ASIAN","🟡"
    if 7<=h<12: return "LONDON","🔵"
    if 12<=h<21: return "NY","🟢"
    return "OFF","⚫"

def kl(sym,interval):
    try:
        r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}", params={"interval":interval}, timeout=10).json()
        data=r.get("data",[])
        if not data: return None
        if isinstance(data,dict):
            def f(x):
                try: return float(x)
                except: return 0.0
            return {"o":[f(x) for x in data.get("open",[])],"h":[f(x) for x in data.get("high",[])],"l":[f(x) for x in data.get("low",[])],"c":[f(x) for x in data.get("close",[])],"v":[f(x) for x in data.get("vol",[])]}
        o,h,l,c,v=[],[],[],[],[]
        for k in data: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
        return {"o":o,"h":h,"l":l,"c":c,"v":v}
    except: return None

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc = h[-2],l[-2],o[-2],c[-2]
    ch,cl,co,cc = h[-1],l[-1],o[-1],c[-1]
    prange = ph-pl
    if prange==0: return None,0,0
    p75 = pl + prange*0.75; p62 = pl + prange*0.62; p38 = pl + prange*0.38; p25 = pl + prange*0.25
    big_range_pct = (ph-pl)/(pl or 1)*100
    body = abs(pc-po); upper_wick = ph - max(pc,po); lower_wick = min(pc,po) - pl
    is_sweep_up = upper_wick > body*1.5; is_sweep_down = lower_wick > body*1.5
    if pc > po:
        if is_sweep_up and cc < p75: return "WEAK_BULL_TRAP", ph, big_range_pct
        if pc >= p62:
            if cc >= p38 and cl >= p25 and cc > co: return "BOS_UP_STRONG", ph, big_range_pct
            elif cc < p25 or (cc < co and cc < p38): return "BOS_UP_WEAK", ph, big_range_pct
    if pc < po:
        if is_sweep_down and cc > p25: return "WEAK_BEAR_TRAP", pl, big_range_pct
        if pc <= p38:
            if cc <= p62 and ch <= p75 and cc < co: return "BOS_DOWN_STRONG", pl, big_range_pct
            elif cc > p75 or (cc > co and cc > p62): return "BOS_DOWN_WEAK", pl, big_range_pct
    return None,0,big_range_pct

def pattern(h,l):
    tops=[];bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]: tops.append((i,h[i]))
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]: bots.append((i,l[i]))
    if len(tops)>=2 and tops[-1][0]-tops[-2][0]>=5:
        if abs(tops[-1][1]-tops[-2][1])/tops[-2][1]<0.008: return "double_top"
    if len(bots)>=2 and bots[-1][0]-bots[-2][0]>=5:
        if abs(bots[-1][1]-bots[-2][1])/bots[-2][1]<0.008: return "double_bottom"
    return "none"

def get_last_ob(o,h,l,c,bullish=True,lookback=60):
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2,len(c)-lookback,-1):
        body=c[i+1]-o[i+1]; is_impulse=abs(body)>atr*0.3 if atr else True
        if bullish and c[i]<o[i] and is_impulse and c[i+1]>o[i+1]: return (l[i],h[i])
        if not bullish and c[i]>o[i] and is_impulse and c[i+1]<o[i+1]: return (l[i],h[i])
    return None

def volume_pressure(o,h,l,c,v,n=20):
    if len(v)<n: return {"vol_x":1,"buy_pct":50,"sell_pct":50}
    avg=statistics.mean(v[-n:]); cur=v[-1]; bp=sp=0
    for i in range(-n,0): rng=h[i]-l[i] or 1e-9; delta=(c[i]-o[i])/rng*v[i]; bp+=delta if delta>0 else 0; sp+=-delta if delta<0 else 0
    total=bp+sp or 1; return {"vol_x":cur/(avg or 1),"buy_pct":bp/total*100,"sell_pct":sp/total*100}

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,big_range_pct,symbol,perp=None):
    ob_low,ob_high=ob
    is_volatile = symbol in VOLATILE_SYMS or big_range_pct > 2.5
    prange = ob_high-ob_low
    if is_buy:
        entry = ob_low + prange* (0.56 if is_volatile else 0.44)
        sl_pct = 0.028 if is_volatile else 0.012
        tp1_pct, tp2_pct, tp3_pct = (0.03,0.06,0.09) if is_volatile else (0.015,0.025,0.04)
        sl = entry * (1 - sl_pct); tp1 = entry * (1 + tp1_pct); tp2 = entry * (1 + tp2_pct); tp3 = entry * (1 + tp3_pct)
    else:
        entry = ob_high - prange* (0.56 if is_volatile else 0.44)
        sl_pct = 0.028 if is_volatile else 0.012
        tp1_pct, tp2_pct, tp3_pct = (0.03,0.06,0.09) if is_volatile else (0.015,0.025,0.04)
        sl = entry * (1 + sl_pct); tp1 = entry * (1 - tp1_pct); tp2 = entry * (1 - tp2_pct); tp3 = entry * (1 - tp3_pct)
    risk=abs(entry-sl)
    rr1=abs(tp1-entry)/(risk or 1e-9); rr2=abs(tp2-entry)/(risk or 1e-9); rr3=abs(tp3-entry)/(risk or 1e-9)
    return entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_volatile

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    if get_session()[0]=="OFF": return
    now=time.time()
    buy_key=f"{s}_BUY"; sell_key=f"{s}_SELL"

    # --- ACTIVE BUY - check reversal ---
    if buy_key in ACTIVE:
        fbs_res,_,brp = fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if fbs_res and "DOWN_STRONG" in fbs_res:
            fbs_15,res15_top,brp15 = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "DOWN_STRONG" in fbs_15:
                tg(f"⚠️ <b>REVERSAL {s}</b> 🔴 STRONG 38% BREAKDOWN (5m+15m)\nClose BUY {c[-1]:.6f}")
                del ACTIVE[buy_key]; save_active()
                # INSTANT FLIP SELL
                is_vol = s in VOLATILE_SYMS or max(brp,brp15) > 2.5
                entry = c[-1]
                sl_pct = 0.028 if is_vol else 0.012
                tp1_pct,tp2_pct,tp3_pct = (0.03,0.06,0.09) if is_vol else (0.015,0.025,0.04)
                sl = entry * (1 + sl_pct); tp1 = entry * (1 - tp1_pct); tp2 = entry * (1 - tp2_pct); tp3 = entry * (1 - tp3_pct)
                key = f"{s}_SELL"
                COOLDOWN["signals"][key]={"t":now,"dir":False,"top":res15_top,"entry":entry,"tp1":tp1,"tp2":tp2}; save()
                LAST_TOP[key]=(res15_top,now)
                ACTIVE[key]={"entry":entry,"is_buy":False,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
                vol_tag = "10% VOL" if is_vol else "4% STABLE"
                tg(f"🔄 <b>FLIP SELL {s}</b> | 38% BREAKDOWN FLIP ({vol_tag})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 {tp1:.6f} TP2 {tp2:.6f} TP3 {tp3:.6f}\nImage logic 5m+15m BOS_DOWN")
                return
        prev_high=ACTIVE[buy_key].get("highest", ACTIVE[buy_key]["entry"])
        last_hold_profit=ACTIVE[buy_key].get("last_hold_profit",0)
        if c[-1] > prev_high and fbs_res and "UP_STRONG" in fbs_res:
            profit=(c[-1]-ACTIVE[buy_key]["entry"])/ACTIVE[buy_key]["entry"]*100
            if profit - last_hold_profit >= 0.5:
                tg(f"💎 <b>HOLD BUY {s}</b> | +{profit:.2f}%\nNew high {c[-1]:.6f} 🟢")
                ACTIVE[buy_key]["last_hold_profit"]=profit
            ACTIVE[buy_key]["highest"]=c[-1]; save_active()
        return

    # --- ACTIVE SELL - check reversal ---
    if sell_key in ACTIVE:
        fbs_res,_,brp = fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if fbs_res and "UP_STRONG" in fbs_res:
            fbs_15,res15_top,brp15 = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "UP_STRONG" in fbs_15:
                tg(f"⚠️ <b>REVERSAL {s}</b> 🟢 STRONG 62% BREAKOUT (5m+15m)\nClose SELL {c[-1]:.6f}")
                del ACTIVE[sell_key]; save_active()
                # INSTANT FLIP BUY - catches +8% pump like GRASS
                is_vol = s in VOLATILE_SYMS or max(brp,brp15) > 2.5
                entry = c[-1]
                sl_pct = 0.028 if is_vol else 0.012
                tp1_pct,tp2_pct,tp3_pct = (0.03,0.06,0.09) if is_vol else (0.015,0.025,0.04)
                sl = entry * (1 - sl_pct); tp1 = entry * (1 + tp1_pct); tp2 = entry * (1 + tp2_pct); tp3 = entry * (1 + tp3_pct)
                key = f"{s}_BUY"
                COOLDOWN["signals"][key]={"t":now,"dir":True,"top":res15_top,"entry":entry,"tp1":tp1,"tp2":tp2}; save()
                LAST_TOP[key]=(res15_top,now)
                ACTIVE[key]={"entry":entry,"is_buy":True,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
                vol_tag = "10% VOL" if is_vol else "4% STABLE"
                tg(f"🔄 <b>FLIP BUY {s}</b> | 62% BREAKOUT FLIP ({vol_tag})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 {tp1:.6f} TP2 {tp2:.6f} TP3 {tp3:.6f}\nImage logic 5m+15m BOS_UP - caught pump")
                return
        prev_low=ACTIVE[sell_key].get("lowest", ACTIVE[sell_key]["entry"])
        last_hold_profit=ACTIVE[sell_key].get("last_hold_profit",0)
        if c[-1] < prev_low and fbs_res and "DOWN_STRONG" in fbs_res:
            profit=(ACTIVE[sell_key]["entry"]-c[-1])/ACTIVE[sell_key]["entry"]*100
            if profit - last_hold_profit >= 0.5:
                tg(f"💎 <b>HOLD SELL {s}</b> | +{profit:.2f}%\nNew low {c[-1]:.6f} 🔴")
                ACTIVE[sell_key]["last_hold_profit"]=profit
            ACTIVE[sell_key]["lowest"]=c[-1]; save_active()
        return

    # --- NEW ENTRY ---
    fbs_res=None; top_level=0; tf_used=""; big_range_pct=0
    for tf_data,tf_name in [(d5,"5m"),(d15,"15m")]:
        res,top,brp=fbs_image_logic(tf_data["h"],tf_data["l"],tf_data["c"],tf_data["o"])
        if res and "STRONG" in res:
            fbs_res=res; top_level=top; tf_used=tf_name; big_range_pct=brp; break
        if res and "WEAK" in res: return
    if not fbs_res: return
    vp=volume_pressure(o,h,l,c,v); pat=pattern(d5["h"],d5["l"])
    is_buy="UP" in fbs_res; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"
    if key in ACTIVE: return # ANTI-DUP
    try:
        day=kl(p,"Day1")
        if day and len(day["c"])>=2:
            day_pct = (day["c"][-1]-day["c"][-2])/(day["c"][-2] or 1)*100
            if abs(day_pct) > 7.0: return
    except: pass
    if f"{s}_{side}" in LAST_TOP:
        last_top,last_time=LAST_TOP[f"{s}_{side}"]
        if abs(top_level-last_top)/(last_top or 1)<0.005 and (now-last_time)<COOLDOWN_SAME_LIQ: return
    prev=COOLDOWN["signals"].get(key,{});
    if now-prev.get("t",0)<COOLDOWN_NORMAL: return
    if is_buy and pat=="double_top": return
    if not is_buy and pat=="double_bottom": return
    if is_buy and vp["buy_pct"]<55: return
    if not is_buy and vp["sell_pct"]<55: return
    ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=60)
    if not ob: ob=(min(l[-15:]),max(h[-15:]))
    entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol=get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,big_range_pct,s,p)
    min_rr1 = 1.0 if is_vol else 1.2; min_rr2 = 1.8 if is_vol else 2.0
    if rr1 < min_rr1 or rr1 > 8.0: return
    if rr2 < min_rr2: return
    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top_level,"entry":entry,"tp1":tp1,"tp2":tp2}; save()
    LAST_TOP[f"{s}_{side}"]=(top_level,now)
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
    vol_tag = "10% VOL" if is_vol else "4% STABLE"
    if is_buy: tg(f"🟢 <b>BUY {s}</b> | 62% STRONG ({tf_used}) {vol_tag}\nRange {big_range_pct:.2f}% | Entry {entry:.6f} | SL {sl:.6f} ({abs(entry-sl)/entry*100:.1f}%)\nTP1 {tp1:.6f} ({rr1:.1f}R) | TP2 {tp2:.6f} ({rr2:.1f}R) | TP3 {tp3:.6f} ({rr3:.1f}R)")
    else: tg(f"🔴 <b>SELL {s}</b> | 38% STRONG ({tf_used}) {vol_tag}\nRange {big_range_pct:.2f}% | Entry {entry:.6f} | SL {sl:.6f} ({abs(entry-sl)/entry*100:.1f}%)\nTP1 {tp1:.6f} ({rr1:.1f}R) | TP2 {tp2:.6f} ({rr2:.1f}R) | TP3 {tp3:.6f} ({rr3:.1f}R)")

print("=== BOT V31.2 FLIP + ANTI-DUP ===",flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(f"{s} err {e}")
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except: pass
        time.sleep(60)
