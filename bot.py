import time, requests, json, os, sys
from datetime import datetime

SYMBOLS = ["GRASSUSDT","TAOUSDT","JASMYUSDT","SANDUSDT","SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"]
SYMBOL_MAP = {s:s for s in SYMBOLS}

TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "YOUR_TOKEN"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT"

ACTIVE_FILE = "active.json"
COOLDOWN_FILE = "cooldown.json"
LAST_FILE = "last_update.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
WARNING_SENT = {}
LAST_UPDATE_ID = 0
PREV_BIAS = {}

if os.path.exists(LAST_FILE):
    try: LAST_UPDATE_ID = json.load(open(LAST_FILE)).get("id",0)
    except: pass

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=5)
    except: pass
    print(msg)

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
        d=closes[-i]-closes[-i-1]
        if d>0: gains+=d
        else: losses+=-d
    if losses==0: return 80
    return 100-(100/(1+gains/losses))

def get_crt_levels(d):
    if not d: return None,None
    return max(d["h"][-30:]), min(d["l"][-30:])

def check_early_warning(s, price, rsi, ch, cl):
    k=f"{s}_warn"; now=time.time()
    if now-WARNING_SENT.get(k,0)<7200: return
    if ch and price>=ch*0.95 and 75<=rsi<80:
        WARNING_SENT[k]=now
        tg(f"⚠️ WARNING {s} OB near HIGH {ch:.5f}\nPrice {price:.5f} RSI {rsi:.1f} ->80 in 1-2H\n{get_time()}")
    if cl and price<=cl*1.05 and 22<rsi<=27:
        WARNING_SENT[k]=now
        tg(f"⚠️ WARNING {s} OS near LOW {cl:.5f}\nPrice {price:.5f} RSI {rsi:.1f} ->22 in 1-2H\n{get_time()}")

def analyze_4h_full(d,s):
    if not d: return "NEUTRAL",0
    ema50=sum(d["c"][-50:])/50
    return ("BULL" if d["c"][-1]>ema50 else "BEAR"), ema50

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
    return f"FBS_{body/prev:.2f}", d15["c"][-2]>d15["o"][-2], body/prev>=0.62

def get_tps(entry,is_buy,ch,cl):
    return (entry+(ch-entry)*0.5, ch) if is_buy else (entry-(entry-cl)*0.5, cl)

def manage():
    for s,data in list(ACTIVE.items()):
        price=get_live_price(s)
        if not price: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        ch,cl=data.get("crt_high"),data.get("crt_low")
        if not ch: continue
        tp1,tp2=get_tps(entry,is_buy,ch,cl)
        if is_buy and price<=sl or not is_buy and price>=sl:
            tg(f"❌ SL {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit"):
            if is_buy and price>=tp1 or not is_buy and price<=tp1:
                data["tp1_hit"]=True; data["sl"]=entry; save_a()
                tg(f"✅ TP1 {s} {price:.5f} SL->BE\n{get_time()}")
        if is_buy and price>=tp2 or not is_buy and price<=tp2:
            tg(f"✅✅ TP2 {s} JUNCTION {price:.5f} CLOSE\n{get_time()}"); del ACTIVE[s]; save_a()

def scan():
    manage()
    if len(ACTIVE)>=2: return
    for s in SYMBOLS:
        if s in ACTIVE or len(ACTIVE)>=2: continue
        d_daily=kl(SYMBOL_MAP[s],"Day1"); d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d15=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d15: continue
        rsi_15=get_rsi(d15["c"],14); ch,cl=get_crt_levels(d_daily)
        live=get_live_price(s) or d15["c"][-1]
        if not ch: continue
        check_early_warning(s,live,rsi_15,ch,cl)

        if live>=ch*0.98 and rsi_15>=80:
            k=f"{s}_SHORT"
            if time.time()-COOLDOWN["signals"].get(k,0)>=1800:
                entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["h"][-2]*1.002
                ACTIVE[s]={"entry":entry,"is_buy":False,"time":time.time(),"sl":sl,"crt_high":ch,"crt_low":cl}; save_a()
                COOLDOWN["signals"][k]=time.time(); save_c()
                tg(f"🔴 SELL FLIP {s} RSI {rsi_15:.1f}\nH {ch:.5f}->L {cl:.5f}\nE {entry:.5f}\n{get_time()}"); break
        if live<=cl*1.02 and rsi_15<=22:
            k=f"{s}_LONG"
            if time.time()-COOLDOWN["signals"].get(k,0)>=1800:
                entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["l"][-2]*0.998
                ACTIVE[s]={"entry":entry,"is_buy":True,"time":time.time(),"sl":sl,"crt_high":ch,"crt_low":cl}; save_a()
                COOLDOWN["signals"][k]=time.time(); save_c()
                tg(f"🟢 BUY FLIP {s} RSI {rsi_15:.1f}\nL {cl:.5f}->H {ch:.5f}\nE {entry:.5f}\n{get_time()}"); break

        rng=ch-cl or 1
        pct_from_low = (live-cl)/rng*100
        is_mid = 15 < pct_from_low < 85
        zone = "LOW" if pct_from_low<=15 else "HIGH" if pct_from_low>=85 else f"MID {pct_from_low:.0f}%"

        bias,_=analyze_4h_full(d240,s)
        prev_bias = PREV_BIAS.get(s)
        PREV_BIAS[s]=bias

        bo,ro,_=detect_ob_1h(d60); bf,rf,_=detect_fvg_1h(d60); bl,rl=detect_liquidity_1h(d60)
        tbs_type,is_tbs=check_crt_tbs(d_daily,d15)
        fbs,is_buy_fbs,is_strong=fbs_strong_breakout_62(d15)

        is_buy=None
        if is_tbs: is_buy="BULL" in tbs_type
        elif is_strong and fbs: is_buy=is_buy_fbs
        else:
            if bo or bf or bl: is_buy=True
            if ro or rf or rl: is_buy=False

        if is_buy is None: continue
        if is_mid and not (is_tbs or is_strong): continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue

        k=f"{s}_{'LONG' if is_buy else 'SHORT'}"
        if time.time()-COOLDOWN["signals"].get(k,0)<1800: continue

        entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["l"][-2]*0.998 if is_buy else d15["h"][-2]*1.002
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time(),"sl":sl,"crt_high":ch,"crt_low":cl}; save_a()
        COOLDOWN["signals"][k]=time.time(); save_c()
        tp1,tp2=get_tps(entry,is_buy,ch,cl)

        if prev_bias and prev_bias!= bias:
            label = f"🔄 TOTAL REVERSAL {prev_bias}->{bias}"
        else:
            label = f"💧 LIQ GRAB → CONTINUE {'UP' if is_buy else 'DOWN'}"

        exp_pct = ((tp2-entry)/entry*100) if is_buy else ((entry-tp2)/entry*100)

        if is_buy:
            if "MID" in zone:
                tg(f"🟢 BUY {zone} {s} {label}\nBUY MID - Back to High GRASS 0.55->0.69\nE {entry:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} ({exp_pct:.1f}%) SL {sl:.5f}\n{tbs_type or fbs} | 4H {bias} | RSI {rsi_15:.1f}\nLive {live:.5f}\n{get_time()}")
            else:
                tg(f"🟢 {s} {zone} {label} RSI {rsi_15:.1f}\nE {entry:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f}\n{tbs_type or fbs}\n{get_time()}")
        else:
            if "MID" in zone:
                tg(f"🔴 SELL {zone} {s} {label}\nSELL MID - Back to Low GRASS 0.65->0.55\nE {entry:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} ({exp_pct:.1f}%) SL {sl:.5f}\n{tbs_type or fbs} | 4H {bias} | RSI {rsi_15:.1f}\nLive {live:.5f}\n{get_time()}")
            else:
                tg(f"🔴 {s} {zone} {label} RSI {rsi_15:.1f}\nE {entry:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f}\n{tbs_type or fbs}\n{get_time()}")
        break

def poll_telegram_commands():
    global LAST_UPDATE_ID, ACTIVE
    try:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_UPDATE_ID+1}&timeout=2"
        r=requests.get(url, timeout=5).json()
        for upd in r.get("result",[]):
            LAST_UPDATE_ID=upd["update_id"]
            json.dump({"id":LAST_UPDATE_ID}, open(LAST_FILE,"w"))
            text=upd.get("message",{}).get("text","").strip()
            if not text.startswith("/"): continue
            if text.startswith("/status"):
                txt=f"V69.1 MID {get_time()} Hold:{list(ACTIVE.keys()) or 'None'}\n"
                for s in SYMBOLS:
                    d15=kl(SYMBOL_MAP[s],"Min15"); dd=kl(SYMBOL_MAP[s],"Day1")
                    if not d15 or not dd: continue
                    rsi=get_rsi(d15["c"]); ch,cl=get_crt_levels(dd); price=get_live_price(s) or d15["c"][-1]
                    rng=ch-cl or 1; pct=(price-cl)/rng*100 if rng else 50
                    zone="MID" if 15<pct<85 else "JUNC"
                    txt+=f"{s} {price:.4f} RSI{int(rsi)} {zone} {pct:.0f}%\n"
                tg(txt)
            elif text.startswith("/rsi"):
                txt=f"RSI {get_time()}\n"
                for s in SYMBOLS:
                    d15=kl(SYMBOL_MAP[s],"Min15")
                    if not d15: continue
                    txt+=f"{s} {get_rsi(d15['c']):.0f}\n"
                tg(txt)
            elif text.startswith("/junctions"):
                txt=""
                for s in SYMBOLS:
                    dd=kl(SYMBOL_MAP[s],"Day1")
                    if not dd: continue
                    ch,cl=get_crt_levels(dd); txt+=f"{s} L{cl:.4f} H{ch:.4f}\n"
                tg(txt)
            elif text.startswith("/close"):
                p=text.split()
                if len(p)>1:
                    sym=p[1].upper()
                    if sym in ACTIVE: del ACTIVE[sym]; save_a(); tg(f"Closed {sym}")
                else: ACTIVE.clear(); save_a(); tg("Closed all")
    except Exception as e: print(f"poll err {e}")

# === FIXED FOR GITHUB ACTIONS ===
if "--once" in sys.argv:
    poll_telegram_commands()
    scan()
    print("DONE --once")
else:
    while True:
        try:
            poll_telegram_commands()
            scan()
        except Exception as e: print(e)
        time.sleep(10)
