import time, requests, json, os
from datetime import datetime

# === CONFIG ===
SYMBOLS = ["GRASSUSDT","TAOUSDT","JASMYUSDT","SANDUSDT","SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"]
SYMBOL_MAP = {s:s for s in SYMBOLS}

TELEGRAM_TOKEN = os.getenv("TG_TOKEN","YOUR_TOKEN_HERE")
TELEGRAM_CHAT = os.getenv("TG_CHAT","YOUR_CHAT_ID")

ACTIVE_FILE = "active.json"
COOLDOWN_FILE = "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
WARNING_SENT = {}
LAST_UPDATE_ID = 0
SILENT_MODE = True

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=5)
    except: pass

def kl(symbol, interval):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit=200"
        r = requests.get(url, timeout=10).json()
        data = r["result"]["list"][::-1]
        return {"o":[float(x[1]) for x in data],"h":[float(x[2]) for x in data],"l":[float(x[3]) for x in data],"c":[float(x[4]) for x in data]}
    except: return None

def get_live_price(s):
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={s}"
        return float(requests.get(url, timeout=5).json()["result"]["list"][0]["lastPrice"])
    except: return None

def get_rsi(closes, period=14):
    if len(closes)<period+1: return 50
    gains,losses=0,0
    for i in range(1,period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>0: gains+=diff
        else: losses+=-diff
    if losses==0: return 80
    rs=gains/losses
    return 100-(100/(1+rs))

def get_crt_levels(d_daily):
    if not d_daily: return None,None
    return max(d_daily["h"][-30:]), min(d_daily["l"][-30:])

# === EARLY WARNING 75/27 ===
def check_early_warning(symbol, live_price, rsi, crt_high, crt_low):
    key=f"{symbol}_warn"; now=time.time()
    if now-WARNING_SENT.get(key,0)<7200: return
    if crt_high and live_price>=crt_high*0.95 and 75<=rsi<80:
        WARNING_SENT[key]=now
        tg(f"⚠️ EARLY WARNING {symbol}\nOVERBOUGHT near HIGH {crt_high:.5f}\nPrice {live_price:.5f} RSI {rsi:.1f} → 80 in 1-2H\n👉 EXIT LONG, READY SHORT to {crt_low:.5f}\n{get_time()}")
    if crt_low and live_price<=crt_low*1.05 and 22<rsi<=27:
        WARNING_SENT[key]=now
        tg(f"⚠️ EARLY WARNING {symbol}\nOVERSOLD near LOW {crt_low:.5f}\nPrice {live_price:.5f} RSI {rsi:.1f} → 22 in 1-2H\n👉 EXIT SHORT, READY LONG to {crt_high:.5f}\n{get_time()}")

def analyze_4h_full(d,s):
    if not d: return "NEUTRAL",0
    c=d["c"]; ema50=sum(c[-50:])/50
    return ("BULL" if c[-1]>ema50 else "BEAR"), ema50

def detect_ob_1h(d): return False,False,None
def detect_fvg_1h(d): return False,False,None
def detect_liquidity_1h(d):
    if not d: return False,False
    if d["h"][-1]>max(d["h"][-10:-1]): return True,False
    if d["l"][-1]<min(d["l"][-10:-1]): return False,True
    return False,False

def check_crt_tbs(d_daily,d15):
    if not d_daily or not d15: return None,False
    low=min(d15["l"][-10:-1]); high=max(d15["h"][-10:-1])
    if d15["l"][-1]<low and d15["c"][-1]>low: return "BULL_TBS",True
    if d15["h"][-1]>high and d15["c"][-1]<high: return "BEAR_TBS",True
    return None,False

def fbs_strong_breakout_62(d15):
    if not d15 or len(d15["c"])<3: return None,None,False
    body=abs(d15["c"][-2]-d15["o"][-2]); prev=abs(d15["c"][-3]-d15["o"][-3])
    if prev==0: return None,None,False
    engulf=body/prev; is_buy=d15["c"][-2]>d15["o"][-2]
    return f"FBS_{engulf:.2f}",is_buy,engulf>=0.62

def get_tps(entry,is_buy,ch,cl):
    if is_buy: return entry+(ch-entry)*0.5, ch
    else: return entry-(entry-cl)*0.5, cl

def manage():
    for s,data in list(ACTIVE.items()):
        price=get_live_price(s)
        if not price: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        ch,cl=data.get("crt_high"),data.get("crt_low")
        if not ch: continue
        tp1,tp2=get_tps(entry,is_buy,ch,cl)

        if is_buy and price<=sl or not is_buy and price>=sl:
            tg(f"❌ SL HIT {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue

        if not data.get("tp1_hit"):
            if is_buy and price>=tp1 or not is_buy and price<=tp1:
                data["tp1_hit"]=True; data["sl"]=entry; save_a()
                tg(f"✅ TP1 HIT {s} {price:.5f} SL->BE\n{get_time()}")

        if is_buy and price>=tp2 or not is_buy and price<=tp2:
            tg(f"✅✅ TP2 HIT {s} JUNCTION {price:.5f} CLOSE\n{get_time()}"); del ACTIVE[s]; save_a()

def scan():
    global ACTIVE
    manage()
    if not SILENT_MODE: print(f"{get_time()} Holding {list(ACTIVE.keys())}")
    if len(ACTIVE)>=2: return

    for s in SYMBOLS:
        if s in ACTIVE or len(ACTIVE)>=2: continue
        d_daily=kl(SYMBOL_MAP[s],"Day1"); d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d15=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d15: continue

        rsi_15=get_rsi(d15["c"],14)
        crt_high,crt_low=get_crt_levels(d_daily)
        live_price=get_live_price(s) or d15["c"][-1]
        if not crt_high: continue

        check_early_warning(s,live_price,rsi_15,crt_high,crt_low)

        bias_4h,_=analyze_4h_full(d240,s)
        bo,ro,_=detect_ob_1h(d60); bf,rf,_=detect_fvg_1h(d60); bl,rl=detect_liquidity_1h(d60)
        tbs_type,is_tbs=check_crt_tbs(d_daily,d15)
        fbs,is_buy_fbs,is_strong=fbs_strong_breakout_62(d15)

        # === V68 RSI FLIP 80/22 UNIVERSAL ===
        if live_price>=crt_high*0.98 and rsi_15>=80:
            k=f"{s}_SHORT"
            if time.time()-COOLDOWN["signals"].get(k,0)<1800: continue
            entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["h"][-2]*1.002
            ACTIVE[s]={"entry":entry,"is_buy":False,"time":time.time(),"sl":sl,"crt_high":crt_high,"crt_low":crt_low}; save_a()
            COOLDOWN["signals"][k]=time.time(); save_c()
            tg(f"🔴 SELL FLIP {s} RSI {rsi_15:.1f}\nHIGH {crt_high:.5f} -> LOW {crt_low:.5f}\nENTRY {entry:.5f} SL {sl:.5f}\n{get_time()}"); break

        if live_price<=crt_low*1.02 and rsi_15<=22:
            k=f"{s}_LONG"
            if time.time()-COOLDOWN["signals"].get(k,0)<1800: continue
            entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["l"][-2]*0.998
            ACTIVE[s]={"entry":entry,"is_buy":True,"time":time.time(),"sl":sl,"crt_high":crt_high,"crt_low":crt_low}; save_a()
            COOLDOWN["signals"][k]=time.time(); save_c()
            tg(f"🟢 BUY FLIP {s} RSI {rsi_15:.1f}\nLOW {crt_low:.5f} -> HIGH {crt_high:.5f}\nENTRY {entry:.5f} SL {sl:.5f}\n{get_time()}"); break

        # MIDDLE 70% NO TRADE
        rng=crt_high-crt_low or 1
        if crt_low+rng*0.15 < live_price < crt_high-rng*0.15 and not is_tbs:
            if not SILENT_MODE: print(f"❌ NO TRADE {s} MIDDLE {live_price:.5f}")
            continue

        is_buy=None
        if is_tbs: is_buy="BULL" in tbs_type
        elif is_strong and fbs: is_buy=is_buy_fbs
        else:
            if bo or bf or bl: is_buy=True
            if ro or rf or rl: is_buy=False
        if is_buy is None or (not is_strong and not is_tbs): continue
        if bias_4h=="BULL" and not is_buy: continue
        if bias_4h=="BEAR" and is_buy: continue

        k=f"{s}_{'LONG' if is_buy else 'SHORT'}"
        if time.time()-COOLDOWN["signals"].get(k,0)<1800: continue
        entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["l"][-2]*0.998 if is_buy else d15["h"][-2]*1.002
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time(),"sl":sl,"crt_high":crt_high,"crt_low":crt_low}; save_a()
        COOLDOWN["signals"][k]=time.time(); save_c()
        tp1,tp2=get_tps(entry,is_buy,crt_high,crt_low)
        tg(f"{'🟢' if is_buy else '🔴'} {s} {tbs_type or fbs} RSI {rsi_15:.1f}\nENTRY {entry:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f}\n{get_time()}"); break

# === TELEGRAM COMMANDS - ONLY REPLY WHEN YOU ASK ===
def poll_telegram_commands():
    global LAST_UPDATE_ID, ACTIVE
    try:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_UPDATE_ID+1}&timeout=2"
        r=requests.get(url, timeout=5).json()
        if not r.get("result"): return
        for upd in r["result"]:
            LAST_UPDATE_ID=upd["update_id"]
            text=upd.get("message",{}).get("text","").strip()
            if not text.startswith("/"): continue

            if text.startswith("/status"):
                txt=f"V68 {get_time()}\nHold: {list(ACTIVE.keys()) or 'None'}\n"
                for s in SYMBOLS:
                    d15=kl(SYMBOL_MAP[s],"Min15"); dd=kl(SYMBOL_MAP[s],"Day1")
                    if not d15 or not dd: continue
                    rsi=get_rsi(d15["c"]); ch,cl=get_crt_levels(dd); price=get_live_price(s) or d15["c"][-1]
                    rng=ch-cl if ch and cl else 1
                    zone="MIDDLE" if cl+rng*0.15 < price < ch-rng*0.15 else "JUNCTION"
                    txt+=f"{s} {price:.4f} RSI{int(rsi)} {zone}\n"
                tg(txt)

            elif text.startswith("/rsi"):
                txt=f"RSI {get_time()}\n"
                for s in SYMBOLS:
                    d15=kl(SYMBOL_MAP[s],"Min15")
                    if not d15: continue
                    rsi=get_rsi(d15["c"]); price=get_live_price(s) or d15["c"][-1]
                    st="🔴80" if rsi>=80 else "🟢22" if rsi<=22 else "⚠️75/27" if rsi>=75 or rsi<=27 else "⏳"
                    txt+=f"{s} {rsi:.0f} {st} {price:.4f}\n"
                tg(txt)

            elif text.startswith("/junctions"):
                txt=f"JUNCTIONS 30D {get_time()}\n"
                for s in SYMBOLS:
                    dd=kl(SYMBOL_MAP[s],"Day1")
                    if not dd: continue
                    ch,cl=get_crt_levels(dd); txt+=f"{s} L{cl:.4f} H{ch:.4f}\n"
                tg(txt)

            elif text.startswith("/close"):
                parts=text.split()
                if len(parts)>1:
                    sym=parts[1].upper()
                    if sym in ACTIVE: del ACTIVE[sym]; save_a(); tg(f"✅ Closed {sym}")
                    else: tg(f"{sym} not active")
                else: ACTIVE.clear(); save_a(); tg("✅ Closed all")

            elif text.startswith("/silent"):
                global SILENT_MODE; SILENT_MODE=True; tg("🔇 Silent ON - only FLIP/TP/WARN")
            elif text.startswith("/loud"):
                SILENT_MODE=False; tg("🔊 Loud ON")

    except Exception as e: print("TG err",e)

while True:
    try:
        poll_telegram_commands()
        scan()
    except Exception as e: print("ERR",e)
    time.sleep(10)
