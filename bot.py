# V28.9.3 DUAL SIDE - CLAMPED 0-100% FIX 168% BUG + LEFT 25/75 BLOCK + RIGHT 62/38 ENTER + VOL 0.4x + RR2.0 + PAPER + DAILY LOSS
import time, json, os, requests, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo

# === SAFETY SETTINGS - CHANGE HERE ===
PAPER_MODE = True # True = paper signals only, no real trade
DAILY_MAX_LOSS_R = 2.0 # stop trading after -2R loss per day
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

# Daily loss tracking
def get_daily_loss():
    if not os.path.exists(DAILY_LOSS_FILE): return {"date": str(datetime.now().date()), "loss_r": 0.0}
    try:
        data = json.load(open(DAILY_LOSS_FILE))
        if data.get("date")!= str(datetime.now().date()):
            return {"date": str(datetime.now().date()), "loss_r": 0.0}
        return data
    except: return {"date": str(datetime.now().date()), "loss_r": 0.0}

def add_daily_loss(r_loss):
    data = get_daily_loss()
    data["loss_r"] += r_loss
    data["date"] = str(datetime.now().date())
    open(DAILY_LOSS_FILE,"w").write(json.dumps(data))
    return data["loss_r"]

def check_daily_limit():
    data = get_daily_loss()
    if data["loss_r"] >= DAILY_MAX_LOSS_R:
        return False, data["loss_r"]
    return True, data["loss_r"]

STATS={"touched":0,"sniper":0,"xxx":0}
WHALE_TRACKER={}
LAST_TOP = {}

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
COOLDOWN_SAME_LIQ=30*60

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

# === V28.9.3 FIXED 168% BUG - CLAMPED 0-100% ===
def fbs_62_first(h,l,c,o):
    if len(c)<3: return None, "no data", 0, 50
    prev_high, prev_low = h[-2], l[-2]
    prev_range = prev_high - prev_low
    if prev_range==0: return None, "no range", 0, 50
    pc, po = c[-2], o[-2]
    cc, co, ch, cl = c[-1], o[-1], h[-1], l[-1]
    l75 = prev_low + prev_range*0.75
    l62 = prev_low + prev_range*0.62
    l38 = prev_low + prev_range*0.38
    l25 = prev_low + prev_range*0.25

    def clamp_pct(price):
        raw = (price - prev_low)/prev_range*100 if prev_range else 50
        return max(0.0, min(100.0, raw))

    pct = clamp_pct(cc)
    pct_high = clamp_pct(ch)
    pct_low = clamp_pct(cl)

    prev_bull = pc > po
    prev_bear = pc < po
    curr_bull = cc > co
    curr_bear = cc < co

    if prev_bull and curr_bear:
        if l25 < cc < l75:
            return None, f"BULLISH WEAK TOP-LEFT {pct:.0f}% <75% DO NOT ENTER X", 0, pct
    if prev_bear and curr_bull:
        if l25 < cc < l75:
            return None, f"BEARISH WEAK BTM-LEFT {pct:.0f}% >25% DO NOT ENTER X", 0, pct

    if prev_bull and curr_bull:
        if cc > l62 and cl > l38:
            return "BOS_UP_STRONG", f"STRONG BUY Top-Right >62% {pct:.0f}% ENTER ✓ {l62:.4f} ({pct_low:.0f}-{pct_high:.0f}%)", l62, pct
    if prev_bear and curr_bear:
        if cc < l38 and ch < l62:
            return "BOS_DOWN_STRONG", f"STRONG SELL Btm-Right <38% {pct:.0f}% ENTER ✓ {l38:.4f} ({pct_low:.0f}-{pct_high:.0f}%)", l38, pct

    return None, f"No breakout {pct:.0f}% H:{pct_high:.0f}% L:{pct_low:.0f}%", 0, pct

def can_flip(sym, new_side, close_pct):
    if sym not in [k.split('_')[0] for k in ACTIVE.keys()]:
        return True
    active_buy_key = f"{sym}_BUY"
    active_sell_key = f"{sym}_SELL"
    has_buy = active_buy_key in ACTIVE
    has_sell = active_sell_key in ACTIVE
    if has_buy and new_side == "SELL":
        if close_pct > 25:
            tg(f"⛔ <b>{sym} COUNTER-TREND BLOCKED</b>\nACTIVE BUY >62% exists\nNew SELL {close_pct:.0f}% (need <25% to flip)")
            return False
        else:
            tg(f"🔄 <b>{sym} FLIP ALLOWED</b> BUY->{new_side} {close_pct:.0f}% <25% super strong")
            del ACTIVE[active_buy_key]; save_active(); return True
    if has_sell and new_side == "BUY":
        if close_pct < 75:
            tg(f"⛔ <b>{sym} COUNTER-TREND BLOCKED</b>\nACTIVE SELL <38% exists\nNew BUY {close_pct:.0f}% (need >75% to flip)")
            return False
        else:
            tg(f"🔄 <b>{sym} FLIP ALLOWED</b> SELL->{new_side} {close_pct:.0f}% >75%")
            del ACTIVE[active_sell_key]; save_active(); return True
    return True

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

def get_liquidity_tps(d5, d15, d60, entry, is_buy):
    try:
        liqs = []
        for tf in [d5, d15, d60]:
            if not tf: continue
            hi = max(tf["h"][-20:]); lo = min(tf["l"][-20:])
            liqs.append(hi); liqs.append(lo)
            for i in range(-15,-1):
                if tf["h"][i] > tf["h"][i-1] * 1.005: liqs.append(tf["h"][i])
                if tf["l"][i] < tf["l"][i-1] * 0.995: liqs.append(tf["l"][i])
        liqs = sorted(list(set(liqs)))
        if is_buy:
            above = [x for x in liqs if x > entry * 1.002]
            above = sorted(above)
            if len(above) >= 2: return above[0], above[1], above[0]*1.02
            elif len(above) == 1: return above[0], above[0]*1.015, above[0]*1.03
        else:
            below = [x for x in liqs if x < entry * 0.998]
            below = sorted(below, reverse=True)
            if len(below) >= 2: return below[0], below[1], below[0]*0.98
            elif len(below) == 1: return below[0], below[0]*0.985, below[0]*0.97
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
    ok, loss = check_daily_limit()
    if not ok:
        print(f"⛔ DAILY LOSS LIMIT HIT {loss:.1f}R >= {DAILY_MAX_LOSS_R}R - STOP TRADING TODAY", flush=True)
        return

    d5=kl(p,"Min5"); d15=kl(p,"Min15"); d60=kl(p,"Min60")
    if not d5 or not d15: return
    c,o,h,l,v=d5["c"],d5["o"],d5["h"],d5["l"],d5["v"]
    if len(c)<30: return
    price=c[-1]
    session_name,session_emoji=get_session()
    if session_name=="OFF": return
    fbs_up=None; fbs_down=None; fbs_msg_up=""; fbs_msg_down=""; top_up=0; top_down=0; pct_up=50; pct_down=50
    for tf_data, tf_name in [(d5,"5m"),(d15,"15m")]:
        res,msg,top,pct = fbs_62_first(tf_data["h"], tf_data["l"], tf_data["c"], tf_data["o"])
        if res and "UP" in res and not fbs_up: fbs_up=res; fbs_msg_up=f"{msg} ({tf_name})"; top_up=top; pct_up=pct
        if res and "DOWN" in res and not fbs_down: fbs_down=res; fbs_msg_down=f"{msg} ({tf_name})"; top_down=top; pct_down=pct
        if "WEAK" in msg:
            print(f"{s} {tf_name} {msg}", flush=True)
    if not fbs_up and not fbs_down:
        has_weak = False
        for tf_data in [d5,d15]:
            _,msg,_,_ = fbs_62_first(tf_data["h"], tf_data["l"], tf_data["c"], tf_data["o"])
            if "WEAK" in msg: has_weak=True
        if not has_weak:
            _,msg,_,_ = fbs_62_first(d5["h"], d5["l"], d5["c"], d5["o"])
            print(f"{s} SNIPER:0 - {msg}", flush=True)
        return
    vp=volume_pressure(o,h,l,c,v)
    if vp["vol_x"] < 0.4:
        print(f"{s} SNIPER:0 VOL KILL {vp['vol_x']:.2f}x <0.4x WEAK - SKIP", flush=True)
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
        close_pct = pct_up if is_buy else pct_down
        if not fbs_res: continue
        side="BUY" if is_buy else "SELL"
        key=f"{s}_{side}"
        if not can_flip(s, side, close_pct):
            continue
        last_top_key = f"{s}_{side}"
        if last_top_key in LAST_TOP:
            last_top, last_time = LAST_TOP[last_top_key]
            same_liq = abs(top_level - last_top) / (last_top or 1) < 0.005
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
            if prev.get("session") == "ASIAN" and session_name!= "ASIAN" and prev.get("dir")==is_buy:
                last_entry = prev.get("entry", price)
                last_tp1 = prev.get("tp1", 0)
                last_tp2 = prev.get("tp2", 0)
                tg(f"🟡 <b>{s} {side} TREND CONTINUING</b> {prev.get('session','')}->{session_name}\nLast {side} {top_level:.4f} still >62% holding\nEntry {last_entry:.6f} tapping OB\nTP1 {last_tp1:.6f} TP2 {last_tp2:.6f} | {pat} | {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}%")
                COOLDOWN["signals"][key]["t"]=now - cd_need + 300
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
        if rr2 < 2.0:
            print(f"{s} {side} RR LOW {rr2:.1f} <2.0 SKIP", flush=True)
            continue

        mode_tag = "📄 PAPER" if PAPER_MODE else "💰 REAL"
        COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"result":"normal","session":session_name,"top":top_level,"entry":entry,"tp1":tp1,"tp2":tp2}
        save()
        LAST_TOP[f"{s}_{side}"] = (top_level, now)
        if not PAPER_MODE:
            ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"sl":sl,"side_key":key}
            save_active()
        STATS["sniper"]+=1
        emoji = "🟢" if is_buy else "🔴"
        phase_txt = f"⚡ WHALE {vp['vol_x']:.1f}x" if is_whale else f"🏗️ BUILD {vp['vol_x']:.1f}x"
        tg(f"{emoji} <b>{s} {side}</b> {session_emoji} {session_name} {mode_tag}\n{phase_txt} {fbs_res} RR:{rr2:.1f}R\n{fbs_msg}\nEntry: {entry:.6f} (50% OB)\nSL: {sl:.6f}\nTP1: {tp1:.6f} (liq tap)\nTP2: {tp2:.6f} (liq sweep)\n{pat} {bos or ''} | {vp['buy_pct']:.0f}%/{vp['sell_pct']:.0f}% | Δ B:{buy_v:.0f} S:{sell_v:.0f}")

print("=== BOT V28.9.3 CLAMPED 0-100% + VOL 0.4x RR2.0 + PAPER + DAILY LOSS ===", flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e, flush=True)
    print(f"STATS SNIPER:{STATS['sniper']} ACTIVE:{list(ACTIVE.keys())} PAPER:{PAPER_MODE}", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(e, flush=True)
        print(f"Sleep 60s... ACTIVE:{list(ACTIVE.keys())} PAPER:{PAPER_MODE} DailyLoss:{get_daily_loss()['loss_r']:.1f}R", flush=True)
        time.sleep(60)
