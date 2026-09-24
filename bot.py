# BOT V33 FINAL PERFECT - BTC DOMINANCE FILTER ALIGNED TO YOUR LIST
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {
    "GRASSUSDT":"GRASS_USDT",
    "KOMAUSDT":"KOMA_USDT",
    "FARTCOINUSDT":"FARTCOIN_USDT",
    "SENTUSDT":"SENT_USDT",
    "SANDUSDT":"SAND_USDT",
    "TAOUSDT":"TAO_USDT",
    "JASMYUSDT":"JASMY_USDT",
}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
FAST_SYMS = ["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"]
SLOW_SYMS = ["SANDUSDT","TAOUSDT","JASMYUSDT"]

# === PERFECT DOMINANCE SENSITIVITY ALIGNED TO YOUR COINS ===
DOM_SENSITIVITY = {
    "FARTCOINUSDT": 2.5, # Ultra volatile - moves 2.5x BTC.D
    "GRASSUSDT": 2.2, # Ultra volatile
    "KOMAUSDT": 2.0, # Very volatile
    "SENTUSDT": 1.6, # High beta
    "SANDUSDT": 1.3, # Medium
    "TAOUSDT": 1.1, # Medium-low, TAO holds better
    "JASMYUSDT": 1.2, # Medium
}

# BTC Dominance tracker
BTC_DOM_CACHE = {"value": 58.5, "history": [], "last_fetch": 0}

def get_btc_dominance():
    now = time.time()
    if now - BTC_DOM_CACHE["last_fetch"] < 300: # 5 min cache
        return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]
    try:
        # Free API - CoinGecko global
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()
        btc_d = r["data"]["market_cap_percentage"]["btc"]
        BTC_DOM_CACHE["value"] = btc_d
        BTC_DOM_CACHE["history"].append((now, btc_d))
        # Keep last 4 hours
        BTC_DOM_CACHE["history"] = [(t,v) for t,v in BTC_DOM_CACHE["history"] if now - t < 14400]
        BTC_DOM_CACHE["last_fetch"] = now
        return btc_d, BTC_DOM_CACHE["history"]
    except:
        return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]

def check_btc_dominance_filter(symbol,is_buy):
    btc_d, hist = get_btc_dominance()
    if len(hist) < 2: return True
    oldest_dom = hist[0][1]
    change = btc_d - oldest_dom # + = pumping, - = dumping
    sensitivity = DOM_SENSITIVITY.get(symbol, 1.0)
    effective_move = change * sensitivity

    # PERFECT MONEY LOGIC
    if change >= 0.6 and effective_move >= 0.9:
        if is_buy:
            print(f"⛔ DOM +{change:.2f}% (eff +{effective_move:.2f}%) BLOCK BUY {symbol}", flush=True)
            return False
        else:
            return True # Perfect SELL
    if change <= -0.6 and effective_move <= -0.9:
        if not is_buy:
            print(f"⛔ DOM {change:.2f}% (eff {effective_move:.2f}%) BLOCK SELL {symbol}", flush=True)
            return False
        else:
            return True # Perfect BUY

    # Absolute levels safety
    if btc_d > 60.5 and sensitivity >= 2.0 and is_buy: return False
    if btc_d < 54.0 and sensitivity >= 2.0 and not is_buy: return False
    return True

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

COOLDOWN_FAST_SAME=90*60; COOLDOWN_FAST_OPP=45*60; COOLDOWN_FAST_LVL=4*3600
COOLDOWN_SLOW_SAME=6*3600; COOLDOWN_SLOW_OPP=3*3600; COOLDOWN_SLOW_LVL=24*3600

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

def detect_foundation(o,h,l,c,is_buy,crt_low,crt_high):
    for i in range(-20,-1):
        try:
            body=abs(c[i]-o[i]); rng=h[i]-l[i] or 1e-9
            is_doji=body/rng<0.2
            is_engulf=(is_buy and c[i]>o[i] and c[i-1]<o[i-1] and c[i]>o[i-1] and o[i]<c[i-1]) or (not is_buy and c[i]<o[i] and c[i-1]>o[i-1] and c[i]<o[i-1] and o[i]>c[i-1])
            near_edge=(is_buy and l[i]<=crt_low*1.015) or (not is_buy and h[i]>=crt_high*0.985)
            if (is_doji or is_engulf) and near_edge: return True
        except: pass
    return False

def trendline_break(h,l,c,is_buy):
    if len(c)<20: return False
    if is_buy:
        recent_highs=h[-12:-2]
        is_descending=recent_highs[-1] < recent_highs[0]*1.02
        break_up=c[-1] > max(h[-11:-1])*1.002
        return is_descending and break_up
    else:
        recent_lows=l[-12:-2]
        is_ascending=recent_lows[-1] > recent_lows[0]*0.98
        break_down=c[-1] < min(l[-11:-1])*0.998
        return is_ascending and break_down

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]
    ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p75=pl+prange*0.75; p62=pl+prange*0.62; p38=pl+prange*0.38; p25=pl+prange*0.25
    big_range_pct=(ph-pl)/(pl or 1)*100
    body=abs(pc-po); upper_wick=ph-max(pc,po); lower_wick=min(pc,po)-pl
    is_sweep_up=upper_wick>body*1.5; is_sweep_down=lower_wick>body*1.5
    if pc>po:
        if is_sweep_up and cc<p75: return "WEAK_BULL_TRAP",ph,big_range_pct
        if pc>=p62:
            if cc>=p38 and cl>=p25 and cc>co: return "BOS_UP_STRONG",ph,big_range_pct
            elif cc<p25 or (cc<co and cc<p38): return "BOS_UP_WEAK",ph,big_range_pct
    if pc<po:
        if is_sweep_down and cc>p25: return "WEAK_BEAR_TRAP",pl,big_range_pct
        if pc<=p38:
            if cc<=p62 and ch<=p75 and cc<co: return "BOS_DOWN_STRONG",pl,big_range_pct
            elif cc>p75 or (cc>co and cc>p62): return "BOS_DOWN_WEAK",pl,big_range_pct
    return None,0,big_range_pct

def build_crt(symbol,h,l):
    if symbol in FAST_SYMS:
        look=min(48,len(h)); crt_high=max(h[-look:]); crt_low=min(l[-look:]); crt_type="4H CRT"
    else:
        look=min(288,len(h)); crt_high=max(h[-look:]); crt_low=min(l[-look:]); crt_type="Day CRT"
    return crt_low,crt_high,crt_type

def check_tbs(o,h,l,c,crt_low,crt_high,is_buy):
    if len(c)<3: return False
    if is_buy: return l[-2]<crt_low and c[-1]>crt_low and c[-1]>o[-1]
    else: return h[-2]>crt_high and c[-1]<crt_high and c[-1]<o[-1]

def pattern(h,l):
    tops=[]; bots=[]
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
    for i in range(-n,0):
        rng=h[i]-l[i] or 1e-9
        delta=(c[i]-o[i])/rng*v[i]
        if delta>0: bp+=delta
        else: sp+=-delta
    total=bp+sp or 1
    return {"vol_x":cur/(avg or 1),"buy_pct":bp/total*100,"sell_pct":sp/total*100}

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,big_range_pct,symbol,crt_low,crt_high):
    ob_low,ob_high=ob
    prange=ob_high-ob_low
    crt_range_pct=(crt_high-crt_low)/(crt_low or 1)*100
    is_volatile=symbol in FAST_SYMS or big_range_pct>2.5
    if symbol in FAST_SYMS:
        tp1_pct=max(0.03, crt_range_pct*0.30/100)
        tp2_pct=max(0.06, crt_range_pct*0.60/100)
        tp3_pct=max(0.09, crt_range_pct*0.90/100)
        sl_pct=max(0.028, crt_range_pct*0.25/100)
    else:
        tp1_pct=max(0.015, crt_range_pct*0.30/100)
        tp2_pct=max(0.025, crt_range_pct*0.60/100)
        tp3_pct=max(0.04, crt_range_pct*0.90/100)
        sl_pct=0.012
    if is_buy:
        entry=ob_low+prange*(0.56 if is_volatile else 0.44)
        sl=entry*(1-sl_pct); tp1=entry*(1+tp1_pct); tp2=entry*(1+tp2_pct); tp3=entry*(1+tp3_pct)
    else:
        entry=ob_high-prange*(0.56 if is_volatile else 0.44)
        sl=entry*(1+sl_pct); tp1=entry*(1-tp1_pct); tp2=entry*(1-tp2_pct); tp3=entry*(1-tp3_pct)
    risk=abs(entry-sl)
    rr1=abs(tp1-entry)/(risk or 1e-9); rr2=abs(tp2-entry)/(risk or 1e-9); rr3=abs(tp3-entry)/(risk or 1e-9)
    return entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_volatile,crt_range_pct

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<60: return
    if get_session()[0]=="OFF": return
    now=time.time(); time_12hr=get_time_12hr(); live_price=c[-1]
    buy_key=f"{s}_BUY"; sell_key=f"{s}_SELL"
    crt_low,crt_high,crt_type=build_crt(s,h,l)

    if buy_key in ACTIVE:
        fbs_res,_,brp=fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        profit=(c[-1]-ACTIVE[buy_key]["entry"])/ACTIVE[buy_key]["entry"]*100
        last_profit=ACTIVE[buy_key].get("last_hold_profit",0)
        hold_step=2.0 if s in FAST_SYMS else 1.0
        if profit-last_profit>=hold_step and fbs_res and "UP_STRONG" in fbs_res:
            tg(f"🟡 {s} HOLD BUY +{profit:.2f}% | {time_12hr} Price {live_price:.6f} FBS 62% still STRONG {crt_type}")
            ACTIVE[buy_key]["last_hold_profit"]=profit
            ACTIVE[buy_key]["highest"]=max(ACTIVE[buy_key].get("highest",0),c[-1])
            save_active()
        if fbs_res and "DOWN_STRONG" in fbs_res:
            fbs_15,res15_top,brp15=fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "DOWN_STRONG" in fbs_15 and check_tbs(o,h,l,c,crt_low,crt_high,False):
                if not check_btc_dominance_filter(s, False): return
                ob_flip=get_last_ob(o,h,l,c,bullish=False,lookback=60)
                if not ob_flip: ob_flip=(min(l[-15:]),max(h[-15:]))
                entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol,crt_pct=get_perfect_entry_sl_tp(o,h,l,c,ob_flip,False,max(brp,brp15),s,crt_low,crt_high)
                if rr1<1.0 or rr1>8:
                    del ACTIVE[buy_key]; save_active(); return
                pnl=(live_price-ACTIVE[buy_key]["entry"])/ACTIVE[buy_key]["entry"]*100
                emoji="🟢" if pnl>=0 else "🔴"
                tg(f"<b>REVERSAL {s} CLOSE BUY</b> {emoji} {pnl:+.2f}% {time_12hr} TBS SELL + FBS 38% {crt_type}")
                del ACTIVE[buy_key]; save_active()
                key=f"{s}_SELL"
                COOLDOWN["signals"][key]={"t":now,"dir":False,"top":res15_top,"entry":entry}; save()
                LAST_TOP[key]=(res15_top,now)
                ACTIVE[key]={"entry":entry,"is_buy":False,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
                vol_tag="10% VOL" if is_vol else "4% STABLE"
                tg(f"🔴 {s} SELL 38% STRONG | {crt_type} CRT {crt_pct:.1f}% | 5m TBS | {vol_tag} | {time_12hr}\nPrice: {live_price:.6f} Entry: {entry:.6f} SL: {sl:.6f} TP1 {tp1:.6f} ({rr1:.1f}R)")
                return
        if c[-1]>ACTIVE[buy_key].get("highest",0):
            ACTIVE[buy_key]["highest"]=c[-1]; save_active()
        return

    if sell_key in ACTIVE:
        fbs_res,_,brp=fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        profit=(ACTIVE[sell_key]["entry"]-c[-1])/ACTIVE[sell_key]["entry"]*100
        last_profit=ACTIVE[sell_key].get("last_hold_profit",0)
        hold_step=2.0 if s in FAST_SYMS else 1.0
        if profit-last_profit>=hold_step and fbs_res and "DOWN_STRONG" in fbs_res:
            tg(f"🟡 {s} HOLD SELL +{profit:.2f}% | {time_12hr} Price {live_price:.6f} FBS 38% still STRONG {crt_type}")
            ACTIVE[sell_key]["last_hold_profit"]=profit
            ACTIVE[sell_key]["lowest"]=min(ACTIVE[sell_key].get("lowest",999999),c[-1]); save_active()
        if fbs_res and "UP_STRONG" in fbs_res:
            fbs_15,res15_top,brp15=fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "UP_STRONG" in fbs_15 and check_tbs(o,h,l,c,crt_low,crt_high,True):
                if not check_btc_dominance_filter(s, True): return
                ob_flip=get_last_ob(o,h,l,c,bullish=True,lookback=60)
                if not ob_flip: ob_flip=(min(l[-15:]),max(h[-15:]))
                entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol,crt_pct=get_perfect_entry_sl_tp(o,h,l,c,ob_flip,True,max(brp,brp15),s,crt_low,crt_high)
                if rr1<1.0 or rr1>8:
                    del ACTIVE[sell_key]; save_active(); return
                pnl=(ACTIVE[sell_key]["entry"]-live_price)/ACTIVE[sell_key]["entry"]*100
                emoji="🟢" if pnl>=0 else "🔴"
                tg(f"<b>REVERSAL {s} CLOSE SELL</b> {emoji} {pnl:+.2f}% {time_12hr} TBS BUY + FBS 62% {crt_type}")
                del ACTIVE[sell_key]; save_active()
                key=f"{s}_BUY"
                COOLDOWN["signals"][key]={"t":now,"dir":True,"top":res15_top,"entry":entry}; save()
                LAST_TOP[key]=(res15_top,now)
                ACTIVE[key]={"entry":entry,"is_buy":True,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
                vol_tag="10% VOL" if is_vol else "4% STABLE"
                tg(f"🟢 {s} BUY 62% STRONG | {crt_type} CRT {crt_pct:.1f}% | 5m TBS | {vol_tag} | {time_12hr}\nPrice: {live_price:.6f} Entry: {entry:.6f} SL: {sl:.6f} TP1 {tp1:.6f} ({rr1:.1f}R)")
                return
        if c[-1]<ACTIVE[sell_key].get("lowest",999999):
            ACTIVE[sell_key]["lowest"]=c[-1]; save_active()
        return

    fbs_res=None; top_level=0; big_range_pct=0
    for tf_data in [d5,d15]:
        res,top,brp=fbs_image_logic(tf_data["h"],tf_data["l"],tf_data["c"],tf_data["o"])
        if res and "STRONG" in res:
            fbs_res=res; top_level=top; big_range_pct=brp; break
        if res and "WEAK" in res: return
    if not fbs_res: return
    is_buy="UP" in fbs_res; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"
    if key in ACTIVE: return
    if not detect_foundation(o,h,l,c,is_buy,crt_low,crt_high): return
    if not trendline_break(h,l,c,is_buy): return
    if not check_tbs(o,h,l,c,crt_low,crt_high,is_buy): return
    if not check_btc_dominance_filter(s, is_buy): return

    vp=volume_pressure(o,h,l,c,v); pat=pattern(d5["h"],d5["l"])
    try:
        day=kl(p,"Day1")
        if day and len(day["c"])>=2:
            day_pct=(day["c"][-1]-day["c"][-2])/(day["c"][-2] or 1)*100
            limit=12.0 if s in FAST_SYMS else 7.0
            if abs(day_pct)>limit: return
    except: pass

    if s in FAST_SYMS:
        SAME_CD=COOLDOWN_FAST_SAME; OPP_CD=COOLDOWN_FAST_OPP; LVL_CD=COOLDOWN_FAST_LVL
    else:
        SAME_CD=COOLDOWN_SLOW_SAME; OPP_CD=COOLDOWN_SLOW_OPP; LVL_CD=COOLDOWN_SLOW_LVL

    if f"{s}_{side}" in LAST_TOP:
        last_top,last_time=LAST_TOP[f"{s}_{side}"]
        if abs(top_level-last_top)/(last_top or 1)<0.005 and (now-last_time)<LVL_CD: return

    prev=COOLDOWN["signals"].get(key,{})
    if now-prev.get("t",0)<SAME_CD: return
    opp_key=f"{s}_{'SELL' if is_buy else 'BUY'}"
    opp_prev=COOLDOWN["signals"].get(opp_key,{})
    if now-opp_prev.get("t",0)<OPP_CD: return
    if is_buy and pat=="double_top": return
    if not is_buy and pat=="double_bottom": return
    if is_buy and vp["buy_pct"]<55: return
    if not is_buy and vp["sell_pct"]<55: return

    ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=60)
    if not ob: ob=(min(l[-15:]),max(h[-15:]))
    entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol,crt_pct=get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,big_range_pct,s,crt_low,crt_high)
    min_rr1=1.0 if is_vol else 1.2
    min_rr2=1.8 if is_vol else 2.0
    if rr1<min_rr1 or rr1>8.0: return
    if rr2<min_rr2: return

    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top_level,"entry":entry}; save()
    LAST_TOP[f"{s}_{side}"]=(top_level,now)
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0}; save_active()
    vol_tag="10% VOL" if is_vol else "4% STABLE"
    color="🟢" if is_buy else "🔴"
    fbs_l="FBS 62%" if is_buy else "FBS 38%"
    tg(f"{color} {s} {side} {fbs_l} STRONG | {crt_type} {crt_pct:.1f}% | 5m TBS | Foundation+Climb | {vol_tag} | {time_12hr}\nPrice: {live_price:.6f} Entry: {entry:.6f} (OB) SL: {sl:.6f} TP1 {tp1:.6f} ({rr1:.1f}R) TP2 {tp2:.6f} TP3 {tp3:.6f}")

print("=== BOT V33 PERFECT MONEY - DOM FILTER ALIGNED ===",flush=True)
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
