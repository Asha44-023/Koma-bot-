# BOT V30.8 - PER IMAGE 62/38 DUAL-TF REVERSAL - TP1 1H / TP2 Daily - RR 1.5-8
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {"GRASSUSDT":"GRASS_USDT","TAOUSDT":"TAO_USDT","SANDUSDT":"SAND_USDT","SENTUSDT":"SENT_USDT","FARTCOINUSDT":"FARTCOIN_USDT","JASMYUSDT":"JASMY_USDT","KOMAUSDT":"KOMA_USDT",}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
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

COOLDOWN_NORMAL=120*60; COOLDOWN_SAME_LIQ=60*60

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
    if len(c)<3: return None,0
    ph,pl,po,pc = h[-2],l[-2],o[-2],c[-2]
    cc,co = c[-1],o[-1]
    prange = ph-pl
    if prange==0: return None,0
    p62 = pl + prange*0.62
    p38 = pl + prange*0.38
    if pc > po and cc > co:
        if pc >= p62 and cc > ph: return "BOS_UP_STRONG", ph
    if pc < po and cc < co:
        if pc <= p38 and cc < pl: return "BOS_DOWN_STRONG", pl
    return None,0

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

def get_daily_levels(perp):
    try:
        d1=kl(perp,"Day1")
        if d1 and len(d1["h"])>=2 and d1["h"][-2]>0: return d1["h"][-2],d1["l"][-2]
    except: pass
    return None,None

def get_1h_levels(perp):
    try:
        h1=kl(perp,"Min60")
        if h1 and len(h1["h"])>=24: return max(h1["h"][-24:]), min(h1["l"][-24:])
    except: pass
    return None,None

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,perp=None):
    ob_low,ob_high=ob; entry=(ob_low+ob_high)/2
    daily_high,daily_low=get_daily_levels(perp) if perp else (None,None)
    h1_high,h1_low=get_1h_levels(perp) if perp else (None,None)
    if is_buy:
        sl=min(min(l[-7:]),ob_low)*0.997
        if h1_high and h1_high > entry: tp1=h1_high*1.002
        else: tp1=max(h[-20:])*1.005
        tp2=daily_high*1.012 if daily_high and daily_high>tp1 else tp1*1.015
        tp1=max(tp1,entry*1.006)
        tp2=max(tp2,tp1*1.008)
    else:
        sl=max(max(h[-7:]),ob_high)*1.003
        if h1_low and h1_low < entry: tp1=h1_low*0.998
        else: tp1=min(l[-20:])*0.995
        tp2=daily_low*0.988 if daily_low and daily_low<tp1 else tp1*0.985
        tp1=min(tp1,entry*0.994)
        tp2=min(tp2,tp1*0.992)
    risk=abs(entry-sl); rr1=abs(tp1-entry)/(risk or 1e-9); rr2=abs(tp2-entry)/(risk or 1e-9)
    return entry,sl,tp1,tp2,rr1,rr2

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    if get_session()[0]=="OFF": return
    now=time.time()
    buy_key=f"{s}_BUY"; sell_key=f"{s}_SELL"

    if buy_key in ACTIVE:
        fbs_res,_ = fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if fbs_res and "DOWN" in fbs_res:
            fbs_15,_ = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "DOWN" in fbs_15:
                tg(f"⚠️ <b>REVERSAL {s}</b> 🔴 38% BREAKDOWN per image (5m+15m)\nClose BUY {c[-1]:.6f}")
                del ACTIVE[buy_key]; save_active(); return
        prev_high=ACTIVE[buy_key].get("highest", ACTIVE[buy_key]["entry"])
        if c[-1] > prev_high and fbs_res and "UP" in fbs_res:
            profit=(c[-1]-ACTIVE[buy_key]["entry"])/ACTIVE[buy_key]["entry"]*100
            tg(f"💎 <b>HOLD BUY {s}</b> | +{profit:.2f}%\nNew high {c[-1]:.6f} 🟢")
            ACTIVE[buy_key]["highest"]=c[-1]; save_active()
        return

    if sell_key in ACTIVE:
        fbs_res,_ = fbs_image_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if fbs_res and "UP" in fbs_res:
            fbs_15,_ = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
            if fbs_15 and "UP" in fbs_15:
                tg(f"⚠️ <b>REVERSAL {s}</b> 🟢 62% BREAKOUT per image (5m+15m)\nClose SELL {c[-1]:.6f}")
                del ACTIVE[sell_key]; save_active(); return
        prev_low=ACTIVE[sell_key].get("lowest", ACTIVE[sell_key]["entry"])
        if c[-1] < prev_low and fbs_res and "DOWN" in fbs_res:
            profit=(ACTIVE[sell_key]["entry"]-c[-1])/ACTIVE[sell_key]["entry"]*100
            tg(f"💎 <b>HOLD SELL {s}</b> | +{profit:.2f}%\nNew low {c[-1]:.6f} 🔴")
            ACTIVE[sell_key]["lowest"]=c[-1]; save_active()
        return

    fbs_res=None; top_level=0; tf_used=""
    for tf_data,tf_name in [(d5,"5m"),(d15,"15m")]:
        res,top=fbs_image_logic(tf_data["h"],tf_data["l"],tf_data["c"],tf_data["o"])
        if res: fbs_res=res; top_level=top; tf_used=tf_name; break
    if not fbs_res: return

    vp=volume_pressure(o,h,l,c,v); pat=pattern(d5["h"],d5["l"])
    is_buy="UP" in fbs_res; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"

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
    entry,sl,tp1,tp2,rr1,rr2=get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy,perp=p)

    if rr1 < 1.5 or rr1 > 8.0: return
    if rr2 < 2.0: return

    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top_level,"entry":entry,"tp1":tp1,"tp2":tp2}; save()
    LAST_TOP[f"{s}_{side}"]=(top_level,now)
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl,"highest":entry,"lowest":entry}; save_active()

    if is_buy: tg(f"🟢 <b>BUY {s}</b> | 62% ({tf_used})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 1H {tp1:.6f} ({rr1:.1f}R) | TP2 D {tp2:.6f} ({rr2:.1f}R)")
    else: tg(f"🔴 <b>SELL {s}</b> | 38% ({tf_used})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 1H {tp1:.6f} ({rr1:.1f}R) | TP2 D {tp2:.6f} ({rr2:.1f}R)")

print("=== BOT V30.8 PER IMAGE DUAL-TF ===",flush=True)
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
