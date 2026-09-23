# V28.9.8 SIMPLE - DAILY WICK TP FIXED
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

PAPER_MODE = True
DAILY_MAX_LOSS_R = 2.0
DAILY_LOSS_FILE = "daily_loss.json"

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

def get_daily_loss():
    if not os.path.exists(DAILY_LOSS_FILE): return {"date": str(datetime.now().date()), "loss_r": 0.0}
    try:
        data = json.load(open(DAILY_LOSS_FILE))
        if data.get("date")!= str(datetime.now().date()):
            return {"date": str(datetime.now().date()), "loss_r": 0.0}
        return data
    except: return {"date": str(datetime.now().date()), "loss_r": 0.0}

def check_daily_limit():
    data = get_daily_loss()
    if data["loss_r"] >= DAILY_MAX_LOSS_R:
        return False, data["loss_r"]
    return True, data["loss_r"]

STATS={"sniper":0}
LAST_TOP = {}

def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except: pass

COOLDOWN_NORMAL=120*60
COOLDOWN_AFTER_SL=90*60
COOLDOWN_SAME_LIQ=60*60

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

def fbs_62_first(h,l,c,o):
    if len(c)<3: return None, "no data", 0, 50
    prev_high, prev_low = h[-2], l[-2]
    prev_range = prev_high - prev_low
    if prev_range==0: return None, "no range", 0, 50
    pc, po = c[-2], o[-2]
    cc, co, ch, cl = c[-1], o[-1], h[-1], l[-1]
    l62 = prev_low + prev_range*0.62
    l38 = prev_low + prev_range*0.38
    l25 = prev_low + prev_range*0.25
    l75 = prev_low + prev_range*0.75
    def clamp_pct(price):
        raw = (price - prev_low)/prev_range*100 if prev_range else 50
        return max(0.0, min(100.0, raw))
    pct = clamp_pct(cc)
    prev_bull = pc > po
    prev_bear = pc < po
    curr_bull = cc > co
    curr_bear = cc < co
    if prev_bull and curr_bear:
        if l25 < cc < l75:
            return None, f"HOLD WEAK TOP-LEFT {pct:.0f}%", 0, pct
    if prev_bear and curr_bull:
        if l25 < cc < l75:
            return None, f"HOLD WEAK BTM-LEFT {pct:.0f}%", 0, pct
    if prev_bull and curr_bull:
        if cc > l62 and cl > l38:
            return "BOS_UP_STRONG", f"PUMP >62% {pct:.0f}%", l62, pct
    if prev_bear and curr_bear:
        if cc < l38 and ch < l62:
            return "BOS_DOWN_STRONG", f"DUMP <38% {pct:.0f}%", l38, pct
    return None, f"HOLD {pct:.0f}%", 0, pct

def can_flip(sym, new_side, close_pct):
    has_buy = f"{sym}_BUY" in ACTIVE
    has_sell = f"{sym}_SELL" in ACTIVE
    if has_buy and new_side == "SELL":
        if close_pct > 25:
            print(f"{sym} HOLD ACTIVE BUY exists, need <25% to REVERSAL", flush=True)
            return False
        else:
            print(f"{sym} REVERSAL BUY->SELL {close_pct:.0f}%", flush=True)
            del ACTIVE[f"{sym}_BUY"]; save_active(); return True
    if has_sell and new_side == "BUY":
        if close_pct < 75:
            print(f"{sym} HOLD ACTIVE SELL exists, need >75% to REVERSAL", flush=True)
            return False
        else:
            print(f"{sym} REVERSAL SELL->BUY {close_pct:.0f}%", flush=True)
            del ACTIVE[f"{sym}_SELL"]; save_active(); return True
    return True

def pattern(h,l):
    tops=[];bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]:
            tops.append((i,h[i]))
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]:
            bots.append((i,l[i]))
    if len(tops)>=2 and tops[-1][0]-tops[-2][0]>=5:
        if abs(tops[-1][1]-tops[-2][1])/tops[-2][1]<0.008: return "double_top"
    if len(bots)>=2 and bots[-1][0]-bots[-2][0]>=5:
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

def get_daily_levels(perp):
    # TRY Day1 first
    try:
        d1 = kl(perp, "Day1")
        if d1 and len(d1["h"]) >= 2 and d1["h"][-2] > 0:
            return d1["h"][-2], d1["l"][-2]
    except: pass
    # FALLBACK 60m 24h
    try:
        h1 = kl(perp, "Min60")
        if h1 and len(h1["h"]) >= 24:
            return max(h1["h"][-24:]), min(h1["l"][-24:])
    except: pass
    return None, None

def get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy, perp=None):
    ob_low, ob_high = ob
    entry = (ob_low + ob_high)/2
    daily_high, daily_low = get_daily_levels(perp) if perp else (None, None)
    if is_buy:
        sl = min(min(l[-7:]), ob_low) * 0.997
        if daily_high:
            tp1 = daily_high * 1.003
            tp2 = daily_high * 1.012
        else:
            tp1 = max(h[-20:]) * 1.008
            tp2 = max(h[-20:]) * 1.018
        tp1 = max(tp1, entry*1.006)
        tp2 = max(tp2, tp1*1.006)
        daily_level = daily_high
    else:
        sl = max(max(h[-7:]), ob_high) * 1.003
        if daily_low:
            tp1 = daily_low * 0.997
            tp2 = daily_low * 0.988
        else:
            tp1 = min(l[-20:]) * 0.992
            tp2 = min(l[-20:]) * 0.982
        tp1 = min(tp1, entry*0.994)
        tp2 = min(tp2, tp1*0.994)
        daily_level = daily_low
    risk = abs(entry - sl)
    rr2 = abs(tp2 - entry)/(risk or 1e-9)
    return entry, sl, tp1, tp2, daily_level, rr2

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
    ok, loss = check_daily_limit()
    if not ok:
        print(f"⛔ DAILY LOSS {loss:.1f}R STOP", flush=True)
        return
    d5=kl(p,"Min5"); d15=kl(p,"Min15")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    session_name,session_emoji=get_session()
    if session_name=="OFF": return

    fbs_res = None; fbs_msg = ""; top_level = 0; pct = 50; tf_used = ""
    for tf_data, tf_name in [(d5,"5m"),(d15,"15m")]:
        res,msg,top,pc = fbs_62_first(tf_data["h"], tf_data["l"], tf_data["c"], tf_data["o"])
        if res and not fbs_res:
            fbs_res=res; fbs_msg=msg; top_level=top; pct=pc; tf_used=tf_name
            break
    if not fbs_res:
        _,msg,_,pct_tmp = fbs_62_first(d5["h"], d5["l"], d5["c"], d5["o"])
        print(f"{s} HOLD {msg}", flush=True)
        return

    vp=volume_pressure(o,h,l,c,v)
    pat=pattern(d5["h"],d5["l"])

    is_buy = "UP" in fbs_res
    side = "BUY" if is_buy else "SELL"
    key=f"{s}_{side}"

    if not can_flip(s, side, pct): return

    if f"{s}_{side}" in LAST_TOP:
        last_top, last_time = LAST_TOP[f"{s}_{side}"]
        same_liq = abs(top_level - last_top) / (last_top or 1) < 0.005
        if same_liq and (time.time() - last_time) < COOLDOWN_SAME_LIQ:
            print(f"{s} {side} SAME LIQ HOLD {int((COOLDOWN_SAME_LIQ-(time.time()-last_time))//60)}m", flush=True)
            return

    if key in ACTIVE:
        print(f"{s} {side} TREND CONTINUING HOLD", flush=True)
        return

    prev=COOLDOWN["signals"].get(key,{}); now=time.time()
    if now - prev.get("t",0) < COOLDOWN_NORMAL:
        print(f"{s} {side} COOLDOWN HOLD {int((COOLDOWN_NORMAL-(now-prev.get('t',0)))//60)}m", flush=True)
        return

    if is_buy and pat in ["double_top"]:
        print(f"{s} BUY FALSE PUMP BLOCK {pat} HOLD", flush=True)
        return
    if not is_buy and pat in ["double_bottom"]:
        print(f"{s} SELL FALSE DUMP BLOCK {pat} HOLD", flush=True)
        return

    if is_buy and vp["buy_pct"] < 55:
        print(f"{s} BUY PRESSURE LOW {vp['buy_pct']:.0f}% HOLD", flush=True)
        return
    if not is_buy and vp["sell_pct"] < 55:
        print(f"{s} SELL PRESSURE LOW {vp['sell_pct']:.0f}% HOLD", flush=True)
        return

    ob=get_last_ob(o,h,l,c,bullish=is_buy,lookback=60)
    if not ob: ob = (min(l[-15:]), max(h[-15:]))

    entry, sl, tp1, tp2, daily_level, rr2 = get_perfect_entry_sl_tp(o,h,l,c,ob,is_buy, perp=p)

    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top_level,"entry":entry,"tp1":tp1,"tp2":tp2}
    save()
    LAST_TOP[f"{s}_{side}"] = (top_level, now)
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl}
    save_active()
    STATS["sniper"]+=1

    mode_tag = "PAPER" if PAPER_MODE else "REAL"
    if daily_level:
        daily_str = f"Daily {daily_level:.4f}"
    else:
        daily_str = f"{tf_used} High"

    if is_buy:
        tg(f"🟢 <b>BUY {s}</b> {session_emoji} {mode_tag} | {fbs_msg} ({tf_used})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 {tp1:.6f} ({daily_str} +0.3%)\nTP2 {tp2:.6f} (+1.2%) | RR {rr2:.1f}R")
    else:
        tg(f"🔴 <b>SELL {s}</b> {session_emoji} {mode_tag} | {fbs_msg} ({tf_used})\nEntry {entry:.6f} | SL {sl:.6f}\nTP1 {tp1:.6f} ({daily_str} -0.3%)\nTP2 {tp2:.6f} (-1.2%) | RR {rr2:.1f}R")

print("=== BOT V28.9.8 DAILY WICK FIXED ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"ACTIVE:{list(ACTIVE.keys())}", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(e, flush=True)
        time.sleep(60)
