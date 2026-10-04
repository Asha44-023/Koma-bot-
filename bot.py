import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","C_USDT","G_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE, STATS_FILE = "active.json", "cooldown.json", "stats.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"wall":{},"daily_pnl":6.53,"last_day":"2026-10-04"}
STATS = json.load(open(STATS_FILE)) if os.path.exists(STATS_FILE) else {"total":0,"tp2":0,"sl":0,"sl_after_tp1":0,"timeout_win":0,"timeout_loss":0,"be_stop":0,"by_face":{},"by_symbol":{}}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
if "daily_pnl" not in COOLDOWN: COOLDOWN["daily_pnl"]=6.53
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def save_s(): json.dump(STATS, open(STATS_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":m}, timeout=10)
    except: pass
    print(m)
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
    for try_sym in [s, s.replace("_","")]:
        try:
            r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={try_sym}", timeout=5).json()
            p = float((r.get("data", r))["lastPrice"])
            if p>0: return p
        except: pass
    return None
def get_funding(symbol):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}", timeout=5).json()
        return float(r.get("data", r).get("fundingRate", 0))*100
    except: return 0.0
def get_liquidity_reason(s, HH, fund):
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/depth/{s}?depth=20", timeout=5).json()
        data = r.get("data",{})
        asks = data.get("asks", [])[:10]; bids = data.get("bids", [])[:10]
        ask_vol = sum(float(a[1]) for a in asks) if asks else 0
        bid_vol = sum(float(b[1]) for b in bids) if bids else 0
        ask_wall = float(asks[0][0]) if asks else HH
        bid_wall = float(bids[0][0]) if bids else HH
        reason = f"Swept {HH:.5f}->{ask_wall:.5f} ({ask_vol/1000:.1f}k asks / {bid_vol/1000:.1f}k bids)"
        if fund>=0.015: reason += f" + fund {fund:.3f}%"
        return reason, ask_wall, bid_wall, ask_vol, bid_vol
    except:
        return f"Swept pool {HH:.5f}", HH, HH, 0, 0
def reversal_or_continuation(station, direction):
    face = station.get("face","Rectangle"); parking = station.get("parking","NEUTRAL_MIDDLE")
    if direction=="BUY":
        if face=="Rounded Top" and parking=="DISTRIBUTION_UPPER": return "REVERSAL - top distribution, grab then dump"
        if face=="Rounded Bottom": return "REVERSAL - bottom accumulation, pump starting"
        if face=="Flag Down" and parking=="ACCUMULATION_LOWER": return "CONTINUATION - flag down, pump continues"
        return "CONTINUATION - breakout"
    else:
        if face=="Rounded Bottom" and parking=="ACCUMULATION_LOWER": return "REVERSAL - bottom, grab then pump"
        if face=="Rounded Top": return "REVERSAL - top distribution starting"
        if face=="Flag Up": return "CONTINUATION - flag up, dump continues"
        return "CONTINUATION - breakdown"
def funding_label(rate_percent, direction):
    if direction=="BUY":
        if rate_percent >= 0.08: return "DANGER", "crowded longs - SKIP"
        if rate_percent >= 0.03: return "CAUTION", "longs crowded - 0.3x"
        if rate_percent <= -0.10: return "SAFE", "squeeze fuel - BIG"
        return "SAFE", "pump ready"
    else:
        if rate_percent <= -0.08: return "DANGER", "crowded shorts - SKIP"
        if rate_percent <= -0.03: return "CAUTION", "shorts crowded - 0.3x"
        if rate_percent >= 0.10: return "SAFE", "dump fuel - BIG"
        return "SAFE", "dump ready"
def get_daily_bias_TW(d1):
    if len(d1["c"]) < 3: return "NEUTRAL"
    T_high = d1["h"][-3]; T_low = d1["l"][-3]; W_close = d1["c"][-2]
    if W_close > T_high: return "BULLISH"
    if W_close < T_low: return "BEARISH"
    return "NEUTRAL"
def detect_4h_trend_fallback(d4):
    lows = d4["l"][-20:]; highs = d4["h"][-20:]
    hl=sum(1 for i in range(1,len(lows)) if lows[i]>lows[i-1]); lh=sum(1 for i in range(1,len(highs)) if highs[i]<highs[i-1])
    if hl>=12: return "BULLISH"
    if lh>=12: return "BEARISH"
    return "NEUTRAL"
def find_fvgs_4h(d4):
    bull, bear = [], []; h=d4["h"]; l=d4["l"]
    for i in range(2, len(h)):
        if l[i] > h[i-2]: bull.append({'top': l[i], 'bottom': h[i-2]})
        if h[i] < l[i-2]: bear.append({'top': l[i-2], 'bottom': h[i]})
    return bull[-3:], bear[-3:]
def get_pure_tick(d15):
    h=d15["h"][-20:]; l=d15["l"][-20:]; avg_range = sum(h[i]-l[i] for i in range(20)) / 20
    tick = avg_range / 10
    if tick < 0.00001: tick = 0.00001
    return float(tick)
def detect_station_and_parking(d15, symbol=""):
    c=d15["c"][-40:]; h=d15["h"][-40:]; l=d15["l"][-40:]
    if len(c)<12: return None
    is_new = symbol in ["C_USDT","G_USDT"]
    HH=max(h[-12:]); LL=min(l[-12:])
    if HH==LL: return None
    tick=get_pure_tick(d15); mid=(HH+LL)/2
    zone_low=mid-18*tick; zone_high=mid+18*tick
    touches=sum(1 for cl in c[-12:] if zone_low <= cl <= zone_high)
    range_ticks=(HH-LL)/tick if tick!=0 else 9999
    min_touch = 2 if is_new else 5
    max_range = 2000 if is_new else 600
    if touches<min_touch or range_ticks>max_range: return None
    third=(HH-LL)/3; lower_thr=LL+third; upper_thr=LL+third*2
    cnt_lower=sum(1 for cl in c[-12:] if cl <= lower_thr)
    cnt_upper=sum(1 for cl in c[-12:] if cl >= upper_thr)
    cnt_middle=12-cnt_lower-cnt_upper
    h20=h[-20:]; l20=l[-20:]; h_first=sum(h20[:10])/10; h_last=sum(h20[-10:])/10; l_first=sum(l20[:10])/10; l_last=sum(l20[-10:])/10
    is_coil=(h_last < h_first-5*tick) and (l_last > l_first+5*tick)
    h_mid=max(h[13:27]); h_edges=max(max(h[:13]), max(h[27:])); l_mid=min(l[13:27]); l_edges=min(min(l[:13]), min(l[27:]))
    is_rounded_top=(h_mid > h_edges+20*tick); is_rounded_bottom=(l_mid < l_edges-20*tick)
    is_flag_down=(h_last < h_first-10*tick) and (l_last < l_first-10*tick); is_flag_up=(h_last > h_first+10*tick) and (l_last > l_first+10*tick)
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
def guard_V99(d15, d5, d4, d1, symbol=""):
    daily_raw = get_daily_bias_TW(d1); daily_bias = daily_raw
    if daily_bias == "NEUTRAL": daily_bias = detect_4h_trend_fallback(d4)
    station=detect_station_and_parking(d15, symbol)
    if not station and symbol in ["C_USDT","G_USDT","SAND_USDT","SENT_USDT","GRASS_USDT"]:
        c=d15["c"][-12:]; h=d15["h"][-12:]; l=d15["l"][-12:]
        if len(c)>=6:
            HH=max(h); LL=min(l); tick=get_pure_tick(d15)
            station={"HH":HH,"LL":LL,"mid":(HH+LL)/2,"tick":tick,"touches":6,"cnt_lower":2,"cnt_middle":8,"cnt_upper":2,"parking":"NEUTRAL_MIDDLE","face":"Rectangle","range_ticks":(HH-LL)/tick}
    if not station: return None, None, f"no station", None, None, 0,0,station, daily_bias
    bull_fvgs, bear_fvgs = find_fvgs_4h(d4)
    curr = d15["c"][-1]; HH, LL = station["HH"], station["LL"]; tick=station["tick"]; range_abs=HH-LL
    fvg_bull_5, fvg_bear_5 = detect_FVG(d5)
    bos_bull, bos_bear, swing_h, swing_l = detect_MSS_BOS(d5)
    eq_high, eq_low, upper_sweep, lower_sweep, upper_dist, lower_dist = detect_true_liquidity_pool(d15, d5)
    buy_triggers=[]; sell_triggers=[]
    if lower_sweep and curr>eq_low: buy_triggers.append(("SWEEP_L", eq_low-2*tick, f"SweepL {int(lower_dist)}t"))
    if bos_bull: buy_triggers.append(("BOS_UP", LL, "BOS_UP"))
    if upper_sweep and curr<eq_high: sell_triggers.append(("SWEEP_H", eq_high+2*tick, f"SweepH {int(upper_dist)}t"))
    if bos_bear: sell_triggers.append(("BOS_DOWN", HH, "BOS_DOWN"))
    if not buy_triggers and not sell_triggers: return None, None, f"no trigger", HH, LL, 0,0, station, daily_bias
    direction=None
    if buy_triggers and sell_triggers:
        direction="BUY" if lower_dist>=upper_dist else "SELL"
    elif buy_triggers: direction="BUY"
    else: direction="SELL"
    if direction=="BUY":
        trigger_type, pool_15, reason_extra = buy_triggers[0]
        if not bull_fvgs and symbol not in ["C_USDT","G_USDT"] and "SWEEP" not in trigger_type:
            return None, None, f"no bull FVG", HH, LL, 0,0, station, daily_bias
    else:
        trigger_type, pool_15, reason_extra = sell_triggers[0]
        if not bear_fvgs and symbol not in ["C_USDT","G_USDT"] and "SWEEP" not in trigger_type:
            return None, None, f"no bear FVG", HH, LL, 0,0, station, daily_bias
    min_dist=range_abs*0.4
    if direction=="BUY":
        if curr-pool_15<min_dist: pool_15=curr-min_dist
        for fvg_low,fvg_high,idx in fvg_bull_5:
            if pool_15>fvg_low and pool_15<fvg_high: pool_15=fvg_low-2*tick
    else:
        if pool_15-curr<min_dist: pool_15=curr+min_dist
        for fvg_high,fvg_low,idx in fvg_bear_5:
            if pool_15<fvg_low and pool_15>fvg_high: pool_15=fvg_low+2*tick
    reason=f"V103.3 BOTH {direction} {daily_bias} {trigger_type} {station['face']} {reason_extra}"
    return direction, pool_15, reason, HH, LL, station['cnt_lower'], station['cnt_upper'], station, daily_bias
COOLDOWN_MAP={"SIREN_USDT":900,"FARTCOIN_USDT":900,"KOMA_USDT":900,"GRASS_USDT":1200}
DEFAULT_CD=1800
def update_stats_on_close(symbol, data, pnl, close_type):
    STATS["total"] = STATS.get("total",0)+1
    face = data.get("face","Unknown"); sym = symbol.replace("_USDT","")
    if face not in STATS["by_face"]: STATS["by_face"][face]={"w":0,"l":0,"be":0}
    if sym not in STATS["by_symbol"]: STATS["by_symbol"][sym]={"w":0,"l":0}
    if close_type=="TP2": STATS["tp2"]+=1; STATS["by_face"][face]["w"]+=1; STATS["by_symbol"][sym]["w"]+=1
    elif close_type=="SL":
        STATS["sl"]+=1
        if data.get("tp1_hit"): STATS["sl_after_tp1"]+=1; STATS["by_face"][face]["be"]+=1
        else: STATS["by_face"][face]["l"]+=1; STATS["by_symbol"][sym]["l"]+=1
    elif close_type=="TIME_WIN": STATS["timeout_win"]+=1; STATS["by_face"][face]["w"]+=1
    elif close_type=="TIME_LOSS": STATS["timeout_loss"]+=1; STATS["by_face"][face]["l"]+=1
    elif close_type=="BE": STATS["be_stop"]+=1; STATS["by_face"][face]["be"]+=1
    save_s()
def scan():
    today = get_today()
    if COOLDOWN.get("last_day")!= today:
        if COOLDOWN.get("last_day") and COOLDOWN["last_day"]!= "": COOLDOWN["daily_pnl"]=0
        COOLDOWN["last_day"]=today; save_c()
    if COOLDOWN["daily_pnl"] <= -3.0:
        tg(f"⛔ DAILY STOP - Loss {COOLDOWN['daily_pnl']:.2f}% - PAUSE 24h {get_time()}"); return
    btc_chg = 0
    try:
        r = requests.get("https://contract.mexc.com/api/v1/contract/kline/BTC_USDT?interval=Min15", timeout=5).json()
        d = r.get("data", r)
        if isinstance(d, dict) and "data" in d: d = d["data"]
        c = [float(x) for x in d["close"][-4:]]
        if len(c)>=4: btc_chg = (c[-1]-c[-4])/c[-4]*100
    except: btc_chg=0
    if btc_chg <= -0.8: tg(f"⚠️ PAUSE - BTC DUMPING {btc_chg:.2f}% - No new LONGS {get_time()}"); return
    for s, data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry, is_buy, sl = data["entry"], data["is_buy"], data["sl"]
        held = time.time()-data.get("time", time.time())
        if held < 0: held = 0
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            if data.get("tp1_hit") and abs(p-entry)/entry*100 <0.3:
                update_stats_on_close(s,data,pnl,"BE"); tg(f"🟡 BE STOP {s} {p:.5f} PnL {pnl:.2f}% after TP1 {get_time()}")
            else:
                update_stats_on_close(s,data,pnl,"SL"); tg(f"🔴🔴 STOP {s} {p:.5f} PnL {pnl:.2f}% Daily {COOLDOWN['daily_pnl']:.2f}% {get_time()}")
            del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            profit = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            tg(f"🟢 TP1 BEST GRAB {s} @ {p:.5f} (+{profit:.2f}%)\nNEXT {data['tp2']:.5f} | {data.get('next_move','')}\n{get_time()}")
        # FIXED 4H - only close if NO TP1 hit (let winners run)
        if held > 14400 and not data.get("tp1_hit"):
            pnl = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            ct="TIME_WIN" if pnl>0 else "TIME_LOSS"; update_stats_on_close(s,data,pnl,ct)
            tg(f"⏰ 4H CLOSE {s} {p:.5f} {pnl:.2f}% {get_time()}"); del ACTIVE[s]; save_a(); continue
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            profit = ((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c(); update_stats_on_close(s,data,profit,"TP2")
            tg(f"🟢🟢 TP2 HIT {s} {p:.5f} +{profit:.2f}% {get_time()}"); del ACTIVE[s]; save_a()
    if len(ACTIVE)>=3: return
    print(f"=== V103.3 BEST GRAB BOTH {get_time()} Daily {COOLDOWN['daily_pnl']:.2f}% ===")
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1: continue
            direction, pool_15, reason, HH, LL, cnt_l, cnt_h, station, eff_bias = guard_V99(d15, d5, d4, d1, s)
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
            liq_reason, ask_wall, bid_wall, ask_vol, bid_vol = get_liquidity_reason(s, HH, fund)
            next_move = reversal_or_continuation(station, direction)
            sl=pool_15
            tick_sz = station["tick"]*2
            if is_buy:
                tp1 = ask_wall if ask_wall > live + tick_sz else live + tick_sz*5
                tp2 = tp1 * 1.008
            else:
                tp1 = bid_wall if bid_wall < live - tick_sz else live - tick_sz*5
                tp2 = tp1 * 0.992
            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"HH":HH,"LL":LL,"time":time.time(),"fund":fund,"face":station["face"],"liq_reason":liq_reason,"next_move":next_move}; save_a()
            COOLDOWN["signals"][s]=time.time(); COOLDOWN["wall"][s]={"HH":HH,"LL":LL,"time":time.time()}; save_c()
            if is_buy:
                msg=(f"🟢🟢🟢 BUY {s.replace('_USDT','')} @ {live:.6f}\n"
                     f"{eff_bias} {station['face']} {station['parking']} T{station['touches']}\n"
                     f"NEXT POOL: {tp1:.6f} ({ask_vol/1000:.1f}k asks)\n"
                     f"{next_move}\n"
                     f"SL {sl:.6f} | GRAB {tp1:.6f} | EXT {tp2:.6f}\n"
                     f"FUND {fund:.3f}% {f_label}\n{liq_reason}\nV103.3 {get_time()}")
            else:
                msg=(f"🔴🔴🔴 SELL {s.replace('_USDT','')} @ {live:.6f}\n"
                     f"{eff_bias} {station['face']} {station['parking']} T{station['touches']}\n"
                     f"NEXT POOL: {tp1:.6f} ({bid_vol/1000:.1f}k bids)\n"
                     f"{next_move}\n"
                     f"SL {sl:.6f} | GRAB {tp1:.6f} | EXT {tp2:.6f}\n"
                     f"FUND {fund:.3f}% {f_label}\n{liq_reason}\nV103.3 {get_time()}")
            tg(msg)
            break
        except Exception as e:
            print(f"SKIP {s} error: {e}"); continue
if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(10)
