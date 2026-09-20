# V26.3 FIXED FINAL - BOTH WAYS ALL SESSIONS BSL/SSL ERL 15/30/5
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOL_MAP = {
    "GRASSUSDT": "GRASS_USDT", "TAOUSDT": "TAO_USDT", "SANDUSDT": "SAND_USDT",
    "SENTUSDT": "SENT_USDT", "FARTCOINUSDT": "FARTCOIN_USDT",
    "JASMYUSDT": "JASMY_USDT", "KOMAUSDT": "KOMA_USDT",
}
SYMBOLS = list(SYMBOL_MAP.keys())
PERPS = list(SYMBOL_MAP.values())
COOLDOWN_FILE="cooldown.json"
COOLDOWN={"signals":{}}
if os.path.exists(COOLDOWN_FILE):
    try:
        d=json.load(open(COOLDOWN_FILE))
        # auto clear old format
        if d.get("signals") and len(d["signals"])>0:
            k=list(d["signals"].keys())[0]
            if "_" not in k: d={"signals":{}}
        COOLDOWN=d
    except: COOLDOWN={"signals":{}}
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
STATS={"touched":0,"almost":0,"sniper":0,"xxx":0}
def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass
ACTIVE={}
COOLDOWN_NORMAL=15*60
COOLDOWN_AFTER_SL=30*60
COOLDOWN_AFTER_TP2=5*60

def get_session():
    h=datetime.now(ZoneInfo("UTC")).hour
    if 0<=h<7: return "ASIAN","🟡"
    if 7<=h<12: return "LONDON","🔵"
    if 12<=h<21: return "NY","🟢"
    return "OFF","⚫"

def kl(sym, interval):
    try:
        r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}", params={"interval":interval}, timeout=10).json()
        data=r.get("data",[])
        if not data: return None
        if isinstance(data, dict):
            def f(x):
                try: return float(x)
                except: return 0.0
            return {"o":[f(x) for x in data.get("open",[])], "h":[f(x) for x in data.get("high",[])], "l":[f(x) for x in data.get("low",[])], "c":[f(x) for x in data.get("close",[])], "v":[f(x) for x in data.get("vol",[])]}
        o,h,l,c,v=[],[],[],[],[]
        for k in data: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
        return {"o":o,"h":h,"l":l,"c":c,"v":v}
    except Exception as e: print(f"kl err {sym} {e}", flush=True); return None

def ema(vals,n):
    if not vals: return 0
    k=2/(n+1); e=vals[0]
    for v in vals[1:]: e=v*k+e*(1-k)
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
    if side=="BUY":
        lvl=min(l[-6:-1]); swept=c[-2]<lvl*0.997; back=c[-1]>lvl and c[-1]>o[-1]
        dist=(lvl-min(l[-2],l[-3]))/lvl*100 if swept else 0
        return swept and back and 0.1<=dist<=1.0
    else:
        lvl=max(h[-6:-1]); swept=c[-2]>lvl*1.003; back=c[-1]<lvl and c[-1]<o[-1]
        dist=(max(h[-2],h[-3])-lvl)/lvl*100 if swept else 0
        return swept and back and 0.1<=dist<=1.0

def detect_deep_WM(h,l,side):
    if len(h)<8: return False
    if side=="BUY":
        _,lows=swing_points(h,l,look=2)
        if len(lows)<2: return False
        return lows[-1][1]<lows[-2][1] and (lows[-2][1]-lows[-1][1])/lows[-2][1]*100>=0.10
    else:
        highs,_=swing_points(h,l,look=2)
        if len(highs)<2: return False
        return highs[-1][1]>highs[-2][1] and (highs[-1][1]-highs[-2][1])/highs[-2][1]*100>=0.10

def detect_xxx_sweep(lows,cur):
    if len(lows)<2: return False
    return abs(lows[-2][1]-lows[-1][1])/lows[-2][1]<0.003 and cur<min(lows[-2][1],lows[-1][1])*0.997

def detect_xxx_sweep_high(highs,cur):
    if len(highs)<2: return False
    return abs(highs[-2][1]-highs[-1][1])/highs[-2][1]<0.003 and cur>max(highs[-2][1],highs[-1][1])*1.003

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

def get_fvgs(h,l,lookback=50):
    fvgs=[]
    for i in range(max(2,len(h)-lookback),len(h)-1):
        if l[i]>h[i-2]: fvgs.append(('bull',h[i-2],l[i]))
        if h[i]<l[i-2]: fvgs.append(('bear',l[i-2],h[i]))
    return fvgs

def get_last_ob(o,h,l,c,bullish=True,lookback=50):
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    for i in range(len(c)-2, len(c)-lookback, -1):
        body=c[i+1]-o[i+1]
        is_impulse=abs(body)>atr*0.3 if atr else True
        if bullish:
            if c[i]<o[i] and is_impulse and c[i+1]>o[i+1]: return (l[i],h[i])
        else:
            if c[i]>o[i] and is_impulse and c[i+1]<o[i+1]: return (l[i],h[i])
    return None

def volume_pressure(o,h,l,c,v,n=20):
    if len(v)<n: return {"vol_x":1,"buy_pct":50,"sell_pct":50}
    avg=statistics.mean(v[-n:]); cur=v[-1]; bp=sp=0
    for i in range(-n,0):
        rng=h[i]-l[i] or 1e-9; delta=(c[i]-o[i])/rng*v[i]
        if delta>0: bp+=delta
        else: sp+=-delta
    total=bp+sp or 1
    return {"vol_x":cur/(avg or 1),"buy_pct":bp/total*100,"sell_pct":sp/total*100}

def detect_strong_candles(o,h,l,c):
    if len(c)<3: return {"buy":False,"sell":False,"name":"none"}
    prev_o,prev_c=o[-2],c[-2]; cur_o,cur_c=o[-1],c[-1]
    c1_o,c1_c=o[-3],c[-3]
    body_cur=abs(cur_c-cur_o)+1e-9; body_prev=abs(prev_c-prev_o)+1e-9
    bullish_engulfing=prev_c<prev_o and cur_c>cur_o and cur_c>prev_o and body_cur>body_prev*0.6
    morning_star=c1_c<c1_o and cur_c>cur_o and cur_c>(c1_o+c1_c)/2
    bullish_harami=prev_c<prev_o and cur_c>cur_o and cur_o>prev_c and cur_c<prev_o
    bearish_engulfing=prev_c>prev_o and cur_c<cur_o and cur_c<prev_o and body_cur>body_prev*0.6
    evening_star=c1_c>c1_o and cur_c<cur_o and cur_c<(c1_o+c1_c)/2
    bearish_harami=prev_c>prev_o and cur_c<cur_o and cur_o<prev_c and cur_c>prev_o
    buy=bullish_engulfing or morning_star or bullish_harami
    sell=bearish_engulfing or evening_star or bearish_harami
    name="BULL_HARAMI" if bullish_harami else "BULLISH_ENGULFING" if bullish_engulfing else "MORNING_STAR" if morning_star else "BEAR_HARAMI" if bearish_harami else "BEARISH_ENGULFING" if bearish_engulfing else "EVENING_STAR" if evening_star else "none"
    return {"buy":buy,"sell":sell,"name":name}

def market_state(c,vp):
    e20=ema(c,20); price=c[-1]
    rng=max(c[-10:])-min(c[-10:]); atr=statistics.mean([abs(c[i]-c[i-1]) for i in range(-14,0)]) or 1e-9
    consolidating=rng<atr*3
    if consolidating and vp["vol_x"]<1.5: return "CONSOLIDATING"
    if price>e20 and vp["buy_pct"]>60 and vp["vol_x"]>1.1: return "PUMPING"
    if price<e20 and vp["sell_pct"]>60 and vp["vol_x"]>1.1: return "DUMPING"
    return "TRENDING"

def get_bsl_ssl_auto(h,l,c,is_buy):
    highs,lows=swing_points(h,l,look=2); price=c[-1]
    if is_buy:
        above=[x[1] for x in highs if x[1]>price*1.005]
        if not above: above=[max(h[-20:])*1.01]
        above=sorted(set(above)); bsl1=above[0]; bsl2=above[1] if len(above)>1 else above[0]*1.012
        return bsl1,bsl2
    else:
        below=[x[1] for x in lows if x[1]<price*0.995]
        if not below: below=[min(l[-20:])*0.99]
        below=sorted(set(below),reverse=True); ssl1=below[0]; ssl2=below[1] if len(below)>1 else below[0]*0.988
        return ssl1,ssl2

def full_scan(s,p):
    d5=kl(p,"Min5"); d15=kl(p,"Min15"); h1=kl(p,"Min60")
    if not d5 or not d15 or not h1: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    price=c[-1]
    session_name,session_emoji=get_session()
    bos=detect_bos(d5["h"],d5["l"],d5["c"]) or detect_bos(d15["h"],d15["l"],d15["c"])
    pat=pattern(d5["h"],d5["l"])
    if pat=="none": pat=pattern(d15["h"],d15["l"])
    highs_5,lows_5=swing_points(d5["h"],d5["l"])
    vp=volume_pressure(o,h,l,c,v)
    state=market_state(c,vp)
    fvgs=get_fvgs(h1["h"],h1["l"])
    has_fvg_bull=any(f[0]=='bull' for f in fvgs[-10:])
    has_fvg_bear=any(f[0]=='bear' for f in fvgs[-10:])

    for is_buy in [True,False]:
        side="BUY" if is_buy else "SELL"
        key=f"{s}_{side}"; now=time.time(); prev=COOLDOWN["signals"].get(key,{}); elapsed=now-prev.get("t",0)
        last_result=prev.get("result","normal")
        cd_need=COOLDOWN_NORMAL
        if last_result=="SL": cd_need=COOLDOWN_AFTER_SL
        if last_result=="TP2": cd_need=COOLDOWN_AFTER_TP2
        if vp["vol_x"]>1.8: cd_need=min(cd_need,10*60)
        if elapsed<cd_need: continue

        # BOS + PATTERN - MUST HAVE ONE
        if is_buy:
            if pat not in ["double_bottom","triple_bottom"] and bos!="BOS_UP": continue
        else:
            if pat not in ["double_top","triple_top"] and bos!="BOS_DOWN": continue

        out_in=detect_out_in(o,h,l,c,side)
        deep=detect_deep_WM(h,l,side)
        sweep_low=detect_xxx_sweep(lows_5,l[-1]) if lows_5 else False
        sweep_high=detect_xxx_sweep_high(highs_5,h[-1]) if highs_5 else False
        sweep_ok=sweep_low if is_buy else sweep_high
        if not (out_in or deep or sweep_ok): continue
        STATS["xxx"]+=1

        ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=50)
        if not ob: continue
        ob_low,ob_high=ob
        # FIX: allow NEAR OB not just INSIDE
        if is_buy:
            in_ob = ob_low*0.985 <= price <= ob_high*1.015
            near_ob = abs(price-ob_high)/price < 0.03
            if not (in_ob or near_ob): continue
        else:
            in_ob = ob_low*0.985 <= price <= ob_high*1.015
            near_ob = abs(price-ob_low)/price < 0.03
            if not (in_ob or near_ob): continue
        STATS["touched"]+=1

        candles=detect_strong_candles(o,h,l,c)
        if is_buy and not candles["buy"]:
            STATS["almost"]+=1; continue
        if not is_buy and not candles["sell"]:
            STATS["almost"]+=1; continue

        if is_buy and vp["buy_pct"]<40: continue
        if not is_buy and vp["sell_pct"]<40: continue
        if vp["vol_x"]<0.65: continue

        trs=[max(h[i]-l[i],abs(h[i]-c[i-1])) for i in range(-14,0)]
        atr=sum(trs)/len(trs) if trs else price*0.01
        risk=min(atr*1.5,price*0.035)
        sl=price-risk if is_buy else price+risk
        auto_tp1,auto_tp2=get_bsl_ssl_auto(d5["h"],d5["l"],d5["c"],is_buy)
        min_tp=price*0.006
        if is_buy:
            if auto_tp1<price+min_tp: auto_tp1=price+min_tp
            if auto_tp2<price+min_tp*1.5: auto_tp2=price+min_tp*1.5
        else:
            if auto_tp1>price-min_tp: auto_tp1=price-min_tp
            if auto_tp2>price-min_tp*1.5: auto_tp2=price-min_tp*1.5
        rr1=abs(auto_tp1-price)/(risk or 1e-9); rr2=abs(auto_tp2-price)/(risk or 1e-9)
        if rr2<1.0: continue

        COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"normal"}; save()
        ACTIVE[s]={"entry":price,"is_buy":is_buy,"t":now,"atr":atr,"perp":p,"tp1":auto_tp1,"tp2":auto_tp2,"sl":sl,"side_key":key}
        STATS["sniper"]+=1
        nai=datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
        tag=[]
        if out_in: tag.append("OUT&IN")
        if deep: tag.append(f"Deep{'W' if is_buy else 'M'}")
        if sweep_ok: tag.append("XXX")
        if has_fvg_bull and is_buy: tag.append("FVG")
        if has_fvg_bear and not is_buy: tag.append("FVG")
        sweep_txt="+".join(tag) or "SNIPER"
        fvg_icon="✅FVG" if (has_fvg_bull and is_buy) or (has_fvg_bear and not is_buy) else "NO-FVG"
        tg(f"{session_emoji} {'🟢' if is_buy else '🔴'} <b>{s} {'BUY' if is_buy else 'SELL'} V26.3 {session_name} {sweep_txt}</b> [{state}] {fvg_icon}\n"
           f"{bos or ''} {pat} + {candles['name']}\n"
           f"Vol {vp['vol_x']:.2f}x Buy {vp['buy_pct']:.0f}% \n"
           f"OB {ob_low:.5f}-{ob_high:.5f} Price: {price}\n"
           f"SL:{sl:.6f} TP1:{auto_tp1:.6f}({rr1:.1f}R) TP2:{auto_tp2:.6f}({rr2:.1f}R) ERL\n"
           f"[{nai}] CD:{cd_need//60}m | T:{STATS['touched']} S:{STATS['sniper']}")

def check_exits():
    now=time.time()
    for s in list(ACTIVE.keys()):
        pos=ACTIVE[s]; p=pos.get("perp",SYMBOL_MAP.get(s,s)); d=kl(p,"Min1")
        if not d: continue
        cur=d["c"][-1]; entry=pos["entry"]; is_buy=pos["is_buy"]
        sl=pos.get("sl",entry*0.99 if is_buy else entry*1.01); tp1=pos.get("tp1",entry*1.01); tp2=pos.get("tp2",entry*1.015); key=pos.get("side_key",s)
        if is_buy:
            if cur>=tp2: tg(f"🎯 TP2 HIT {s} ERL"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"TP2"}; save(); ACTIVE.pop(s); continue
            if cur>=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 TP1 HIT {s} -> SL BE"); pos["sl"]=entry
            if cur<=sl: tg(f"🛑 SL HIT {s}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"SL"}; save(); ACTIVE.pop(s); continue
        else:
            if cur<=tp2: tg(f"🎯 TP2 HIT {s} ERL"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"TP2"}; save(); ACTIVE.pop(s); continue
            if cur<=tp1 and not pos.get("tp1_hit"): pos["tp1_hit"]=True; tg(f"🎯 TP1 HIT {s} -> SL BE"); pos["sl"]=entry
            if cur>=sl: tg(f"🛑 SL HIT {s}"); COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"SL"}; save(); ACTIVE.pop(s); continue
        if now-pos["t"]>30*60: tg(f"⏰ TIMEOUT {s}"); ACTIVE.pop(s)

print("=== BOT V26.3 FIXED - NEAR OB + FVG BONUS ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"FINAL STATS T:{STATS['touched']} ALMOST:{STATS['almost']} SNIPER:{STATS['sniper']} XXX:{STATS['xxx']} ACTIVE:{list(ACTIVE.keys())}", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(f"scan err {s} {e}", flush=True)
        check_exits()
        time.sleep(60)
