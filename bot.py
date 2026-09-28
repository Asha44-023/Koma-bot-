import time, requests, json, os, sys
from datetime import datetime

# MEXC SYMBOLS with underscore!
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]
SYMBOL_MAP = {s:s for s in SYMBOLS}

TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "YOUR_TOKEN"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT"

ACTIVE_FILE = "active.json"
COOLDOWN_FILE = "cooldown.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
if "signals" not in COOLDOWN: COOLDOWN={"signals":{}}

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=5)
    except: pass
    print(msg)

def kl(symbol, interval):
    try:
        # Map your intervals to MEXC intervals
        mexc_interval = interval
        if interval == "Min240": mexc_interval = "Hour4"
        if interval == "Min60": mexc_interval = "Min60"
        if interval == "Min15": mexc_interval = "Min15"
        if interval == "Day1": mexc_interval = "Day1"
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={mexc_interval}"
        r = requests.get(url, timeout=10).json()
        d = r["data"] if "data" in r else r
        # MEXC returns column arrays
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]]}
    except Exception as e:
        print(f"kl err {symbol} {e}")
        return None

def get_live_price(s):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}"
        r = requests.get(url, timeout=5).json()
        data = r["data"] if "data" in r else r
        return float(data["lastPrice"])
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

def analyze_4h_full(d,s):
    if not d: return "NEUTRAL",0
    ema50=sum(d["c"][-50:])/50
    return ("BULL" if d["c"][-1]>ema50 else "BEAR"), ema50

def detect_liquidity_1h(d):
    if not d: return False,False
    if d["h"][-1]>max(d["h"][-10:-1]): return True,False
    if d["l"][-1]<min(d["l"][-10:-1]): return False,True
    return False,False

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
            tg(f"❌ STOP {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit"):
            if is_buy and price>=tp1 or not is_buy and price<=tp1:
                data["tp1_hit"]=True; data["sl"]=entry; save_a()
                tg(f"✅ TP1 {s} {price:.5f} SL→BE\n{get_time()}")
        if is_buy and price>=tp2 or not is_buy and price<=tp2:
            tg(f"✅✅ TP2 JUNCTION {s} {price:.5f} BOX COMPLETE\n{get_time()}"); del ACTIVE[s]; save_a()

def poll_telegram_commands():
    try:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-5&timeout=2"
        r=requests.get(url, timeout=5).json()
        for upd in r.get("result",[])[-3:]:
            text=upd.get("message",{}).get("text","").strip()
            if not text: continue
            print(f"CMD: {text}")
            if "/status" in text.lower():
                txt=f"V70 MEXC BOX {get_time()} Hold:{list(ACTIVE.keys()) or 'None'}\n"
                for s in SYMBOLS[:6]:
                    d15=kl(s,"Min15"); price=get_live_price(s) or 0
                    if not d15: continue
                    txt+=f"{s} {price:.4f} RSI{int(get_rsi(d15['c']))}\n"
                tg(txt)
    except Exception as e: print(f"poll err {e}")

def scan():
    manage()
    if len(ACTIVE)>=2: return
    for s in SYMBOLS:
        if s in ACTIVE: continue
        d_daily=kl(s,"Day1"); d240=kl(s,"Min240"); d15=kl(s,"Min15")
        if not d240 or not d15: continue
        rsi_15=get_rsi(d15["c"],14); ch,cl=get_crt_levels(d_daily)
        live=get_live_price(s) or d15["c"][-1]
        if not ch: continue
        rng=ch-cl or 1
        pct=(live-cl)/rng*100
        if 15<pct<85: zone=f"MID {pct:.0f}%"
        else: zone="JUNC"
        is_mid=15<pct<85
        bias,_=analyze_4h_full(d240,s)
        bl,rl=detect_liquidity_1h(d15)
        fbs,is_buy_fbs,is_strong=fbs_strong_breakout_62(d15)
        is_buy=None
        if is_strong and fbs: is_buy=is_buy_fbs
        else:
            if bl: is_buy=True
            if rl: is_buy=False
        if is_buy is None: continue
        if is_mid and not is_strong: continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue
        k=f"{s}_{'LONG' if is_buy else 'SHORT'}"
        if time.time()-COOLDOWN["signals"].get(k,0)<1800: continue
        entry=(d15["h"][-2]+d15["l"][-2])/2; sl=d15["l"][-2]*0.998 if is_buy else d15["h"][-2]*1.002
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time(),"sl":sl,"crt_high":ch,"crt_low":cl}; save_a()
        COOLDOWN["signals"][k]=time.time(); save_c()
        tp1,tp2=get_tps(entry,is_buy,ch,cl)
        exp_pct=((tp2-entry)/entry*100) if is_buy else ((entry-tp2)/entry*100)
        if is_buy:
            tg(f"""🟢 BUY {s} {zone}
━━━━━━━━━━━━━━
🟩 BUY BOX: {d15['l'][-2]:.5f} - {d15['h'][-2]:.5f}
🟥 SELL BOX: {ch:.5f} (Long TP)
TP1 {tp1:.5f} TP2 {tp2:.5f} ({exp_pct:.1f}%)
ENTRY {entry:.5f} SL {sl:.5f}
{fbs} 4H {bias} RSI {rsi_15:.0f}
Live {live:.5f} {get_time()}""")
        else:
            tg(f"""🔴 SELL {s} {zone}
━━━━━━━━━━━━━━
🟥 SELL BOX: {d15['l'][-2]:.5f} - {d15['h'][-2]:.5f}
🟩 BUY BOX: {cl:.5f} (Short TP)
TP1 {tp1:.5f} TP2 {tp2:.5f} ({exp_pct:.1f}%)
ENTRY {entry:.5f} SL {sl:.5f}
{fbs} 4H {bias} RSI {rsi_15:.0f}
Live {live:.5f} {get_time()}""")
        break

if "--once" in sys.argv:
    poll_telegram_commands()
    scan()
else:
    while True:
        try: poll_telegram_commands(); scan()
        except Exception as e: print(e)
        time.sleep(10)
