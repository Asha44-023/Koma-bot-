import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"wall":{}}
if "wall" not in COOLDOWN: COOLDOWN["wall"]={}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
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
    try:
        r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}", timeout=5).json()
        return float((r.get("data", r))["lastPrice"])
    except: return None
def detect_4h_trend(d4):
    lows = d4["l"][-20:]; highs = d4["h"][-20:]; hl=0; lh=0
    for i in range(1,len(lows)):
        if lows[i] > lows[i-1]: hl+=1
        if highs[i] < highs[i-1]: lh+=1
    if hl >= 12: return "up"
    if lh >= 12: return "down"
    return "neutral"
def get_pure_tick(d15):
    c = d15["c"][-40:]
    diffs=[]
    for i in range(1,len(c)):
        d = abs(c[i]-c[i-1])
        if d>0: diffs.append(d)
    if not diffs: return 0.00001
    diffs.sort()
    tick = diffs[0]
    if tick==0 or tick<1e-12: tick = diffs[len(diffs)//2] if len(diffs)>2 else 0.00001
    return float(tick)
def detect_station_and_parking(d15):
    c=d15["c"][-40:]; h=d15["h"][-40:]; l=d15["l"][-40:]
    if len(c)<40: return None
    HH=max(h); LL=min(l)
    if HH==LL: return None
    tick=get_pure_tick(d15)
    mid=(HH+LL)/2
    zone_low=mid-15*tick; zone_high=mid+15*tick # V97.5 15-tick
    touches=sum(1 for cl in c if zone_low <= cl <= zone_high)
    range_ticks=(HH-LL)/tick if tick!=0 else 9999
    if touches<8: return None # V97.5 was 10
    if range_ticks>220: return None # was 180
    third=(HH-LL)/3; lower_thr=LL+third; upper_thr=LL+third*2
    cnt_lower=0; cnt_middle=0; cnt_upper=0
    for cl in c:
        if cl <= lower_thr: cnt_lower+=1
        elif cl >= upper_thr: cnt_upper+=1
        else: cnt_middle+=1
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
    is_staircase=False
    if len(d15["c"])>=80:
        HH2=max(d15["h"][-80:-40]); LL2=min(d15["l"][-80:-40]); mid2=(HH2+LL2)/2
        range2_ticks=(HH2-LL2)/tick if tick!=0 else 9999
        if range2_ticks<220:
            gap_ticks=abs(mid-mid2)/tick if tick!=0 else 9999
            if 10<gap_ticks<80: is_staircase=True
    face="Rectangle"
    if is_rounded_top: face="Rounded Top"
    elif is_rounded_bottom: face="Rounded Bottom"
    elif is_coil: face="Coil"
    elif is_flag_down: face="Flag Down"
    elif is_flag_up: face="Flag Up"
    elif is_staircase: face="Staircase"
    if cnt_lower>cnt_upper and cnt_lower>cnt_middle: parking="ACCUMULATION_LOWER"
    elif cnt_upper>cnt_lower and cnt_upper>cnt_middle: parking="DISTRIBUTION_UPPER"
    else: parking="NEUTRAL_MIDDLE"
    return {"HH":HH,"LL":LL,"mid":mid,"tick":tick,"touches":touches,"cnt_lower":cnt_lower,"cnt_middle":cnt_middle,"cnt_upper":cnt_upper,"parking":parking,"face":face,"range_ticks":range_ticks,"is_staircase":is_staircase}
def guard_Aplus(d15, d5, trend_4h):
    station=detect_station_and_parking(d15)
    if not station: return None, None, "no station 8+ in 15-tick", None, None, 0, 0, None
    c5=d15["c"]; h5=d15["h"]; l5=d15["l"]; curr=c5[-1]
    HH=station["HH"]; LL=station["LL"]; tick=station["tick"]; face=station["face"]; parking=station["parking"]
    # V97.5: no block on neutral if high quality
    direction=None
    lower_thr=LL+(HH-LL)/3; upper_thr=LL+(HH-LL)/3*2
    # SWEEP CHECK
    has_bear_sweep = any(h>HH for h in h5[-3:])
    has_bull_sweep = any(ll<LL for ll in l5[-3:])
    # A+ logic
    if parking=="ACCUMULATION_LOWER":
        if has_bull_sweep and curr>LL: direction="BUY"
        elif station['touches']>=25 and curr<=lower_thr and curr>LL: direction="BUY" # no sweep needed if high touch
    if parking=="DISTRIBUTION_UPPER":
        if has_bear_sweep and curr<HH: direction="SELL"
        elif station['touches']>=25 and curr>=upper_thr and curr<HH: direction="SELL"
    if not direction and parking=="NEUTRAL_MIDDLE":
        if station['touches']>=20:
            # scalp both edges
            dist_to_HH = abs(curr-HH); dist_to_LL = abs(curr-LL)
            if dist_to_HH < dist_to_LL and curr<HH and (has_bear_sweep or station['touches']>=28):
                direction="SELL"
            elif dist_to_LL <= dist_to_HH and curr>LL and (has_bull_sweep or station['touches']>=28):
                direction="BUY"
            # bias based
            if not direction:
                if trend_4h=="up" and curr>LL: direction="BUY"
                elif trend_4h=="down" and curr<HH: direction="SELL"
                elif trend_4h=="neutral":
                    # your screenshot case: Rectangle NEUTRAL touch33 should SELL at top half
                    if curr >= station['mid']: direction="SELL"
                    else: direction="BUY"
    if not direction:
        reason=f"{face} {parking} L{station['cnt_lower']} M{station['cnt_middle']} U{station['cnt_upper']} touch{station['touches']} range{int(station['range_ticks'])}ticks no sweep"
        return None, (HH+LL)/2, reason, HH, LL, station['cnt_lower'], station['cnt_upper'], station
    reason=f"A+ {direction} {face} {parking} L{station['cnt_lower']} M{station['cnt_middle']} U{station['cnt_upper']} touch{station['touches']} range{int(station['range_ticks'])}ticks"
    pool_15=LL if direction=="BUY" else HH
    return direction, pool_15, reason, HH, LL, station['cnt_lower'], station['cnt_upper'], station

COOLDOWN_MAP={"SIREN_USDT":900,"FARTCOIN_USDT":900,"KOMA_USDT":900,"GRASS_USDT":1200}
DEFAULT_CD=1800
def scan():
    for s, data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        entry, is_buy, sl = data["entry"], data["is_buy"], data["sl"]
        if time.time()-data.get("time", time.time()) > 14400:
            tg(f"⏰ 4H CLOSE {s} {p:.5f} {get_time()} - time out"); del ACTIVE[s]; save_a(); continue
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            tg(f"🔴🔴 STOP {s} {p:.5f} {get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a(); tg(f"🟡 TP1 {s} SL->BE {p:.5f} {get_time()}")
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            tg(f"🟢🟢 TP2 HIT {s} {p:.5f} {get_time()}"); del ACTIVE[s]; save_a()
    if len(ACTIVE)>=3: return
    print(f"=== V97.5 SCALP LOOSE-SWEEP {get_time()} ===")
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1: continue
            trend_4h=detect_4h_trend(d4)
            daily_trend="up" if d1["c"][-1] > d1["c"][-20] else "down"
            bias=trend_4h if trend_4h!="neutral" else daily_trend
            bias_str="BUY" if bias=="up" else "SELL"
            direction, pool_15, reason, HH, LL, cnt_l, cnt_h, station = guard_Aplus(d15, d5, trend_4h)
            print(f"{s} 4H:{trend_4h} BIAS:{bias_str} -> {direction} | {reason}")
            if not direction: continue
            cdsec=COOLDOWN_MAP.get(s, DEFAULT_CD)
            if time.time()-COOLDOWN["signals"].get(s,0)<cdsec: continue
            last_wall=COOLDOWN["wall"].get(s)
            if last_wall:
                tick=station["tick"]
                if abs(HH-last_wall.get("HH",0))<3*tick and abs(LL-last_wall.get("LL",0))<3*tick:
                    print(f" SKIP same station {s}"); continue
            live=get_live_price(s) or d5["c"][-1]
            is_buy=direction=="BUY"
            tick=station["tick"]
            sl=min(d5["l"][-3:])-2*tick if is_buy else max(d5["h"][-3:])+2*tick
            if is_buy: sl=min(sl, LL-2*tick)
            else: sl=max(sl, HH+2*tick)
            range_abs=HH-LL
            tp1=live+range_abs*1.5 if is_buy else live-range_abs*1.5
            tp2=live+range_abs*3 if is_buy else live-range_abs*3
            eta_min = int((range_abs*3)/max(0.00001, max(d5["h"][-12:])-min(d5["l"][-12:]))*60)
            eta_str = f"{max(15,eta_min)}-{max(30,eta_min*2)} min"
            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"time":time.time()}; save_a()
            COOLDOWN["signals"][s]=time.time(); COOLDOWN["wall"][s]={"HH":HH,"LL":LL,"time":time.time()}; save_c()
            color="🟢🟢🟢 BUY" if is_buy else "🔴🔴🔴 SELL"
            msg=f"{color} A+ {s}\n4H {trend_4h} BIAS {bias.upper()} {reason}\nENTRY {live:.6f}\nSL {sl:.6f} 🔴\nTP1 {tp1:.6f} 🟡\nTP2 {tp2:.6f} 🟢\n⏱️ EST HOLD: {eta_str}\n⏰ AUTO-CLOSE: 4H\n{get_time()}"
            tg(msg)
            break
        except Exception as e:
            print(f"SKIP {s} error: {e}"); continue

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(30)
