# BOT V47.6 FINAL NO-TOP-BUY - LIQ GRAB + SPECIFIC RE-ENTRY + LIVE + AUTO SELL + EARLY + PUMP FILTER + NO-SPAM
import time, json, os, requests, fcntl, sys
from datetime import datetime
from zoneinfo import ZoneInfo
SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
FAST_COINS={"SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"}
SLOW_COINS={"GRASSUSDT","TAOUSDT","SANDUSDT","JASMYUSDT"}
PER_COIN_TP={"GRASSUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.12,"tp3":0.22,"tp4":0.30},"FARTCOINUSDT":{"sl":0.025,"tp1":0.06,"tp2":0.12,"tp3":0.20,"tp4":0.28},"KOMAUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.10,"tp3":0.18,"tp4":0.25},"SENTUSDT":{"sl":0.022,"tp1":0.04,"tp2":0.08,"tp3":0.15,"tp4":0.22},"LABUSDT":{"sl":0.025,"tp1":0.06,"tp2":0.12,"tp3":0.20,"tp4":0.28},"SIRENUSDT":{"sl":0.022,"tp1":0.05,"tp2":0.10,"tp3":0.18,"tp4":0.25},"TAOUSDT":{"sl":0.015,"tp1":0.025,"tp2":0.05,"tp3":0.08,"tp4":0.12},"SANDUSDT":{"sl":0.012,"tp1":0.02,"tp2":0.04,"tp3":0.07,"tp4":0.10},"JASMYUSDT":{"sl":0.015,"tp1":0.025,"tp2":0.05,"tp3":0.08,"tp4":0.12},}
COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"; LOCK_FILE="/tmp/bot.lock"; TREND_CACHE="last_trend.json"; PUMP_CACHE="pump_cache.json"
COOLDOWN={"signals":{}}; ACTIVE={}; WARN_TIME={}; EARLY_WARN_TIME={}; PUMP_HIST={}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: pass
if os.path.exists(ACTIVE_FILE):
    try: ACTIVE=json.load(open(ACTIVE_FILE))
    except: pass
if os.path.exists(PUMP_CACHE):
    try: PUMP_HIST=json.load(open(PUMP_CACHE))
    except: pass
def save_c(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_a(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
def save_p(): open(PUMP_CACHE,"w").write(json.dumps(PUMP_HIST))
def get_time():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")
def tg(msg):
    print(msg,flush=True)
    try:
        token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
        if token and chat: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
    except: pass
def get_live_price(sym):
    try:
        r=requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={sym}", timeout=4).json()
        return float(r["price"])
    except: return None
def kl(sym,interval):
    headers={"User-Agent":"Mozilla/5.0"}
    spot_sym=sym.replace("_",""); spot_iv={"Min15":"15m","Min60":"60m","Min240":"4h"}.get(interval,"15m")
    urls=[f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval={interval}",f"https://api.mexc.com/api/v3/klines?symbol={spot_sym}&interval={spot_iv}&limit=200",f"https://futures.mexc.com/api/v1/contract/kline/{sym}?interval={interval}"]
    for url in urls:
        try:
            r=requests.get(url,timeout=12,headers=headers).json()
            data=r.get("data",[]) if isinstance(r,dict) else r
            if isinstance(data,dict) and "close" in data and len(data["close"])>20:
                return {"o":[float(x) for x in data["open"]],"h":[float(x) for x in data["high"]],"l":[float(x) for x in data["low"]],"c":[float(x) for x in data["close"]]}
            if isinstance(data,list) and len(data)>20:
                o,h,l,c=[],[],[],[]
                for k in data:
                    try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4]))
                    except: continue
                if len(c)>20: return {"o":o,"h":h,"l":l,"c":c}
        except: continue
    return None
def pump_dump_detector(s, curr):
    global PUMP_HIST
    now = time.time()
    if s not in PUMP_HIST: PUMP_HIST[s] = []
    PUMP_HIST[s].append((now, curr))
    PUMP_HIST[s] = [(t,p) for t,p in PUMP_HIST[s] if now - t <= 600]
    if len(PUMP_HIST[s]) < 3: return None
    prices = [p for _,p in PUMP_HIST[s]]
    low_10 = min(prices); high_10 = max(prices)
    pump_pct = (curr - low_10)/low_10 if low_10 else 0
    dump_pct = (high_10 - curr)/high_10 if high_10 else 0
    is_fast = s in FAST_COINS
    pump_thr = 0.06 if is_fast else 0.08
    dump_thr = 0.04 if is_fast else 0.06
    if pump_pct >= pump_thr:
        return f"PUMP +{pump_pct*100:.1f}% in 10m LIVE {curr:.5f} (low {low_10:.5f}) -> SELL SCALP NOW | {s}"
    if dump_pct >= dump_thr:
        return f"DUMP -{dump_pct*100:.1f}% in 10m LIVE {curr:.5f} (high {high_10:.5f}) -> BUY SCALP | {s}"
    return None
def liquidity_scalp_levels(sym, bias, d15, live_price, entry_price=None):
    if not d15 or len(d15["c"])<25: return None
    recent_low = min(d15["l"][-20:-2])
    recent_high = max(d15["h"][-20:-2])
    mid = (recent_low+recent_high)/2
    if bias == "BULL":
        if live_price < recent_low * 1.005:
            buy_zone = recent_low * 0.985
            target = recent_high * 1.06
            return f" LIQ GRAB BULL | LIVE {live_price:.5f} swept low {recent_low:.5f} | BUY fuel {buy_zone:.5f}-{live_price:.5f} -> HOLD to {target:.5f} | DONT SELL - fuel to pump"
        if live_price > recent_high * 1.05:
            sell_now = live_price
            buy_back = recent_high * 1.01
            return f" OVEREXTENDED BULL +{((live_price/recent_high-1)*100):.1f}% | SELL {sell_now:.5f} -> BUY BACK {buy_back:.5f} | Await retest, if breaks {mid:.5f} flip SHORT"
    if bias == "BEAR":
        if live_price > recent_high * 0.995:
            sell_zone = recent_high * 1.015
            target = recent_low * 0.94
            return f" LIQ GRAB BEAR | LIVE {live_price:.5f} swept high {recent_high:.5f} | SELL fuel {live_price:.5f}-{sell_zone:.5f} -> HOLD SHORT to {target:.5f} | DONT BUY - fuel to dump"
        if live_price < recent_low * 0.95:
            buy_now = live_price
            sell_back = recent_low * 0.99
            return f" OVEREXTENDED BEAR -{((1-live_price/recent_low)*100):.1f}% | BUY {buy_now:.5f} -> SELL BACK {sell_back:.5f} | Await retest, if breaks {mid:.5f} flip LONG"
    return None
def early_warning(d, symbol):
    if len(d["c"])<60: return None
    curr=d["c"][-1]
    recent_low = min(d["l"][-20:]); prev_low = min(d["l"][-50:-20])
    recent_high = max(d["h"][-20:]); prev_high = max(d["h"][-50:-20])
    ema = sum(d["c"][-50:])/50
    lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2
    is_fast = symbol in FAST_COINS
    if curr < ema*1.01 and recent_low < prev_low*1.015 and curr < mid*1.01:
        mins = 10 if is_fast else 15
        return f"EARLY BEAR SHIFT ~{mins}m | {symbol} {curr:.5f} near EMA {ema:.5f}"
    if curr > ema*0.99 and recent_high > prev_high*0.985 and curr > mid*0.99:
        mins = 10 if is_fast else 15
        return f"EARLY BULL SHIFT ~{mins}m | {symbol} {curr:.5f} near EMA {ema:.5f}"
    if abs(curr-mid)/mid < 0.015:
        mins = 10 if is_fast else 15
        side = "BEAR" if curr < mid else "BULL"
        return f"EARLY {side} SHIFT ~{mins}m | {symbol} near mid {mid:.5f}"
    return None
def get_bias_4h(d, symbol=""):
    if len(d["c"])<60: return "RANGE","Need more candles",0,0,d["c"][-1] if d["c"] else 0
    recent_low = min(d["l"][-20:]); prev_low = min(d["l"][-50:-20])
    recent_high = max(d["h"][-20:]); prev_high = max(d["h"][-50:-20])
    ema = sum(d["c"][-50:])/50; curr = d["c"][-1]
    sup=recent_low; res=recent_high; long_tgt=res*1.08; short_tgt=sup*0.92
    is_fast = symbol in FAST_COINS if symbol else curr < 1.0
    thr = 0.008 if is_fast else 0.002
    higher_low = recent_low > prev_low * (1+thr)
    lower_low = recent_low < prev_low * (1-thr)
    if higher_low and curr > ema: return "BULL", f"HL {prev_low:.4f}->{recent_low:.4f} intact", sup, res, long_tgt
    if lower_low and curr < ema: return "BEAR", f"LL {prev_low:.4f}->{recent_low:.4f} broken", sup, res, short_tgt
    lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2
    if not is_fast:
        if curr>mid and curr>ema: return "BULL", f"Above mid {mid:.4f}", sup, res, long_tgt
        if curr<mid and curr<ema: return "BEAR", f"Below mid {mid:.4f}", sup, res, short_tgt
    return "RANGE", f"No HL/LL | {prev_low:.4f}->{recent_low:.4f} | mid {mid:.4f}", sup, res, curr
def detect_fvg_1h(d):
    b=False; br=False
    if len(d["c"])<10: return False,False
    for i in range(-10,-2):
        if d["l"][i] > d["h"][i-2]: b=True
        if d["h"][i] < d["l"][i-2]: br=True
    return b,br
def detect_ob_1h(d):
    b=False; br=False
    if len(d["c"])<10: return False,False
    for i in range(-6,-1):
        body=abs(d["c"][i]-d["o"][i]); rng=d["h"][i]-d["l"][i] or 1
        if d["c"][i] < d["o"][i] and d["c"][-1] > d["h"][i] and body/rng>0.4: b=True
        if d["c"][i] > d["o"][i] and d["c"][-1] < d["l"][i] and body/rng>0.4: br=True
    return b,br
def detect_liquidity_1h(d):
    b=False; br=False
    if len(d["c"])<20: return False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2])
    if d["h"][-2] > recent_high and d["c"][-1] < recent_high: br=True
    if d["l"][-2] < recent_low and d["c"][-1] > recent_low: b=True
    return b,br
def detect_breaker_1h(d):
    b=False; br=False
    if len(d["c"])<20: return False,False
    for i in range(-18,-5):
        ob_high=d["h"][i]; ob_low=d["l"][i]
        if d["c"][i] < d["o"][i]:
            broken=False
            for j in range(i+1,-2):
                if d["c"][j] > ob_high: broken=True; break
            if broken and d["l"][-1] <= ob_high and d["l"][-1] >= ob_low*0.995: b=True
        if d["c"][i] > d["o"][i]:
            broken=False
            for j in range(i+1,-2):
                if d["c"][j] < ob_low: broken=True; break
            if broken and d["h"][-1] >= ob_low and d["h"][-1] <= ob_high*1.005: br=True
    return b,br
def check_1h_confluence(d1, is_buy, is_slow=False):
    bull_fvg,bear_fvg=detect_fvg_1h(d1); bull_ob,bear_ob=detect_ob_1h(d1); bull_liq,bear_liq=detect_liquidity_1h(d1); bull_brk,bear_brk=detect_breaker_1h(d1)
    if is_buy:
        reason=f"FVG:{bull_fvg} OB:{bull_ob} LIQ:{bull_liq} BRK:{bull_brk}"
        ok = (bull_ob or bull_brk or bull_liq or bull_fvg) if is_slow else (bull_ob or bull_brk)
        return ok,reason
    else:
        reason=f"FVG:{bear_fvg} OB:{bear_ob} LIQ:{bear_liq} BRK:{bear_brk}"
        ok = (bear_ob or bear_brk or bear_liq or bear_fvg) if is_slow else (bear_ob or bear_brk)
        return ok,reason
def fbs_logic(h,l,c,o):
    if len(c)<3: return None,None,None
    ph,pl=h[-2],l[-2]; pc=c[-2]; cc=c[-1]; co=o[-1]
    pr=ph-pl or 1; p58=pl+pr*0.58; p35=pl+pr*0.35
    if pc>=p58 and cc>=p35 and cc>co: return "BOS_UP",True,""
    if pc<=p35 and cc<=p58 and cc<co: return "BOS_DOWN",False,""
    return None,None,None
def manage():
    global ACTIVE
    if not ACTIVE: return
    now=time.time()
    for s in list(ACTIVE.keys()):
        d5=kl(SYMBOL_MAP[s],"Min15"); d240=kl(SYMBOL_MAP[s],"Min240")
        if not d5 or not d240: continue
        pos=ACTIVE[s]; is_buy=pos["is_buy"]; entry=pos["entry"]
        live = get_live_price(s)
        cur = live if live else d5["c"][-1]
        pnl=(cur-entry)/entry if is_buy else (entry-cur)/entry
        cfg=PER_COIN_TP[s]
        sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        bias,_,_,_,_ = get_bias_4h(d240, s)
        liq_msg = liquidity_scalp_levels(s, bias, d5, cur, entry)
        if liq_msg:
            if s not in WARN_TIME or now-WARN_TIME.get(s,0)>3600:
                tg(f"{s}{liq_msg} | ACTIVE {pnl*100:+.1f}% | {get_time()}")
                WARN_TIME[s]=now
        pd_msg = pump_dump_detector(s, cur)
        if pd_msg:
            if s not in WARN_TIME or now-WARN_TIME.get(s,0)>3600:
                tg(f"🚨 {pd_msg} | PnL {pnl*100:+.1f}% | {get_time()}")
                WARN_TIME[s]=now
            save_p()
            if is_buy and "PUMP" in pd_msg and pnl>=cfg["tp3"]:
                buy_back = min(d5["l"][-20:-2]) if len(d5["l"])>=20 else cur*0.95
                tg(f"SCALP SELL {s} PUMP +{pnl*100:.1f}% LIVE {cur:.5f} -> BUY BACK {buy_back:.5f} | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            tg(f"SL {s} {pnl*100:.1f}% LIVE {cur:.5f} | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if pnl>=cfg["tp4"]:
            buy_back = max(d5["l"][-20:-2]) if len(d5["l"])>=20 else cur*0.97
            tg(f"TP4 {s} +{pnl*100:.1f}% LIVE {cur:.5f} SELL NOW -> BUY BACK {buy_back:.5f} | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if pnl>=cfg["tp3"]:
            if s not in WARN_TIME or now-WARN_TIME.get(s,0)>1800:
                buy_back = max(d5["l"][-20:-2]) if len(d5["l"])>=20 else cur*0.97
                tg(f"TP3 {s} +{pnl*100:.1f}% LIVE {cur:.5f} SELL -> BUY BACK {buy_back:.5f} | {get_time()}")
                WARN_TIME[s]=now
def print_trends():
    try: manage()
    except Exception as e: print(f"manage error {e}", flush=True)
    global ACTIVE, EARLY_WARN_TIME
    if os.path.exists(ACTIVE_FILE):
        try: ACTIVE=json.load(open(ACTIVE_FILE))
        except: pass
    last={}
    if os.path.exists(TREND_CACHE):
        try: last=json.load(open(TREND_CACHE))
        except: pass
    msg = f"📊 TREND V47.6 NO-SPAM - {get_time()}\n━━━━━━━━━━━━━━\n\n"
    curr_state={}; changed=False; early_msgs=[]; pump_msgs=[]
    for s in SYMBOLS:
        d240=kl(SYMBOL_MAP[s],"Min240"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240: continue
        bias, reason, sup, res, tgt = get_bias_4h(d240, s)
        curr_state[s]=bias
        if last.get(s)!=bias: changed=True
        lp = get_live_price(s)
        cur_price = lp if lp else (d5["c"][-1] if d5 else tgt)
        ew = early_warning(d240, s)
        if ew and (s not in EARLY_WARN_TIME or time.time()-EARLY_WARN_TIME.get(s,0)>3600):
            early_msgs.append(ew); EARLY_WARN_TIME[s]=time.time()
        pd = pump_dump_detector(s, cur_price)
        if pd and (s not in EARLY_WARN_TIME or time.time()-EARLY_WARN_TIME.get(s,0)>3600):
            pump_msgs.append(pd)
        liq = liquidity_scalp_levels(s, bias, d5, cur_price)
        rev_line=""
        if s in ACTIVE and d5:
            pos=ACTIVE[s]; cur=cur_price; entry=pos["entry"]
            pnl=(cur-entry)/entry if pos["is_buy"] else (entry-cur)/entry
            rev_line=f"\n 📈 LIVE {cur:.5f} {pnl*100:+.1f}% HOLD"
            if liq: rev_line+=f"\n{liq}"
        if bias=="BULL": msg += f"🟢 {s} BULL {reason} LIVE {cur_price:.5f}->{tgt:.5f}{rev_line}\n"
        elif bias=="BEAR": msg += f"🔴 {s} BEAR {reason} LIVE {cur_price:.5f}{rev_line}\n"
        else: msg += f"⚪ {s} RANGE {reason} LIVE {cur_price:.5f}{rev_line}\n"
        if liq and s not in ACTIVE: msg+=f" {liq}\n"
        msg+="\n"
    open(TREND_CACHE,"w").write(json.dumps(curr_state)); save_p()
    for em in early_msgs: tg(em + f" | {get_time()}")
    for pm in pump_msgs: tg(f"🚨 {pm} | {get_time()}")
    minute = datetime.now().minute
    should_send = changed or (minute % 60 == 0)
    if should_send or early_msgs or pump_msgs: tg(msg)
def scan():
    global COOLDOWN,ACTIVE
    if os.path.exists(COOLDOWN_FILE):
        try: COOLDOWN=json.load(open(COOLDOWN_FILE))
        except: pass
    if os.path.exists(ACTIVE_FILE):
        try: ACTIVE=json.load(open(ACTIVE_FILE))
        except: pass
    manage()
    for s in SYMBOLS:
        if s in ACTIVE: continue
        is_slow=s in SLOW_COINS
        if time.time()-COOLDOWN["signals"].get(s,0)<(7200 if not is_slow else 21600): continue
        d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d5: continue
        bias,_,_,_,_ =get_bias_4h(d240, s)
        if bias=="RANGE": continue
        lp = get_live_price(s)
        cur_f = lp if lp else d5["c"][-1]
        pd = pump_dump_detector(s, cur_f)
        if pd and "PUMP" in pd and bias=="BULL":
            continue
        liq = liquidity_scalp_levels(s, bias, d5, cur_f)
        if liq and "OVEREXTENDED BULL" in liq and bias=="BULL":
            if s not in WARN_TIME or time.time()-WARN_TIME.get(s,0)>3600:
                tg(f"⏳ {s}{liq} | WAIT - dont chase | {get_time()}")
                WARN_TIME[s]=time.time()
            continue
        if liq and "OVEREXTENDED BEAR" in liq and bias=="BEAR":
            continue
        fbs,is_buy,_=fbs_logic(d5["h"],d5["l"],d5["c"],d5["o"])
        if not fbs: continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue
        ok_1h,_=check_1h_confluence(d60,is_buy,is_slow=is_slow)
        if not ok_1h: continue
        ph=d5["h"][-2]; pl=d5["l"][-2]
        entry=pl+(ph-pl)*0.50
        cfg=PER_COIN_TP[s]; sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"]); tp1=entry*(1+cfg["tp1"]) if is_buy else entry*(1-cfg["tp1"])
        side="BUY" if is_buy else "SELL"
        tg(f"{side} {s} {fbs}\nEntry {entry:.5f} SL {sl:.5f} TP {tp1:.5f}\n{get_time()}")
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time()}; save_a()
        COOLDOWN["signals"][s]=time.time(); save_c()
if __name__=="__main__":
    fp=open(LOCK_FILE,"w")
    try: fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except:
        if "--once" not in sys.argv and "--trend" not in sys.argv: print("Bot already running"); exit(1)
    print(f"BOT V47.6 FINAL | {get_time()}")
    if "--trend" in sys.argv:
        try: print_trends()
        except Exception as e: print(f"TREND ERROR {e}")
        exit(0)
    if "--once" in sys.argv:
        try: scan()
        except: pass
        exit(0)
    while True:
        try: scan()
        except: pass
        time.sleep(60)
