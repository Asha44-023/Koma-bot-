# BOT V36 DIAGRAM PRO - TIMER MODE + 58/35 + 78/22 + TBS OPTIONAL + EXTENDED TP 11.17%/13.3% ALL COINS + SMART WALL 30/10 MIN
import time, json, os, requests, sys
from datetime import datetime
from zoneinfo import ZoneInfo

VERBOSE = False

SYMBOL_MAP = {
    "GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT",
    "SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT",
    "LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"
}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
FAST_SYMS = ["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT","LABUSDT","SIRENUSDT"]

PER_COIN_TP = {
    "FARTCOINUSDT": {"tp1":0.05, "tp2":0.09, "tp3":0.14, "sl_grab":0.02, "sl_rev":0.035, "sl_bos":0.025},
    "GRASSUSDT": {"tp1":0.04, "tp2":0.08, "tp3":0.12, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    "KOMAUSDT": {"tp1":0.04, "tp2":0.08, "tp3":0.12, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    "SENTUSDT": {"tp1":0.035, "tp2":0.065, "tp3":0.10, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    "LABUSDT": {"tp1":0.05, "tp2":0.09, "tp3":0.14, "sl_grab":0.02, "sl_rev":0.035, "sl_bos":0.025},
    "SIRENUSDT": {"tp1":0.04, "tp2":0.08, "tp3":0.12, "sl_grab":0.018, "sl_rev":0.03, "sl_bos":0.022},
    "SANDUSDT": {"tp1":0.018, "tp2":0.035, "tp3":0.055, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
    "TAOUSDT": {"tp1":0.02, "tp2":0.04, "tp3":0.065, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
    "JASMYUSDT": {"tp1":0.018, "tp2":0.038, "tp3":0.06, "sl_grab":0.01, "sl_rev":0.016, "sl_bos":0.012},
}

PER_COIN_TIMER = {
    "GRASSUSDT": {"est_mins": 90, "max_mins": 210},
    "FARTCOINUSDT": {"est_mins": 100, "max_mins": 300},
    "KOMAUSDT": {"est_mins": 120, "max_mins": 360},
    "SENTUSDT": {"est_mins": 70, "max_mins": 180},
    "LABUSDT": {"est_mins": 45, "max_mins": 135},
    "SIRENUSDT": {"est_mins": 120, "max_mins": 360},
    "SANDUSDT": {"est_mins": 80, "max_mins": 220},
    "TAOUSDT": {"est_mins": 60, "max_mins": 180},
    "JASMYUSDT": {"est_mins": 120, "max_mins": 360},
}

DOM_SENSITIVITY = {"FARTCOINUSDT":2.5,"GRASSUSDT":2.2,"KOMAUSDT":2.0,"SENTUSDT":1.6,"LABUSDT":2.4,"SIRENUSDT":2.0,"SANDUSDT":1.3,"TAOUSDT":1.1,"JASMYUSDT":1.2}
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

def check_btc_filter(sym,is_buy):
    btc_d,hist=get_btc_dominance()
    if len(hist)<2: return True
    change=btc_d-hist[0][1]; eff=change*DOM_SENSITIVITY.get(sym,1.0)
    if change>=0.6 and eff>=0.9 and is_buy: return False
    if change<=-0.6 and eff<=-0.9 and not is_buy: return False
    return True

def check_hold_timer(symbol, entry_time_epoch):
    now = time.time()
    mins_in = (now - entry_time_epoch) / 60
    cfg = PER_COIN_TIMER.get(symbol, {"est_mins": 120, "max_mins": 360})
    est = cfg["est_mins"]; max_hold = cfg["max_mins"]
    if mins_in >= max_hold: return "CLOSE_MAX_EXCEEDED", mins_in, max_hold
    elif mins_in >= est: return "MOVE_SL_TO_BE", mins_in, max_hold
    else: return "HOLD", mins_in, max_hold

COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"; WALL_FILE="wall_alerts.json"
COOLDOWN={"signals":{}}; ACTIVE={}; WALL_ALERTS={}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: COOLDOWN={"signals":{}}
if os.path.exists(ACTIVE_FILE):
    try: ACTIVE=json.load(open(ACTIVE_FILE))
    except: ACTIVE={}
if os.path.exists(WALL_FILE):
    try: WALL_ALERTS=json.load(open(WALL_FILE))
    except: WALL_ALERTS={}
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_active(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
def save_wall(): open(WALL_FILE,"w").write(json.dumps(WALL_ALERTS))
LAST_TOP={}

def get_time_12hr():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")

def log(msg):
    if VERBOSE: print(msg, flush=True)

def tg(msg):
    print(msg,flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except Exception as e: print(f"TG error {e}")

def kl(sym,interval):
    def fetch(url_sym, inter):
        urls = [
            f"https://contract.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",
            f"https://futures.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",
            f"https://api.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",
        ]
        for u in urls:
            try:
                r=requests.get(u, timeout=10).json()
                data=r.get("data",[])
                if not data: continue
                if isinstance(data,dict):
                    def f(x):
                        try: return float(x)
                        except: return 0.0
                    if len(data.get("close",[]))>10:
                        return {"o":[f(x) for x in data.get("open",[])],"h":[f(x) for x in data.get("high",[])],"l":[f(x) for x in data.get("low",[])],"c":[f(x) for x in data.get("close",[])],"v":[f(x) for x in data.get("vol",[])]}
                else:
                    o,h,l,c,v=[],[],[],[],[]
                    for k in data:
                        try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
                        except: continue
                    if len(c)>10: return {"o":o,"h":h,"l":l,"c":c,"v":v}
            except: continue
        return None
    res = fetch(sym, interval)
    if res: return res
    if interval=="Min240":
        d60 = fetch(sym, "Min60")
        if not d60 or len(d60["c"])<200: return None
        o,h,l,c,v=[],[],[],[],[]
        for i in range(0, len(d60["c"])-3, 4):
            chunk_c = d60["c"][i:i+4]; chunk_o = d60["o"][i:i+4]; chunk_h = d60["h"][i:i+4]; chunk_l = d60["l"][i:i+4]; chunk_v = d60["v"][i:i+4]
            if len(chunk_c)<4: continue
            o.append(chunk_o[0]); h.append(max(chunk_h)); l.append(min(chunk_l)); c.append(chunk_c[-1]); v.append(sum(chunk_v))
        if len(c)>20:
            return {"o":o,"h":h,"l":l,"c":c,"v":v}
    return None

def get_4h_bias(d240):
    h,l,c=d240["h"],d240["l"],d240["c"]
    if len(c)<50: return None,0,0,""
    crt_low=min(l[-48:]); crt_high=max(h[-48:]); mid=(crt_low+crt_high)/2
    ema50=sum(c[-50:])/50
    if c[-1]>mid and c[-1]>ema50: bias="BULL"; key_level=crt_high
    elif c[-1]<mid and c[-1]<ema50: bias="BEAR"; key_level=crt_low
    else: bias="RANGE"; key_level=mid
    return bias,crt_low,crt_high,key_level

def detect_fvg(h,l,lookback=20):
    fvg_list=[]
    for i in range(len(h)-lookback, len(h)-2):
        if l[i+2] > h[i]: fvg_list.append({"type":"BULL","top":l[i+2],"bot":h[i],"pct":(l[i+2]-h[i])/h[i]*100})
        if h[i+2] < l[i]: fvg_list.append({"type":"BEAR","top":l[i],"bot":h[i+2],"pct":(l[i]-h[i+2])/l[i]*100})
    return fvg_list[-3:] if fvg_list else []

def get_1h_structure(d60):
    h,l,c,o=d60["h"],d60["l"],d60["c"],d60["o"]
    if len(c)<50: return "none","none",None,[],"none"
    up=sum(1 for i in range(-20,-1) if c[i]>c[i-1]); down=20-up
    trend="UP" if up>=13 else "DOWN" if down>=13 else "RANGE"
    last_high=max(h[-20:-1]); last_low=min(l[-20:-1])
    breaks="BOS_UP" if c[-1]>last_high else "BOS_DOWN" if c[-1]<last_low else "none"
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    ob=None
    for i in range(len(c)-2,len(c)-30,-1):
        if c[i]<o[i] and c[i+1]>o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: ob=(l[i],h[i],"BULL"); break
        if c[i]>o[i] and c[i+1]<o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: ob=(l[i],h[i],"BEAR"); break
    fvg=detect_fvg(h,l)
    tops=[]; bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]: bots.append(l[i])
    reversal="double_top" if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.008 else "double_bottom" if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.008 else "none"
    return trend,breaks,ob,fvg,reversal

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p78=pl+prange*0.78; p58=pl+prange*0.58; p35=pl+prange*0.35; p22=pl+prange*0.22
    big_range_pct=(ph-pl)/(pl or 1)*100
    body=abs(pc-po); upper_wick=ph-max(pc,po); lower_wick=min(pc,po)-pl
    if pc>po and upper_wick>body*1.2 and cc<p78: return "WEAK_BULL_TRAP",ph,big_range_pct
    if pc<po and lower_wick>body*1.2 and cc>p22: return "WEAK_BEAR_TRAP",pl,big_range_pct
    if pc>=p58 and cc>=p35 and cl>=p22 and cc>co: return "BOS_UP_STRONG",ph,big_range_pct
    if pc<=p35 and cc<=p58 and ch<=p78 and cc<co: return "BOS_DOWN_STRONG",pl,big_range_pct
    return None,0,big_range_pct

def fbs_trend_pump_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p78=pl+prange*0.78; p62=pl+prange*0.62; p38=pl+prange*0.38; p22=pl+prange*0.22
    p68=pl+prange*0.68; p32=pl+prange*0.32
    big_range_pct=(ph-pl)/(pl or 1)*100
    if pc>po:
        if cc < p78 and cc < co: return "WEAK_BULL_TRAP_TREND",ph,big_range_pct
        if pc >= p62 and cc >= p32 and cc > p22 and cc > co: return "BOS_UP_TREND_STRONG_32_68",ph,big_range_pct
    if pc<po:
        if cc > p22 and cc > co: return "WEAK_BEAR_TRAP_TREND",pl,big_range_pct
        if pc <= p38 and cc <= p68 and cc < p78 and cc < co: return "BOS_DOWN_TREND_STRONG_32_68",pl,big_range_pct
    return None,0,big_range_pct

def check_tbs(o,h,l,c,crt_low,crt_high,is_buy, has_ob, has_fvg):
    if len(c)<3: return False
    if has_ob and has_fvg:
        if is_buy and c[-1] > o[-1] and c[-1] > c[-2]: return True
        if not is_buy and c[-1] < o[-1] and c[-1] < c[-2]: return True
    if is_buy: return l[-2] < crt_low*1.002 and c[-1] > crt_low*0.998 and c[-1] > o[-1]
    else: return h[-2] > crt_high*0.998 and c[-1] < crt_high*1.002 and c[-1] < o[-1]

# === V36 SMART WALL PREDICTOR - 30 MIN + 10 MIN PRE-WARNING - ALL COINS ===
def check_wall_predictive(s, c, h, crt_high_4h, crt_low_4h):
    live = c[-1]
    if len(c) < 10: return None
    speed_5m = (c[-1] - c[-6]) / 6 if len(c)>=6 else 0
    if speed_5m <= 0: return None

    # Find nearest ceiling wall
    # Round number wall (0.50, 1.00, 0.20 etc)
    # Use 0.05 steps for low price coins like GRASS
    if live < 1:
        round_wall = round(live*20)/20 # 0.05 steps
        if round_wall <= live: round_wall += 0.05
    else:
        round_wall = round(live*2)/2
        if round_wall <= live: round_wall += 0.5

    # Choose closest wall between round and 4H CRT high
    dist_round = abs(round_wall - live)
    dist_crt = abs(crt_high_4h - live) if crt_high_4h > live else 999
    wall = round_wall if dist_round < dist_crt else crt_high_4h
    if wall <= live: return None

    dist_to_wall_pct = (wall - live) / live * 100
    if dist_to_wall_pct > 4 or dist_to_wall_pct < 0.15: return None

    speed_pct_per_5m = speed_5m / live * 100
    if speed_pct_per_5m < 0.03: return None
    mins_to_wall = (dist_to_wall_pct / speed_pct_per_5m) * 5

    # Weakening detection
    upper_wick = h[-1] - max(c[-1], 0)
    vol_weak = (h[-1]-c[-1]) > (c[-1]-min(c[-6:]))*0.5 if len(c)>=6 else False

    dump_target = wall * 0.97 # 3% dump
    if crt_high_4h > 0 and crt_low_4h > 0:
        # More accurate dump target = 35% of range
        dump_target = crt_low_4h + (crt_high_4h - crt_low_4h)*0.35

    now = time.time()
    key30 = f"{s}_30MIN"
    key10 = f"{s}_10MIN"
    keyHit = f"{s}_HIT"

    # 30 MIN WARNING
    if 25 <= mins_to_wall <= 38:
        if now - WALL_ALERTS.get(key30,0) > 3600: # once per hour max
            WALL_ALERTS[key30]=now; save_wall()
            return f"⏰ 30-MIN WALL PREP {s} | Wall {wall:.5f} in ~{mins_to_wall:.0f}m | Price {live:.5f} (+{dist_to_wall_pct:.2f}%) | Take partials, move SL to BE | Dump target {dump_target:.5f} | {get_time_12hr()}"
    # 10 MIN WARNING
    if 8 <= mins_to_wall <= 13:
        if now - WALL_ALERTS.get(key10,0) > 1800:
            WALL_ALERTS[key10]=now; save_wall()
            return f"🔔 10-MIN WALL WARNING {s} | Wall {wall:.5f} in ~{mins_to_wall:.0f}m | EXIT NOW at TOP | Price {live:.5f} | Dump to {dump_target:.5f} in 30-45m | {get_time_12hr()}"
    # WALL HIT
    if mins_to_wall < 4 or dist_to_wall_pct < 0.4:
        if vol_weak and now - WALL_ALERTS.get(keyHit,0) > 1800:
            WALL_ALERTS[keyHit]=now; save_wall()
            return f"🧱 WALL HIT NOW {s} {wall:.5f} | Price {live:.5f} | DUMP STARTING to {dump_target:.5f} in 30-60m | CLOSE LONG, wait for {dump_target:.5f} retest | {get_time_12hr()}"
    return None

def get_perfect_entry(o,h,l,c,ob,is_buy,symbol,crt_low,crt_high,setup_type,bias_4h):
    ob_low,ob_high=ob[0],ob[1]
    prange=ob_high-ob_low
    crt_range_pct=(crt_high-crt_low)/(crt_low or 1)*100
    cfg=PER_COIN_TP.get(symbol, PER_COIN_TP["GRASSUSDT"])
    is_strong_bull_bos = is_buy and bias_4h=="BULL" and setup_type in ["BOS","GRAB"]
    is_strong_bear_bos = not is_buy and bias_4h=="BEAR" and setup_type in ["BOS","GRAB"]
    if is_strong_bull_bos or is_strong_bear_bos:
        if setup_type=="GRAB": sl_pct=cfg["sl_grab"]
        elif setup_type=="REVERSAL": sl_pct=cfg["sl_rev"]
        else: sl_pct=cfg["sl_bos"]
        tp1_pct=0.0433; tp2_pct=0.0876; tp3_pct=0.1117; tp4_pct=0.133
        tp1_pct=max(tp1_pct, crt_range_pct*0.45/100)
        tp2_pct=max(tp2_pct, crt_range_pct*0.85/100)
        tp3_pct=max(tp3_pct, crt_range_pct*1.15/100)
        tp4_pct=max(tp4_pct, crt_range_pct*1.35/100)
        has_tp4=True
    else:
        if setup_type=="GRAB": sl_pct=cfg["sl_grab"]; tp1_pct=max(cfg["tp1"], crt_range_pct*0.45/100); tp2_pct=max(cfg["tp2"], crt_range_pct*0.85/100); tp3_pct=max(cfg["tp3"], crt_range_pct*1.30/100); tp4_pct=tp3_pct; has_tp4=False
        elif setup_type=="REVERSAL": sl_pct=cfg["sl_rev"]; tp1_pct=max(cfg["tp1"]*0.85, crt_range_pct*0.35/100); tp2_pct=max(cfg["tp2"]*0.85, crt_range_pct*0.65/100); tp3_pct=max(cfg["tp3"]*0.85, crt_range_pct*1.0/100); tp4_pct=tp3_pct; has_tp4=False
        else: sl_pct=cfg["sl_bos"]; tp1_pct=max(cfg["tp1"], crt_range_pct*0.40/100); tp2_pct=max(cfg["tp2"], crt_range_pct*0.75/100); tp3_pct=max(cfg["tp3"], crt_range_pct*1.15/100); tp4_pct=tp3_pct; has_tp4=False
    if is_buy:
        entry=ob_low+prange*0.56; sl=entry*(1-sl_pct); tp1=entry*(1+tp1_pct); tp2=entry*(1+tp2_pct); tp3=entry*(1+tp3_pct); tp4=entry*(1+tp4_pct)
    else:
        entry=ob_high-prange*0.56; sl=entry*(1+sl_pct); tp1=entry*(1-tp1_pct); tp2=entry*(1-tp2_pct); tp3=entry*(1-tp3_pct); tp4=entry*(1-tp4_pct)
    risk=abs(entry-sl); rr1=abs(tp1-entry)/(risk or 1e-9)
    return entry,sl,tp1,tp2,tp3,tp4,rr1,crt_range_pct,has_tp4,is_strong_bull_bos or is_strong_bear_bos

def full_scan(s,p):
    d240=kl(p,"Min240"); d60=kl(p,"Min60"); d15=kl(p,"Min15"); d5=kl(p,"Min5")
    if not d240 or not d60 or not d15 or not d5:
        log(f"❌ {s}: NO KLINE DATA -> SKIP"); return
    c,o,h,l=d5["c"],d5["o"],d5["h"],d5["l"]
    now=time.time(); time_12hr=get_time_12hr(); live_price=c[-1]
    buy_key=f"{s}_BUY"; sell_key=f"{s}_SELL"

    # === WALL PREDICTOR CHECK FIRST (before active check) ===
    bias_4h_tmp, crt_low_tmp, crt_high_tmp, _ = get_4h_bias(d240)
    if bias_4h_tmp:
        wall_msg = check_wall_predictive(s, c, h, crt_high_tmp, crt_low_tmp)
        if wall_msg:
            tg(wall_msg)
            log(wall_msg)

    if buy_key in ACTIVE or sell_key in ACTIVE:
        active_key=buy_key if buy_key in ACTIVE else sell_key
        is_active_buy=ACTIVE[active_key]["is_buy"]
        entry_t = ACTIVE[active_key]["t"]
        status, mins_in, max_hold = check_hold_timer(s, entry_t)
        fbs15,_br,_=fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        if not fbs15: fbs15,_br,_=fbs_trend_pump_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        profit=(c[-1]-ACTIVE[active_key]["entry"])/ACTIVE[active_key]["entry"]*100 if is_active_buy else (ACTIVE[active_key]["entry"]-c[-1])/ACTIVE[active_key]["entry"]*100
        log(f"🟡 {s} ACTIVE {active_key} {status} {mins_in:.0f}/{max_hold:.0f}m HOLD {profit:.2f}% | FBS={fbs15}")
        if status == "CLOSE_MAX_EXCEEDED":
            if profit < 0:
                tg(f"❌ {s} TIMER CLOSE {active_key} {profit:.2f}% after {mins_in/60:.1f}H / MAX {max_hold/60:.1f}H - OB FAILED | {time_12hr}")
                del ACTIVE[active_key]; save_active(); return
            elif profit < 1.0:
                tg(f"⚠️ {s} TIMER WEAK CLOSE {active_key} +{profit:.2f}% after {mins_in/60:.1f}H / MAX {max_hold/60:.1f}H | {time_12hr}")
                del ACTIVE[active_key]; save_active(); return
        if status == "MOVE_SL_TO_BE" and not ACTIVE[active_key].get("be_moved"):
            if profit > 0.5:
                tg(f"🟡 {s} TIMER BE MOVE {'BUY' if is_active_buy else 'SELL'} +{profit:.2f}% | {mins_in/60:.1f}H/{max_hold/60:.1f}H MAX | {time_12hr}\nMove SL to BE, letting run")
                ACTIVE[active_key]["be_moved"]=True; ACTIVE[active_key]["last_hold_profit"]=profit; save_active()
        if fbs15 and ("UP" in fbs15 if is_active_buy else "DOWN" in fbs15) and "STRONG" in fbs15:
            if profit-ACTIVE[active_key].get("last_hold_profit",0)>= (2.0 if s in FAST_SYMS else 1.0):
                tg(f"🟡 {s} HOLD {'BUY' if is_active_buy else 'SELL'} +{profit:.2f}% | {time_12hr} | Timer {mins_in/60:.1f}H/{max_hold/60:.1f}H")
                ACTIVE[active_key]["last_hold_profit"]=profit; save_active()
        return

    bias_4h,crt_low_4h,crt_high_4h,key_level=get_4h_bias(d240)
    if not bias_4h: log(f"❌ {s}: 4H NO BIAS -> SKIP"); return
    crt_low_1h=min(d60["l"][-24:]); crt_high_1h=max(d60["h"][-24:])
    trend_1h,breaks_1h,ob_1h,fvg_1h,reversal_1h=get_1h_structure(d60)
    has_fvg=len(fvg_1h)>0; has_ob=ob_1h is not None
    fbs15, top15, brp15 = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
    if not fbs15 or "STRONG" not in fbs15:
        fbs15_2, top15_2, brp15_2 = fbs_trend_pump_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        if fbs15_2 and "STRONG" in fbs15_2: fbs15, top15, brp15 = fbs15_2, top15_2, brp15_2
    log(f"🔍 {s} | 4H:{bias_4h} Key:{key_level:.4f} | 1H:{trend_1h} {breaks_1h} OB:{has_ob} FVG:{has_fvg} REV:{reversal_1h} | 15m:{fbs15} Range:{brp15:.2f}% | Price:{live_price:.6f}")
    if not fbs15 or "STRONG" not in fbs15: log(f" -> {s}: 15m NO BOS STRONG -> SKIP"); return
    is_buy="UP" in fbs15; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"
    if bias_4h=="BULL" and not is_buy: log(f" -> {s}: 4H BULL vs SELL MISMATCH -> SKIP"); return
    if bias_4h=="BEAR" and is_buy: log(f" -> {s}: 4H BEAR vs BUY MISMATCH -> SKIP"); return
    if trend_1h=="UP" and not is_buy: log(f" -> {s}: 1H UP vs SELL MISMATCH -> SKIP"); return
    if trend_1h=="DOWN" and is_buy: log(f" -> {s}: 1H DOWN vs BUY MISMATCH -> SKIP"); return
    if not has_ob and not has_fvg and "TREND" not in fbs15: log(f" -> {s}: NO OB/FVG -> SKIP"); return
    SAME_CD=150*60 if s in FAST_SYMS else 8*3600
    OPP_CD=90*60 if s in FAST_SYMS else 4*3600
    if now-COOLDOWN["signals"].get(key,{}).get("t",0)<SAME_CD: log(f" -> {s}: COOLDOWN SAME -> SKIP"); return
    if now-COOLDOWN["signals"].get(f"{s}_{'SELL' if is_buy else 'BUY'}",{}).get("t",0)<OPP_CD: log(f" -> {s}: COOLDOWN OPP -> SKIP"); return
    if key in LAST_TOP:
        last_top,last_time=LAST_TOP[key]
        if last_top!=0 and abs(top15-last_top)/(last_top or 1)<0.008 and (now-last_time)< (8*3600 if s in FAST_SYMS else 24*3600): log(f" -> {s}: SAME TOP PROTECTION -> SKIP"); return
    crt_low,crt_high = (crt_low_1h,crt_high_1h) if s in FAST_SYMS else (crt_low_4h,crt_high_4h)
    if not check_tbs(o,h,l,c,crt_low,crt_high,is_buy, has_ob, has_fvg): log(f" -> {s}: 5m NO TBS -> SKIP"); return
    if not check_btc_filter(s,is_buy): log(f" -> {s}: BTC DOM BLOCK -> SKIP"); return
    setup_type="BOS"
    if is_buy and l[-2]<crt_low*0.998 and "TREND" in fbs15: setup_type="GRAB"
    if not is_buy and h[-2]>crt_high*1.002 and "TREND" in fbs15: setup_type="GRAB"
    if reversal_1h!="none": setup_type="REVERSAL"
    def get_last_ob_5m():
        atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
        for i in range(len(c)-2,len(c)-60,-1):
            if is_buy and c[i]<o[i] and c[i+1]>o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: return (l[i],h[i])
            if not is_buy and c[i]>o[i] and c[i+1]<o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: return (l[i],h[i])
        return None
    ob_entry = (ob_1h[0],ob_1h[1]) if ob_1h else get_last_ob_5m()
    if not ob_entry: ob_entry=(min(l[-15:]),max(h[-15:]))
    entry,sl,tp1,tp2,tp3,tp4,rr1,crt_pct,has_tp4,is_extended=get_perfect_entry(o,h,l,c,ob_entry,is_buy,s,crt_low,crt_high,setup_type,bias_4h)
    if rr1<1.0 or rr1>8: log(f" -> {s}: RR {rr1:.1f} BAD -> SKIP"); return
    COOLDOWN["signals"][key]={"t":now,"dir":is_buy,"top":top15,"entry":entry}; save()
    LAST_TOP[key]=(top15,now)
    cfg_timer = PER_COIN_TIMER.get(s, {"est_mins":120,"max_mins":360})
    ACTIVE[key]={"entry":entry,"is_buy":is_buy,"t":now,"perp":p,"tp1":tp1,"tp2":tp2,"tp3":tp3,"tp4":tp4,"sl":sl,"highest":entry,"lowest":entry,"last_hold_profit":0,"setup":setup_type,"be_moved":False,"extended":is_extended}; save_active()
    fvg_txt=" + FVG" if has_fvg else ""
    ext_txt=" EXTENDED 11.17%/13.3%" if is_extended else ""
    tp4_txt=f" | TP4: {tp4:.6f} (+13.3%)" if has_tp4 else ""
    tg(f"{'🟢' if is_buy else '🔴'} {s} {side} {setup_type}{ext_txt} | {fbs15} | CONFIRMED\n4H: {bias_4h} Key {key_level:.4f} | 1H: {trend_1h} {breaks_1h} OB:{has_ob} {fvg_txt} Liq:{setup_type} Rev:{reversal_1h} | 15m FBS V36 58/35 | 5m TBS Entry | {time_12hr}\nPrice: {live_price:.6f}\nEntry: {entry:.6f} (OB {ob_entry[0]:.6f}-{ob_entry[1]:.6f})\nSL: {sl:.6f} ({abs(entry-sl)/entry*100:.2f}%) | TP1: {tp1:.6f} | TP2: {tp2:.6f} | TP3: {tp3:.6f}{tp4_txt} | RR {rr1:.1f}R | CRT {crt_pct:.1f}%\n⏱️ TIMER: Est {cfg_timer['est_mins']/60:.1f}H | MAX {cfg_timer['max_mins']/60:.1f}H | Auto close if negative after MAX")

print("=== BOT V36 TIMER 58/35 + EXTENDED 11.17/13.3 + WALL 30/10 MIN ===",flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(f"{s} err {e}", flush=True)
    print("=== SCAN DONE V36 EXTENDED + WALL ===", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(f"{s} loop err {e}", flush=True)
        time.sleep(60)
