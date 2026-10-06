import time, requests, json, os, sys
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT","C_USDT","G_USDT","ZEC_USDT","PEPE_USDT","VELVET_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{},"daily_pnl":0,"last_day":"2026-10-04"}
if "signals" not in COOLDOWN: COOLDOWN["signals"]={}
def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def fmt(p):
    if p is None: return "0"
    if p < 0.01: return f"{p:.8f}"
    elif p < 1: return f"{p:.6f}"
    else: return f"{p:.4f}"
def bold(t):
    m = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.-_",
        "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗.-_"
    )
    return str(t).translate(m)
def tg(m):
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":m}, timeout=10)
        print(f"TG resp {r.status_code} {r.text[:150]}")
    except Exception as e:
        print(f"TG err {e}")
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
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]]}
    except: return None
def get_live_price(s):
    for try_sym in [s, s.replace("_","")]:
        try:
            r = requests.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={try_sym}", timeout=5).json()
            return float((r.get("data", r))["lastPrice"])
        except: pass
    return None
def get_tick(d):
    h=d["h"][-20:]; l=d["l"][-20:]
    avg = sum(h[i]-l[i] for i in range(20))/20
    return max(avg/10, 0.00001)
def detect_shape(d, label=""):
    if len(d["c"])<14: return None
    h=d["h"][-20:]; l=d["l"][-20:]; c=d["c"][-20:]; o=d["o"][-20:]
    HH=max(h[-12:]); LL=min(l[-12:]); rng=HH-LL or 0.00001
    flat=rng*0.35
    h0,h1=h[-12],h[-1]; l0,l1=l[-12],l[-1]
    bullish = sum(1 for i in range(len(c)) if c[i] > o[i])
    ratio = bullish / len(c) * 100
    higher_lows = sum(1 for i in range(len(l)-5, len(l)-1) if l[i+1] > l[i])
    lower_highs = sum(1 for i in range(len(h)-5, len(h)-1) if h[i+1] < h[i])
    wicks_down = sum(1 for i in range(-8,0) if l[i] < LL*0.998 and c[i] > LL)
    wicks_up = sum(1 for i in range(-8,0) if h[i] > HH*1.002 and c[i] < HH)
    fake_up = h[-1] > HH*1.005 and c[-1] < HH
    fake_down = l[-1] < LL*0.995 and c[-1] > LL
    manip=""
    if wicks_down>=2 and fake_down: manip="LIQ_GRAB_LONG + FAKE_DOWN"
    elif wicks_down>=2: manip="LIQ_GRAB_LONG"
    elif wicks_up>=2 and fake_up: manip="LIQ_GRAB_SHORT + FAKE_UP"
    elif wicks_up>=2: manip="LIQ_GRAB_SHORT"
    elif fake_up: manip="FAKE BREAKOUT UP"
    elif fake_down: manip="FAKE BREAKDOWN"
    shape="RECT_ACC"; exp="UP"
    if abs(h1-h0)<flat and abs(l1-l0)<flat:
        if ratio >= 60 or higher_lows >=3: shape="RECT_ACC"; exp="UP"
        elif ratio <= 40 or lower_highs >=3: shape="RECT_DIST"; exp="DOWN"
        else: shape="RECT_ACC" if l1>=l0 else "RECT_DIST"; exp="UP" if l1>=l0 else "DOWN"
    elif abs(h1-h0)<flat and l1>l0+flat: shape="ASC_TRI"; exp="UP"
    elif abs(l1-l0)<flat and h1<h0-flat: shape="DESC_TRI"; exp="DOWN"
    elif h1<h0-flat and l1<l0-flat:
        if higher_lows >=2: shape="DOUBLE_BOTTOM"; exp="UP"
        else: shape="FALL_WEDGE" if abs(h1-h0)>abs(l1-l0)*1.2 else "BULL_FLAG"; exp="UP"
    elif h1>h0+flat and l1>l0+flat:
        if lower_highs >=2 and ratio <= 45: shape="DOUBLE_TOP"; exp="DOWN"
        else: shape="RISE_WEDGE" if abs(l1-l0)>abs(h1-l0)*1.2 else "BEAR_FLAG"; exp="DOWN"
    elif h1<h0-flat and l1>l0+flat: shape="SYM_TRI"; exp="UP" if ratio>=50 else "DOWN"
    if higher_lows >=3 and LL == min(l[-8:]): shape="DOUBLE_BOTTOM"; exp="UP"
    if ratio >=60 and higher_lows>=2 and exp=="DOWN" and label=="DAY":
        shape="RECT_ACC"; exp="UP"
        if manip=="": manip="OVR_BUY (60% bulls + HL)"
    if "LONG" in manip and exp=="UP": exp="STRONG_UP"
    if "SHORT" in manip and exp=="DOWN": exp="STRONG_DOWN"
    return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":get_tick(d),"face":shape,"expected":exp,"tf":label,"ratio":ratio,"hl":higher_lows,"manip":manip}

def get_day_bias(d1,d4):
    b=detect_shape(d1,"DAY")
    if not b:
        hl=sum(1 for i in range(1,20) if d4["l"][-i]>d4["l"][-i-1])
        return ("BULLISH" if hl>=12 else "BEARISH"), None
    if "UP" in b["expected"]: return "BULLISH", b
    if "DOWN" in b["expected"]: return "BEARISH", b
    return "NEUTRAL", b

def find_recent_box(d15, live):
    h_all = d15["h"][-96:]; l_all = d15["l"][-96:]; c_all = d15["c"][-96:]
    for wid in range(12, 48):
        for off in range(1, 72):
            end = len(h_all)-off; start = end-wid
            if start < 0: continue
            HH = max(h_all[start:end]); LL = min(l_all[start:end])
            rng = HH-LL or 0.00001
            full_range = max(h_all)-min(l_all) or rng
            if rng > full_range*0.85: continue
            if rng < full_range*0.03: continue
            last_close = c_all[-1]
            broke_up = last_close > HH*1.001 or live > HH*1.001
            broke_down = last_close < LL*0.999 or live < LL*0.999
            if broke_up:
                return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":rng/10,"expected":"UP","tf":f"BROKE {off*15}m ago Box {fmt(LL)}-{fmt(HH)} {wid*15//60}h wide","age":off*15}
            if broke_down:
                return {"HH":HH,"LL":LL,"range":rng,"lvl_38":LL+rng*0.38,"lvl_62":LL+rng*0.62,"tick":rng/10,"expected":"DOWN","tf":f"BROKE {off*15}m ago Box {fmt(LL)}-{fmt(HH)} {wid*15//60}h wide","age":off*15}
    return None

def guard_V126(d15,d5,d4,d1,symbol):
    bias, dbox = get_day_bias(d1,d4)
    if not dbox: return None,None,"no day box",None,None,None,bias
    pattern_emoji = "🟢" if "BULLISH" in bias else "🔴" if "BEARISH" in bias else "⚪️"
    pattern_info = f"{pattern_emoji} PATTERN {dbox['face']} {dbox['ratio']:.0f}% bull HL:{dbox['hl']} {dbox['manip']}"
    if bias=="NEUTRAL": return None,None,f"{pattern_info} -> NEUTRAL wait",None,None,dbox,bias
    live=get_live_price(symbol) or d5["c"][-1]
    hbox=find_recent_box(d15, live)
    if not hbox:
        return None,None,f"{pattern_info} | no breakout yet waiting",None,None,dbox,bias
    HH,LL=hbox["HH"],hbox["LL"]; rng=hbox["range"]
    c15=d15["c"][-1]
    if bias=="BULLISH" and hbox["expected"]=="UP":
        if LL*0.97 < c15 < HH*1.08 or abs(c15 - hbox["lvl_38"]) < rng*0.85:
            is_liq = "LONG" in dbox["manip"] or hbox.get("age",0) < 60
            sl = LL * (0.985 if is_liq else 0.991)
            return "BUY", sl, f"{pattern_info} + V126 BULL {dbox['face']} + {hbox['tf']} + RETEST", HH, LL, dbox, bias
    if bias=="BEARISH" and hbox["expected"]=="DOWN":
        if LL*0.92 < c15 < HH*1.03 or abs(c15 - hbox["lvl_62"]) < rng*0.85:
            is_liq = "SHORT" in dbox["manip"] or hbox.get("age",0) < 60
            sl = HH * (1.015 if is_liq else 1.009)
            return "SELL", sl, f"{pattern_info} + V126 BEAR {dbox['face']} + {hbox['tf']} + RETEST", HH, LL, dbox, bias
    return None,None,f"{pattern_info} | broke but price {fmt(c15)} not back to box waiting retest",HH,LL,dbox,bias

def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today:
        COOLDOWN["daily_pnl"]=0; COOLDOWN["last_day"]=today; save_c()
    if COOLDOWN["daily_pnl"] <= -3: print(f"PAUSE {COOLDOWN['daily_pnl']}"); return
    for s,data in list(ACTIVE.items()):
        p=get_live_price(s)
        if not p: continue
        sym = s.replace("_USDT","")
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            emoji="🟢" if pnl>0 else "🔴"
            tg(f"{emoji} {bold(f'STOP {sym} {pnl:.2f}% @ {fmt(p)}')}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit") and ((is_buy and p>=data["tp1"]) or (not is_buy and p<=data["tp1"])):
            data["tp1_hit"]=True; data["sl"]=entry; save_a()
            tg(f"💚 {bold(f'TP1 {sym} @ {fmt(p)} -> SL BE')}")
        if (is_buy and p>=data["tp2"]) or (not is_buy and p<=data["tp2"]):
            profit=((p-entry)/entry*100) if is_buy else ((entry-p)/entry*100)
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"💚 {bold(f'TP2 {sym} +{profit:.2f}% CLOSED')}"); del ACTIVE[s]; save_a()
    print(f"--- SCAN V126.3 COLOR BOLD {get_time()} ACTIVE:{len(ACTIVE)} {list(ACTIVE.keys())} PNL:{COOLDOWN['daily_pnl']:.2f}% ---")
    if len(ACTIVE)>=5:
        print(f"MAX ACTIVE {len(ACTIVE)} - managing only")
        return
    for s in SYMBOLS:
        try:
            d5=kl(s,"Min5"); d15=kl(s,"Min15"); d4=kl(s,"Hour4"); d1=kl(s,"Day1")
            if not d5 or not d15 or not d4 or not d1: continue
            direction, pool, reason, HH, LL, dbox, bias = guard_V126(d15,d5,d4,d1,s)
            face=dbox['face'] if dbox else "NO-BOX"
            manip=dbox['manip'] if dbox and 'manip' in dbox else ""
            print(f"{s.replace('_USDT',''):10} DAY:{bias:8} {face:15} {manip:20} -> {reason}")
            if not direction: continue
            if time.time()-COOLDOWN["signals"].get(s,0) < 3600: continue
            live=get_live_price(s) or d5["c"][-1]
            is_buy=direction=="BUY"
            now = datetime.now(EAT)
            candles_since_midnight = int((now.hour*60 + now.minute)/15) + 1
            candles_since_midnight = min(candles_since_midnight, len(d15["h"]))
            today_high = max(d15["h"][-candles_since_midnight:])
            today_low = min(d15["l"][-candles_since_midnight:])
            yest_high = d1["h"][-2]
            yest_low = d1["l"][-2]
            box_h = HH-LL if HH and LL else live*0.02
            sym = s.replace("_USDT","")
            if is_buy:
                tp1 = today_high; tp2 = max(yest_high, today_high*1.005, HH + box_h*1.0)
                tp1 = max(tp1, live*1.01); tp2 = max(tp2, live*1.025)
                sl = pool
                rr = (tp2-live)/(live-sl) if live!=sl else 0
                msg = f"💚 {bold(f'BUY {sym} @ {fmt(live)}')}\n🧩 {bold(face)} | 🟢 {bold(bias)}\n🛡️ {bold(f'SL {fmt(sl)}')} | 🎯 {bold(f'TP1 {fmt(tp1)} TP2 {fmt(tp2)}')}\n📈 {bold(f'RR 1:{rr:.1f}')} | 📦 {bold(f'Box {fmt(LL)}-{fmt(HH)}')}"
            else:
                tp1 = today_low; tp2 = min(yest_low, today_low*0.995, LL - box_h*1.0)
                tp1 = min(tp1, live*0.99); tp2 = min(tp2, live*0.975)
                sl = pool
                rr = (live-tp2)/(sl-live) if sl!=live else 0
                msg = f"❤️ {bold(f'SELL {sym} @ {fmt(live)}')}\n🧩 {bold(face)} | 🔴 {bold(bias)}\n🛡️ {bold(f'SL {fmt(sl)}')} | 🎯 {bold(f'TP1 {fmt(tp1)} TP2 {fmt(tp2)}')}\n📈 {bold(f'RR 1:{rr:.1f}')} | 📦 {bold(f'Box {fmt(LL)}-{fmt(HH)}')}"
            ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":pool,"tp1":tp1,"tp2":tp2,"HH":HH,"LL":LL,"time":time.time(),"face":face}; save_a()
            COOLDOWN["signals"][s]=time.time(); save_c()
            tg(msg)
        except Exception as e:
            print(f"{s} err {e}"); continue
    print(f"V126.3 done {get_time()} ACTIVE:{len(ACTIVE)}")
if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(10)
