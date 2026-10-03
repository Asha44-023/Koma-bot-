import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","C_USDT","G_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"wall":{},"daily_pnl":0,"last_day":""}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
if "daily_pnl" not in COOLDOWN: COOLDOWN["daily_pnl"]=0
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":m}, timeout=10)
    except: pass
    print(m)

# --- YOUR EXISTING FUNCS KEEP SAME ---
def kl(symbol, interval):
    sec_map = {"Min5":300,"Min15":900,"Hour4":14400,"Day1":86400}
    sec = sec_map.get(interval, 300)
    end = int(time.time()); start = end - sec*300
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10).json()
        d = r.get("data", r)
        if isinstance(d, dict) and "data" in d: d = d["data"]
        if not isinstance(d, dict) or "open" not in d: return None
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]],"v":[float(x) for x in (d.get("vol") or [0]*200)[-200:]]}
    except: return None
def get_live_price(s):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}", timeout=5).json()
        return float((r.get("data", r))["lastPrice"])
    except: return None
def get_funding(symbol):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}"
        r = requests.get(url, timeout=5).json()
        rate = float(r.get("data", r).get("fundingRate", 0))
        return rate * 100
    except:
        try:
            r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={symbol}", timeout=5).json()
            rate = float(r.get("data", {}).get("fundingRate", 0))
            return rate * 100
        except: return 0.0
def get_btc_dump():
    try:
        r = requests.get("https://contract.mexc.com/api/v1/contract/kline/BTC_USDT?interval=Min15", timeout=5).json()
        d = r.get("data", r)
        if isinstance(d, dict) and "data" in d: d = d["data"]
        c = [float(x) for x in d["close"][-4:]]
        if len(c)>=4: return (c[-1]-c[-4])/c[-4]*100 # 1h change
        return 0.0
    except: return 0.0

# --- NEW TIGHT FUNDING LOGIC = CUTS 95% OF DUST ---
def funding_label(rate_percent, direction):
    if direction=="BUY":
        if rate_percent >= 0.03: return "DANGER", "crowded longs - SKIP" # GRASS 0.025 -> was SAFE now CAUTION, 0.033 -> DANGER
        if rate_percent >= 0.01: return "CAUTION", "longs crowded - 0.3x size only"
        if rate_percent <= -0.10: return "SAFE", "squeeze fuel - big size" # SAND -0.589 -> BIG
        return "SAFE", "pump ready"
    else: # SELL
        if rate_percent <= -0.03: return "DANGER", "crowded shorts - SKIP"
        if rate_percent <= -0.01: return "CAUTION", "shorts crowded - 0.3x size"
        if rate_percent >= 0.10: return "SAFE", "dump fuel - big size"
        return "SAFE", "dump ready"

def get_daily_bias_TW(d1):
    if len(d1["c"]) < 3: return "NEUTRAL"
    T_high = d1["h"][-3]; T_low = d1["l"][-3]; W_close = d1["c"][-2]
    if W_close > T_high: return "BULLISH"
    if W_close < T_low: return "BEARISH"
    return "NEUTRAL"
def detect_4h_trend_fallback(d4):
    lows = d4["l"][-20:]; highs = d4["h"][-20:]
    hl=sum(1 for i in range(1,len(lows)) if lows[i]>lows[i-1])
    lh=sum(1 for i in range(1,len(highs)) if highs[i]<highs[i-1])
    if hl>=12: return "BULLISH"
    if lh>=12: return "BEARISH"
    return "NEUTRAL"
def find_fvgs_4h(d4):
    bull, bear = [], []
    h=d4["h"]; l=d4["l"]
    for i in range(2, len(h)):
        if l[i] > h[i-2]: bull.append({'top': l[i], 'bottom': h[i-2]})
        if h[i] < l[i-2]: bear.append({'top': l[i-2], 'bottom': h[i]})
    return bull[-3:], bear[-3:]
def get_pure_tick(d15):
    h=d15["h"][-20:]; l=d15["l"][-20:]
    avg_range = sum(h[i]-l[i] for i in range(20)) / 20
    tick = avg_range / 10
    if tick < 0.00001: tick = 0.00001
    return float(tick)
def detect_station_and_parking(d15):
    c=d15["c"][-40:]; h=d15["h"][-40:]; l=d15["l"][-40:]
    if len(c)<40: return None
    HH=max(h[-12:]); LL=min(l[-12:])
    if HH==LL: return None
    tick=get_pure_tick(d15)
    mid=(HH+LL)/2
    zone_low=mid-18*tick; zone_high=mid+18*tick
    touches=sum(1 for cl in c[-12:] if zone_low <= cl <= zone_high)
    range_ticks=(HH-LL)/tick if tick!=0 else 9999
    if touches<6 or range_ticks>400: return None
    third=(HH-LL)/3; lower_thr=LL+third; upper_thr=LL+third*2
    cnt_lower=sum(1 for cl in c[-12:] if cl <= lower_thr)
    cnt_upper=sum(1 for cl in c[-12:] if cl >= upper_thr)
    cnt_middle=12-cnt_lower-cnt_upper
    h20=h[-20:]; l20=l[-20:]
    h_first=sum(h20[:10])/10; h_last=sum(h20[-10:])/10
    l_first=sum(l20[:10])/10; l_last=sum(l20[-10:])/10
    is_coil=(h_last < h_first-5*tick) and (l_last > l_first+5*tick)
    h_mid=max(h[13:27]); h_edges=max(max(h[:13]), max(h[27:]))
    l_mid=min(l[13:27]); l_edges=min(min(l[:13]), min(l[27:]))
    is_rounded_top=(h_mid > h_edges+20*tick)
    is_rounded_bottom=(l_mid < l_edges-20*tick)
    is_flag_down=(h_last < h_first-10*tick) and (l_last < l_first-10*tick)
    is_flag_up=(h_last > h_first+10*tick) and (l_last > l_first+10*tick)
    face="Rectangle"
    if is_rounded_top: face="Rounded Top"
    elif is_rounded_bottom: face="Rounded Bottom"
    elif is_coil: face="Coil"
    elif is_flag_down: face="Flag Down"
    elif is_flag_up: face="Flag Up"
    if cnt_lower>cnt_upper and cnt_lower>cnt_middle: parking="ACCUMULATION_LOWER"
    elif cnt_upper>cnt_lower and cnt_upper>cnt_middle: parking="DISTRIBUTION_UPPER"
    else: parking="NEUTRAL_MIDDLE"
    return {"HH":HH,"LL":LL,"mid":mid,"tick":tick,"touches":touches,"cnt_lower":cnt_lower,"cnt_middle":cnt_middle,"cnt_upper":cnt_upper,"parking":parking,"face":face,"range_ticks":range_ticks}
def detect_FVG(d):
    h=d["h"]; l=d["l"]; fvg_bull=[]; fvg_bear=[]
    for i in range(2, len(h)):
        if l[i] > h[i-2]: fvg_bull.append((h[i-2], l[i], i))
        if h[i] < l[i-2]: fvg_bear.append((h[i], l[i-2], i))
    return fvg_bull[-3:], fvg_bear[-3:]
def detect_MSS_BOS(d):
    h=d["h"][-20:]; l=d["l"][-20:]; c=d["c"][-1]
    last_swing_high=max(h[:-3]); last_swing_low=min(l[:-3])
    return c > last_swing_high, c < last_swing_low, last_swing_high, last_swing_low
def detect_true_liquidity_pool(d15, d5):
    h15=d15["h"][-12:]; l15=d15["l"][-12:]; tick=get_pure_tick(d15)
    eq_high = max(h15); eq_low = min(l15)
    h5_max=max(d5["h"][-5:]); l5_min=min(d5["l"][-5:])
    return eq_high, eq_low, h5_max > eq_high, l5_min < eq_low, (h5_max-eq_high)/tick if h5_max>eq_high else 0, (eq_low-l5_min)/tick if l5_min<eq_low else 0
def guard_V99(d15, d5, d4, d1):
    daily_raw = get_daily_bias_TW(d1)
    daily_bias = daily_raw
    if daily_bias == "NEUTRAL": daily_bias = detect_4h_trend_fallback(d4)
    station=detect_station_and_parking(d15)
    if not station: return None, None, f"no station", None, None, 0,0,station, daily_bias
    if daily_bias == "NEUTRAL": return None, None, f"SKIP NEUTRAL", None, None, 0,0, station, daily_bias
    bull_fvgs, bear_fvgs = find_fvgs_4h(d4)
    last_4h_close = d4["c"][-1]; curr = d15["c"][-1]
    effective_bias = daily_bias; flip_reason = ""
    if daily_bias=="BEARISH" and bear_fvgs and last_4h_close > bear_fvgs[-1]['top']:
        effective_bias="BULLISH_FLIP"; flip_reason=f"BearFVG {bear_fvgs[-1]['top']:.5f} DISRESPECTED"
    if daily_bias=="BULLISH" and bull_fvgs and last_4h_close < bull_fvgs[-1]['bottom']:
        effective_bias="BEARISH_FLIP"; flip_reason=f"BullFVG {bull_fvgs[-1]['bottom']:.5f} DISRESPECTED"
    HH, LL = station["HH"], station["LL"]; tick=station["tick"]; range_abs=HH-LL
    fvg_bull_5, fvg_bear_5 = detect_FVG(d5)
    bos_bull, bos_bear, swing_h, swing_l = detect_MSS_BOS(d5)
    eq_high, eq_low, upper_sweep, lower_sweep, upper_dist, lower_dist = detect_true_liquidity_pool(d15, d5)
    if lower_sweep and curr <= eq_low: return None, None, f"no reclaim", HH, LL, 0,0, station, effective_bias
    if upper_sweep and curr >= eq_high: return None, None, f"no reject", HH, LL, 0,0, station, effective_bias
    direction=None; pool_15=None; reason_extra=""; trigger_type=""
    if effective_bias in ["BULLISH","BULLISH_FLIP"]:
        if not bull_fvgs: return None, None, f"no bull FVG", HH, LL, 0,0, station, effective_bias
        if lower_sweep and curr>eq_low:
            direction="BUY"; pool_15=eq_low-2*tick; trigger_type="SWEEP_L"; reason_extra=f"{flip_reason} SweepL {int(lower_dist)}t"
        elif bos_bull:
            direction="BUY"; pool_15=LL; trigger_type="BOS_UP"; reason_extra=f"{flip_reason} BOS_UP"
    if effective_bias in ["BEARISH","BEARISH_FLIP"]:
        if not bear_fvgs: return None, None, f"no bear FVG", HH, LL, 0,0, station, effective_bias
        if upper_sweep and curr<eq_high:
            direction="SELL"; pool_15=eq_high+2*tick; trigger_type="SWEEP_H"; reason_extra=f"{flip_reason} SweepH {int(upper_dist)}t"
        elif bos_bear:
            direction="SELL"; pool_15=HH; trigger_type="BOS_DOWN"; reason_extra=f"{flip_reason} BOS_DOWN"
    if not direction: return None, None, f"no trigger", HH, LL, 0,0, station, effective_bias
    min_dist=range_abs*0.4
    if direction=="BUY":
        if curr-pool_15<min_dist: pool_15=curr-min_dist
        for fvg_low,fvg_high,idx in fvg_bull_5:
            if pool_15>fvg_low and pool_15<fvg_high: pool_15=fvg_low-2*tick
    else:
        if pool_15-curr<min_dist: pool_15=curr+min_dist
        for fvg_high,fvg_low,idx in fvg_bear_5:
            if pool_15<fvg_low and pool_15>fvg_high: pool_15=fvg_low+2*tick
    reason=f"V100 {direction} {effective_bias} {trigger_type} {station['face']} {reason_extra}"
    return direction, pool_15, reason, HH, LL, station['cnt_lower'], station['cnt_upper'], station, effective_bias
COOLDOWN_MAP={"SIREN_USDT":900,"FARTCOIN_USDT":900,"KOMA_USDT":900,"GRASS_USDT":1200}
DEFAULT_CD=1800
def scan():
    # DAILY RESET
    today = get_today()
    if COOLDOWN.get("last_day")!= today:
        COOLDOWN["daily_pnl"]=0
        COOLDOWN["last_day"]=today
        save_c()
    if COOLDOWN["daily_pnl"] <= -3.0:
        tg(f"⛔ DAILY STOP - Loss {COOLDOWN['daily_pnl']:.2f}% - PAUSE 24h {get_time()}")
        return

    btc_chg = get_btc_dump()
    # NEW: -0.8% blocks longs (would have blocked LAB)
    if btc_chg <= -0.8:
        tg(f"⚠️ PAUSE - BTC DUMPING {btc_chg:.2f}% - No new LONGS {get_time()}")
        # STILL CLOSE ACTIVE IF HELD >2h
        for s, data in list(ACTIVE.items()):
            p=get_live_price(s)
            if p and time.time()-data.get("time",0) > 7200:
                loss = ((p-data["entry"])/data["entry"]*100) if data["is_buy"] else ((data["entry"]-p)/data["entry"]*100)
                COOLDOWN["daily_pnl"]+=loss; save_c()
                tg(f"⚠️ FORCE CLOSE {s} BTC CRASH {btc_chg:.1f}% @ {p:.5f} PnL {loss:.2f}% {get_time()}")
                del ACTIVE[s]; save_a()
        return

    for s, data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry, is_buy, sl = data["entry"], data["is_buy"], data["sl"]
        held = time.time()-data.get("time", time.time())
        # FIX: STOP CHECK EVERY LOOP - MARKET EXIT - NO -5% SLIP
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            loss = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=loss; save_c()
            tg(f"🔴🔴 STOP {s} {p:.5f} PnL {loss:.2f}% Daily {COOLDOWN['daily_pnl']:.2f}% {get_time()}"); del ACTIVE[s]; save_a(); continue
        if held < 7200:
            if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
                profit = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
                COOLDOWN["daily_pnl"]+=profit; save_c()
                tg(f"🟢🟢 TP2 HIT {s} {p:.5f} +{profit:.2f}% {get_time()}"); del ACTIVE[s]; save_a()
            continue
        if held > 14400:
            pnl = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"⏰ 4H CLOSE {s} {p:.5f} {pnl:.2f}% {get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True
            buffer_sl = entry * 0.998 if is_buy else entry * 1.002
            data["sl"]=buffer_sl; save_a()
            tg(f"🟡 TP1 {s} SL->BE {buffer_sl:.6f} ({p:.5f}) {get_time()}")
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            profit = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"🟢🟢 TP2 HIT {s} {p:.5f} {get_time()}"); del ACTIVE[s]; save_a()
    if len(ACTIVE)>=3: return
    print(f"=== V100 TIGHT FUND 0.01% SAFE {get_time()} BTC {btc_chg:.2f}% Daily {COOLDOWN['daily_pnl']:.2f}% ===")
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1: continue
            direction, pool_15, reason, HH, LL, cnt_l, cnt_h, station, eff_bias = guard_V99(d15, d5, d4, d1)
            if not direction: continue
            cdsec=COOLDOWN_MAP.get(s, DEFAULT_CD)
            if time.time()-COOLDOWN["signals"].get(s,0)<cdsec: continue
            last_wall=COOLDOWN["wall"].get(s)
            if last_wall and station:
                tick=station["tick"]
                if abs(HH-last_wall.get("HH",0))<3*tick and abs(LL-last_wall.get("LL",0))<3*tick: continue
            fund = get_funding(s)
            f_label, f_msg = funding_label(fund, direction)
            if f_label=="DANGER": print(f" SKIP {s} FUND {fund:.4f}% {f_msg}"); continue
            live=get_live_price(s) or d5["c"][-1]
            is_buy=direction=="BUY"
            tick=station["tick"]; range_abs=HH-LL
            sl=pool_15
            tp1=live+range_abs*1.5 if is_buy else live-range_abs*1.5
            tp2=live+range_abs*3 if is_buy else live-range_abs*3
            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time(),"fund":fund}; save_a()
            COOLDOWN["signals"][s]=time.time(); COOLDOWN["wall"][s]={"HH":HH,"LL":LL,"time":time.time()}; save_c()
            if f_label=="SAFE":
                emoji="🟢🟢🟢" if is_buy else "🔴🔴🔴"
                size_text="BIG SIZE" if abs(fund)>0.08 else "NORMAL SIZE"
                msg=(f"{emoji} STRONG {direction} {s.replace('_USDT','')} @ {live:.6f}\n"
                     f"{eff_bias} {station['face']} {int(station['range_ticks'])}t\n"
                     f"SL {sl:.6f} TP1 {tp1:.6f} TP2 {tp2:.6f}\n"
                     f"FUND {fund:.3f}% {f_label} - {f_msg} -> {size_text}\n"
                     f"Hold 2h min, 4h max\n{get_time()}")
            else:
                emoji="🟡" if is_buy else "🟠"
                msg=(f"{emoji} {direction} {s.replace('_USDT','')} @ {live:.6f} CAUTION 0.3x\n"
                     f"{eff_bias} {station['face']}\n"
                     f"SL {sl:.6f} TP {tp1:.6f}\n"
                     f"FUND {fund:.3f}% {f_label} - {f_msg}\n{get_time()}")
            tg(msg)
            break
        except Exception as e:
            print(f"SKIP {s} error: {e}"); continue
if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(10) # FASTER CHECK = CUTS SLIPPAGE
