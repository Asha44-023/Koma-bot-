# BOT V33.7 FINAL PER-COIN PRO - 15m FBS=VOLUME + GRAB vs REVERSAL + PER-COIN TP/SL + STRATEGIC COOLDOWN
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {
    "GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT",
    "SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT",
}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
FAST_SYMS = ["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"]
SLOW_SYMS = ["SANDUSDT","TAOUSDT","JASMYUSDT"]

# === PER-COIN BEST TP/SL BASED ON HOW EACH COIN PLAYS ===
PER_COIN_TP = {
    # ULTRA VOLATILE - needs big TP, bigger SL
    "FARTCOINUSDT": {"tp1":0.05, "tp2":0.09, "tp3":0.14, "sl_grab":0.02, "sl_rev":0.035, "sl_bos":0.025},
    "GRASSUSDT": {"tp1":0.04, "tp2":0.08, "tp3":0.12, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    "KOMAUSDT": {"tp1":0.04, "tp2":0.08, "tp3":0.12, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    # MEDIUM VOLATILE
    "SENTUSDT": {"tp1":0.035, "tp2":0.065, "tp3":0.10, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    # STABLE - needs small TP or never hits
    "SANDUSDT": {"tp1":0.018, "tp2":0.035, "tp3":0.055, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
    "TAOUSDT": {"tp1":0.02, "tp2":0.04, "tp3":0.065, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
    "JASMYUSDT": {"tp1":0.018, "tp2":0.038, "tp3":0.06, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
}

DOM_SENSITIVITY = {"FARTCOINUSDT":2.5,"GRASSUSDT":2.2,"KOMAUSDT":2.0,"SENTUSDT":1.6,"SANDUSDT":1.3,"TAOUSDT":1.1,"JASMYUSDT":1.2}
BTC_DOM_CACHE = {"value":58.5,"history":[],"last_fetch":0}

def get_btc_dominance():
    now=time.time()
    if now - BTC_DOM_CACHE["last_fetch"] < 300: return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]
    try:
        r=requests.get("https://api.coingecko.com/api/v3/global",timeout=10).json()
        btc_d=r["data"]["market_cap_percentage"]["btc"]
        BTC_DOM_CACHE["value"]=btc_d; BTC_DOM_CACHE["history"].append((now,btc_d))
        BTC_DOM_CACHE["history"]=[(t,v) for t,v in BTC_DOM_CACHE["history"] if now-t<14400]
        BTC_DOM_CACHE["last_fetch"]=now; return btc_d, BTC_DOM_CACHE["history"]
    except: return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]

def check_btc_dominance_filter(symbol,is_buy):
    btc_d,hist=get_btc_dominance()
    if len(hist)<2: return True
    change=btc_d-hist[0][1]; eff=change*DOM_SENSITIVITY.get(symbol,1.0)
    if change>=0.6 and eff>=0.9 and is_buy: print(f"⛔ DOM +{change:.2f}% BLOCK BUY {symbol}",flush=True); return False
    if change<=-0.6 and eff<=-0.9 and not is_buy: print(f"⛔ DOM {change:.2f}% BLOCK SELL {symbol}",flush=True); return False
    if btc_d>60.5 and DOM_SENSITIVITY.get(symbol,1.0)>=2.0 and is_buy: return False
    if btc_d<54.0 and DOM_SENSITIVITY.get(symbol,1.0)>=2.0 and not is_buy: return False
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
            is_engulf=(is_buy and c[i]>o[i] and c[i-1]<o[i-1]) or (not is_buy and c[i]<o[i] and c[i-1]>o[i-1])
            near_edge=(is_buy and l[i]<=crt_low*1.015) or (not is_buy and h[i]>=crt_high*0.985)
            if (is_doji or is_engulf) and near_edge: return True
        except: pass
    return False

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p75=pl+prange*0.75; p62=pl+prange*0.62; p38=pl+prange*0.38; p25=pl+prange*0.25
    big_range_pct=(ph-pl)/(pl or 1)*100
    body=abs(pc-po); upper_wick=ph-max(pc,po); lower_wick=min(pc,po)-pl
    if pc>po and upper_wick>body*1.5 and cc<p75: return "WEAK_BULL_TRAP",ph,big_range_pct
    if pc<po and lower_wick>body*1.5 and cc>p25: return "WEAK_BEAR_TRAP",pl,big_range_pct
    if pc>=p62 and cc>=p38 and cl>=p25 and cc>co: return "BOS_UP_STRONG",ph,big_range_pct
    if pc<=p38 and cc<=p62 and ch<=p75 and cc<co: return "BOS_DOWN_STRONG",pl,big_range_pct
    return None,0,big_range_pct

def fbs_trend_pump_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p75=pl+prange*0.75; p68=pl+prange*0.68; p32=pl+prange*0.32; p25=pl+prange*0.25
    big_range_pct=(ph-pl)/(pl or 1)*100
    if pc>po:
        if cc < p75 and cc < co: return "WEAK_BULL_TRAP_TREND",ph,big_range_pct
        if pc >= p68 and cc >= p32 and cc > p25 and cc > co: return "BOS_UP_TREND_STRONG_32_68",ph,big_range_pct
    if pc<po:
        if cc > p25 and cc > co: return "WEAK_BEAR_TRAP_TREND",pl,big_range_pct
        if pc <= p32 and cc <= p68 and cc < p75 and cc < co: return "BOS_DOWN_TREND_STRONG_32_68",pl,big_range_pct
    return None,0,big_range_pct

def is_steady_trend_pump(h,l,c,o,v):
    if len(c)<20: return False
    up=sum(1 for i in range(-12,-1) if c[i]>c[i-1]); down=sum(1 for i in range(-12,-1) if c[i]<c[i-1])
    avg_body=sum(abs(c[i]-o[i]) for i in range(-12,-1))/12
    avg_range=sum(h[i]-l[i] for i in range(-12,-1))/12 or 1e-9
    return (up>=6 or down>=6) and avg_body/avg_range>0.52

def build_crt(symbol,h,l):
    look=min(48,len(h)) if symbol in FAST_SYMS else min(288,len(h))
    crt_type="4H CRT" if symbol in FAST_SYMS else "Day CRT"
    return min(l[-look:]), max(h[-look:]), crt_type

def check_tbs(o,h,l,c,crt_low,crt_high,is_buy):
    if len(c)<3: return False
    if is_buy: return l[-2]<crt_low and c[-1]>crt_low and c[-1]>o[-1]
    else: return h[-2]>crt_high and c[-1]<crt_high and c[-1]<o[-1]

def pattern(h,l):
    tops=[]; bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]: tops.append((i,h[i]))
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]: bots.append((i,l[i]))
    if len(tops)>=2 and abs(tops[-1][1]-tops[-2][1])/tops[-2][1]<0.008: return "double_top"
    if len(bots)>=2 and abs(bots[-1][1]-bots[-2][1])/bots[-2][1]<0.008: return "double_bottom"
    return "none"

def get_last_ob(o,h,l,c,bullish=True,lookback=60):
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2,len(c)-lookback,-1):
        if bullish and c[i]<o[i] and c[i+1]>o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: return (l[i],h[i])
        if not bullish and c[i]>o[i] and c[i+1]<o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: return (l[i],h[i])
    return None

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,big_range_pct,symbol,crt_low,crt_high,setup_type):
    ob_low,ob_high=ob; prange=ob_high-ob_low
    crt_range_pct=(crt_high-crt_low)/(crt_low or 1)*100
    is_volatile=symbol in FAST_SYMS or big_range_pct>2.5
    coin_cfg = PER_COIN_TP.get(symbol, PER_COIN_TP["GRASSUSDT"])

    # PER-COIN BASE + CRT ADAPTIVE
    if setup_type=="LIQUIDITY_GRAB_CONTINUATION":
        sl_pct=coin_cfg["sl_grab"]
        tp1_pct=max(coin_cfg["tp1"], crt_range_pct*0.45/100)
        tp2_pct=max(coin_cfg["tp2"], crt_range_pct*0.85/100)
        tp3_pct=max(coin_cfg["tp3"], crt_range_pct*1.30/100)
    elif setup_type=="REVERSAL":
        sl_pct=coin_cfg["sl_rev"]
        tp1_pct=max(coin_cfg["tp1"]*0.85, crt_range_pct*0.35/100) # tighter for reversal
        tp2_pct=max(coin_cfg["tp2"]*0.85, crt_range_pct*0.65/100)
        tp3_pct=max(coin_cfg["tp3"]*0.85, crt_range_pct*1.0/100)
    else: # BOS_CONTINUATION
        sl_pct=coin_cfg["sl_bos"]
        tp1_pct=max(coin_cfg["tp1"], crt_range_pct*0.40/100)
        tp2_pct=max(coin_cfg["tp2"], crt_range_pct*0.75/100)
        tp3_pct=max(coin_cfg["tp3"], crt_range_pct*1.15/100)

    if is_buy:
        entry=ob_low+prange*(0.56 if is_volatile else 0.44)
        sl=entry*(1-sl_pct); tp1=entry*(1+tp1_pct); tp2=entry*(1+tp2_pct); tp3=entry*(1+tp3_pct)
    else:
        entry=ob_high-prange*(0.56 if is_volatile else 0.44)
        sl=entry*(1+sl_pct); tp1=entry*(1-tp1_pct); tp2=entry*(1-tp2_pct); tp3=entry*(1-tp3_pct)
    risk=abs(entry-sl); rr1=abs(tp1-entry)/(risk or 1e-9); rr2=abs(tp2-entry)/(risk or 1e-9); rr3=abs(tp3-entry)/(risk or 1e-9)
    return entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_volatile,crt_range_pct

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<60: return
    now=time.time(); time_12hr=get_time_12hr(); live_price=c[-1]
    buy_key=f"{s}_BUY"; sell_key=f"{s}_SELL"
    crt_low,crt_high,crt_type=build_crt(s,d15["h"],d15["l"])

    # STRATEGIC 1: ACTIVE BLOCK - no double message while in trade
    if buy_key in ACTIVE or sell_key in ACTIVE:
        active_key=buy_key if buy_key in ACTIVE else sell_key
        is_active_buy=ACTIVE[active_key]["is_buy"]
        fbs15,_br,_=fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        if not fbs15: fbs15,_br,_=fbs_trend_pump_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        profit=(c[-1]-ACTIVE[active_key]["entry"])/ACTIVE[active_key]["entry"]*100 if is_active_buy else (ACTIVE[active_key]["entry"]-c[-1])/ACTIVE[active_key]["entry"]*100
        if fbs15 and ("UP" in fbs15 if is_active_buy else "DOWN" in fbs15) and "STRONG" in fbs15:
            if profit-ACTIVE[active_key].get("last_hold_profit",0)>= (2.0 if s in FAST_SYMS else 1.0):
                tg(f"🟡 {s} HOLD {'BUY' if is_active_buy else 'SELL'} +{profit:.2f}% | {time_12hr} 15m {fbs15} {crt_type}")
                ACTIVE[active_key]["last_hold_profit"]=profit; save_active()
        if fbs15 and ("DOWN" in fbs15 if is_active_buy else "UP" in fbs15) and "STRONG" in fbs15:
            if check_tbs(o,h,l,c,crt_low,crt_high,not is_active_buy) and check_btc_dominance_filter(s, not is_active_buy):
                ob=get_last_ob(o,h,l,c,bullish=not is_active_buy,lookback=60) or (min(l[-15:]),max(h[-15:]))
                entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol,crt_pct=get_perfect_entry_sl_tp(o,h,l,c,ob,not is_active_buy,0,s,crt_low,crt_high,"REVERSAL")
                if rr1>=1.0 and rr1<=8:
                    tg(f"<b>REVERSAL CLOSE {s}</b> {profit:+.2f}% {time_12hr} | 15m {fbs15} {crt_type}")
                    del ACTIVE[active_key]; save_active()
                    key=f"{s}_{'SELL' if is_active_buy else 'BUY'}"
                    COOLDOWN["signals"][key]={"t":now,"dir":not is_active_buy,"top":0,"entry":entry}; save()
                    LAST_TOP[key]=(0,now)
                    ACTIVE[key]={"entry":entry,"is_buy":not is_active_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0,"setup":"REVERSAL"}; save_active()
                    tg(f"{'🔴' if not is_active_buy else '🟢'} {s} REVERSAL {fbs15} | {crt_type} CRT {crt_pct:.1f}% | SL {sl:.6f} TP1 {tp1:.6f} ({rr1:.1f}R)")
                    return
        if is_active_buy and c[-1]>ACTIVE[active_key].get("highest",0): ACTIVE[active_key]["highest"]=c[-1]; save_active()
        if not is_active_buy and c[-1]<ACTIVE[active_key].get("lowest",999999): ACTIVE[active_key]["lowest"]=c[-1]; save_active()
        return

    # 15m FBS PRIMARY = VOLUME
    fbs15, top15, brp15 = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
    if not fbs15 or "STRONG" not in fbs15:
        fbs15, top15, brp15 = fbs_trend_pump_logic(d15["h"],d15["l"],d15["c"],d15["o"])
    if not fbs15 or "STRONG" not in fbs15: return

    is_buy="UP" in fbs15; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"

    # STRATEGIC 2: LEVEL DUPLICATE BLOCK - no same level spam
    if key in LAST_TOP:
        last_top,last_time=LAST_TOP[key]
        if last_top!=0 and abs(top15-last_top)/(last_top or 1)<0.008 and (now-last_time)< (8*3600 if s in FAST_SYMS else 24*3600): return

    # STRATEGIC 3: TIME COOLDOWN
    SAME_CD=150*60 if s in FAST_SYMS else 8*3600
    OPP_CD=90*60 if s in FAST_SYMS else 4*3600
    if now-COOLDOWN["signals"].get(key,{}).get("t",0)<SAME_CD: return
    if now-COOLDOWN["signals"].get(f"{s}_{'SELL' if is_buy else 'BUY'}",{}).get("t",0)<OPP_CD: return

    if not detect_foundation(d15["o"],d15["h"],d15["l"],d15["c"],is_buy,crt_low,crt_high):
        if "TREND" not in fbs15 or not is_steady_trend_pump(d15["h"],d15["l"],d15["c"],d15["o"],d15["v"]): return

    if not check_tbs(o,h,l,c,crt_low,crt_high,is_buy): return
    if not check_btc_dominance_filter(s,is_buy): return
    pat=pattern(d15["h"],d15["l"])
    if is_buy and pat=="double_top": return
    if not is_buy and pat=="double_bottom": return

    # GRAB vs REVERSAL
    setup_type="BOS_CONTINUATION"
    if is_buy and l[-2]<crt_low*0.998 and fbs15=="BOS_UP_TREND_STRONG_32_68": setup_type="LIQUIDITY_GRAB_CONTINUATION"
    if not is_buy and h[-2]>crt_high*1.002 and fbs15=="BOS_DOWN_TREND_STRONG_32_68": setup_type="LIQUIDITY_GRAB_CONTINUATION"
    if pat in ["double_top","double_bottom"]: setup_type="REVERSAL"

    ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=60) or (min(l[-15:]),max(h[-15:]))
    entry,sl,tp1,tp2,tp3,rr1,rr2,rr3,is_vol,crt_pct=get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,brp15,s,crt_low,crt_high,setup_type)
    if rr1<1.0 or rr1>8 or rr2<1.8: return

    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top15,"entry":entry}; save()
    LAST_TOP[key]=(top15,now)
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0,"setup":setup_type}; save_active()
    tag="GRAB CONTINUES" if "GRAB" in setup_type else ("REVERSAL" if setup_type=="REVERSAL" else "BOS")
    cfg=PER_COIN_TP[s]
    tg(f"{'🟢' if is_buy else '🔴'} {s} {side} {tag} | {fbs15} | 15m FBS=VOLUME | {crt_type} {crt_pct:.1f}% | 5m TBS Entry | {time_12hr}\nPrice: {live_price:.6f}\nEntry: {entry:.6f} (OB {ob[0]:.6f}-{ob[1]:.6f})\nSL: {sl:.6f} ({abs(entry-sl)/entry*100:.2f}% {setup_type}) Per-Coin: GRAB {cfg['sl_grab']*100:.1f}% / REV {cfg['sl_rev']*100:.1f}%\nTP1: {tp1:.6f} ({rr1:.1f}R) TP2: {tp2:.6f} ({rr2:.1f}R) TP3: {tp3:.6f} ({rr3:.1f}R)\nPer-Coin Base: {cfg['tp1']*100:.1f}% / {cfg['tp2']*100:.1f}% / {cfg['tp3']*100:.1f}% | CRT adaptive {crt_pct*0.45:.1f}% | Setup: {setup_type} | Pattern: {pat}")

print("=== BOT V33.7 FINAL PER-COIN PRO ===",flush=True)
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
