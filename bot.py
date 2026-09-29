import time, requests, json, os, sys
from datetime import datetime
import pytz

EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["GRASS_USDT","TAO_USDT","JASMY_USDT","SAND_USDT","SIREN_USDT","LAB_USDT","KOMA_USDT","FARTCOIN_USDT","SENT_USDT"]

TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "8500000000:XXXX"
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID") or "YOUR_CHAT_ID"

COOLDOWN_FILE = "cooldown.json"
ACTIVE_FILE = "active.json"
ACTIVE = json.load(open(ACTIVE_FILE)) if os.path.exists(ACTIVE_FILE) else {}
COOLDOWN = json.load(open(COOLDOWN_FILE)) if os.path.exists(COOLDOWN_FILE) else {"signals":{}}
if "signals" not in COOLDOWN: COOLDOWN={"signals":{}}

def save_a(): json.dump(ACTIVE, open(ACTIVE_FILE,"w"))
def save_c(): json.dump(COOLDOWN, open(COOLDOWN_FILE,"w"))
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=8)
    except: pass
    print(msg)

def kl(symbol, interval):
    try:
        mexc_interval = "Hour4" if interval=="Min240" else interval
        url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={mexc_interval}"
        r = requests.get(url, timeout=10).json()
        d = r["data"] if "data" in r else r
        vols = d.get("vol", d.get("volume", d.get("amount", [0]*300)))
        return {"o":[float(x) for x in d["open"][-200:]],"h":[float(x) for x in d["high"][-200:]],"l":[float(x) for x in d["low"][-200:]],"c":[float(x) for x in d["close"][-200:]],"v":[float(x) for x in vols[-200:]]}
    except Exception as e:
        print(f"kl err {symbol} {e}")
        return None

def get_live_price(s):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={s}"
        r = requests.get(url, timeout=5).json()
        return float((r["data"] if "data" in r else r)["lastPrice"])
    except: return None

def get_pvt(d):
    if not d or len(d["c"])<30: return None,None,None
    pvt=[0]
    for i in range(1,len(d["c"])):
        prev=d["c"][i-1] or 1
        pvt.append(pvt[-1] + ((d["c"][i]-prev)/prev)*d["v"][i])
    sma21=[sum(pvt[max(0,i-20):i+1])/len(pvt[max(0,i-20):i+1]) for i in range(len(pvt))]
    sig=[sum(sma21[max(0,i-8):i+1])/len(sma21[max(0,i-8):i+1]) for i in range(len(sma21))]
    return pvt,sma21,sig

def get_rsi(c, period=14):
    if len(c)<period+1: return 50
    gains=[]; losses=[]
    for i in range(1, len(c)):
        diff=c[i]-c[i-1]
        gains.append(max(diff,0))
        losses.append(max(-diff,0))
    avg_gain=sum(gains[-period:])/period
    avg_loss=sum(losses[-period:])/period
    if avg_loss==0: return 70
    rs=avg_gain/avg_loss
    return 100 - (100/(1+rs))

def get_adx(d, period=14):
    try:
        h,l,c=d["h"],d["l"],d["c"]
        if len(c)<period*2: return 25
        plus_dm=[]; minus_dm=[]; tr=[]
        for i in range(1,len(c)):
            up=h[i]-h[i-1]; down=l[i-1]-l[i]
            plus_dm.append(up if up>down and up>0 else 0)
            minus_dm.append(down if down>up and down>0 else 0)
            tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
        atr=sum(tr[-period:])/period
        if atr==0: return 25
        plus_di=sum(plus_dm[-period:])/period/atr*100
        minus_di=sum(minus_dm[-period:])/period/atr*100
        if plus_di+minus_di==0: return 25
        dx=abs(plus_di-minus_di)/(plus_di+minus_di)*100
        return dx
    except: return 25

def detect_25_shapes(d):
    if not d: return None
    c,h,l = d["c"],d["h"],d["l"]
    def hh(n=10): return max(h[-n:])
    def ll(n=10): return min(l[-n:])
    rng20 = hh(20)-ll(20)
    avg = sum(c[-20:])/20
    if rng20 < avg*0.07: return "BOX_CONSOLIDATION"
    if l[-1]>l[-10] and abs(h[-1]-h[-10])<(h[-1]*0.015): return "ASCENDING_TRIANGLE"
    if h[-1]<h[-10] and abs(l[-1]-l[-10])<(l[-1]*0.015): return "DESCENDING_TRIANGLE"
    if h[-1]<h[-10] and l[-1]>l[-10]: return "SYMMETRICAL_TRIANGLE"
    if h[-1]<h[-5] and l[-1]<l[-5] and (h[-1]-l[-1])<(h[-5]-l[-5])*0.9: return "FALLING_WEDGE_BULLISH"
    if h[-1]>h[-5] and l[-1]>l[-5] and (h[-1]-l[-1])<(h[-5]-l[-5])*0.9: return "RISING_WEDGE_BEARISH"
    if c[-1]>c[-20]*1.05 and rng20 < avg*0.04: return "BULL_FLAG"
    if c[-1]<c[-20]*0.95 and rng20 < avg*0.04: return "BEAR_FLAG"
    if c[-1]>c[-10] and h[-1]<h[-5] and l[-1]>l[-5]: return "BULL_PENNANT"
    if c[-1]<c[-10] and h[-1]<h[-5] and l[-1]>l[-5]: return "BEAR_PENNANT"
    if abs(h[-1]-h[-15])<h[-1]*0.012: return "DOUBLE_TOP_BEARISH"
    if abs(l[-1]-l[-15])<l[-1]*0.012: return "DOUBLE_BOTTOM_BULLISH"
    if len(h)>25 and h[-15]>h[-5] and h[-15]>h[-25]: return "HEAD_SHOULDERS_BEARISH"
    if len(l)>25 and l[-15]<l[-5] and l[-15]<l[-25]: return "INV_HEAD_SHOULDERS_BULLISH"
    if c[-1]>hh(20)*1.002: return "BREAKOUT_BOX_TOP"
    if c[-1]<ll(20)*0.998: return "BREAKDOWN_BOX_BOTTOM"
    if c[-1]>c[-10] and l[-1]>l[-10]: return "ASCENDING_CHANNEL_BULL"
    if c[-1]<c[-10] and h[-1]<h[-10]: return "DESCENDING_CHANNEL_BEAR"
    if c[-20]<c[-10] and c[-1]>c[-10]: return "CUP_AND_HANDLE_BULLISH"
    if abs(h[-1]-h[-8])<avg*0.01 and abs(l[-1]-l[-8])<avg*0.01: return "RECTANGLE_RANGE"
    if h[-1]>h[-2] and l[-1]>l[-2] and c[-1]>c[-2]: return "HIGHER_HIGH_BULLISH"
    if h[-1]<h[-2] and l[-1]<l[-2] and c[-1]<c[-2]: return "LOWER_LOW_BEARISH"
    if c[-1]>c[-2] and h[-1]==hh(5): return "BULLISH_ENGULFING_BREAK"
    if c[-1]<c[-2] and l[-1]==ll(5): return "BEARISH_ENGULFING_BREAK"
    if rng20 < avg*0.12 and c[-1]>avg: return "ROUNDING_BOTTOM_BULLISH"
    return "RANGE_CHOP"

def get_tps_sl(entry, is_buy, d4h, d_daily):
    atr = sum([d4h["h"][i]-d4h["l"][i] for i in range(-14,0)])/14
    ch = max(d_daily["h"][-30:])
    cl = min(d_daily["l"][-30:])
    if is_buy:
        sl = min(d4h["l"][-3:]) * 0.997
        if sl>=entry*0.995: sl=entry*0.97
        tp1 = entry + atr*1.5
        tp2 = ch
    else:
        sl = max(d4h["h"][-3:]) * 1.003
        if sl<=entry*1.005: sl=entry*1.03
        tp1 = entry - atr*1.5
        tp2 = cl
    return tp1, tp2, sl, ch, cl

def manage():
    for s,data in list(ACTIVE.items()):
        price=get_live_price(s)
        if not price: continue
        entry,is_buy,sl=data["entry"],data["is_buy"],data["sl"]
        ch,cl=data.get("crt_high"),data.get("crt_low")
        if not ch: continue
        tp1,tp2=data.get("tp1"),data.get("tp2")
        if is_buy and price<=sl or not is_buy and price>=sl:
            tg(f"❌ STOP {s} {price:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if not data.get("tp1_hit"):
            if is_buy and price>=tp1 or not is_buy and price<=tp1:
                data["tp1_hit"]=True; data["sl"]=entry; save_a()
                tg(f"✅ TP1 {s} {price:.5f} SL→BE\n{get_time()}")
        if is_buy and price>=tp2 or not is_buy and price<=tp2:
            tg(f"✅✅ TP2 JUNCTION {s} {price:.5f} BOX COMPLETE\n{get_time()}"); del ACTIVE[s]; save_a()

LAST_ID=0
def poll_telegram_commands():
    global LAST_ID
    try:
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_ID+1}&timeout=2"
        r=requests.get(url, timeout=5).json()
        for upd in r.get("result",[]):
            LAST_ID=upd["update_id"]
            text=upd.get("message",{}).get("text","").strip()
            if "/status" in text.lower():
                txt=f"V81 GRASS EDITION {get_time()} Hold:{list(ACTIVE.keys()) or 'None'}\n"
                for s in SYMBOLS[:4]:
                    d=kl(s,"Min240"); price=get_live_price(s) or 0
                    if not d: continue
                    _,sma,_=get_pvt(d) or (None,None,None)
                    rsi=get_rsi(d["c"]); adx=get_adx(d)
                    txt+=f"{s} {price:.4f} RSI{int(rsi)} ADX{int(adx)}\n"
                tg(txt)
    except: pass

def scan():
    manage()
    if len(ACTIVE)>=3:
        print(f"3 ACTIVE - SKIP {list(ACTIVE.keys())}")
        return
    try:
        btc=kl("BTC_USDT","Min240")
        if btc and btc["c"][-1] < btc["c"][-2]*0.97:
            print("BTC DUMP PAUSE"); return
    except: pass

    print(f"=== SCAN START {get_time()} ===")
    for s in SYMBOLS:
        if s in ACTIVE:
            print(f"{s} already active skip")
            continue
        d_daily=kl(s,"Day1"); d4h=kl(s,"Min240")
        if not d4h or not d_daily:
            print(f"{s} no data")
            continue

        pvt,sma,sig = get_pvt(d4h)
        if not pvt:
            print(f"{s} no pvt")
            continue
        _,sma_d,_ = get_pvt(d_daily)
        if not sma_d: continue

        rsi = get_rsi(d4h["c"])
        adx = get_adx(d4h)
        slope = sma[-1]-sma[-5]
        vol_ratio = d4h["v"][-1] / (sum(d4h["v"][-15:])/15) if sum(d4h["v"][-15:])>0 else 0

        shape = detect_25_shapes(d4h)

        # LOUD LOG - you will see why
        print(f"{s} Shape:{shape} ADX:{adx:.1f} RSI:{rsi:.1f} Vol:{vol_ratio:.2f}x Slope:{slope:.2f}")

        # === V81 LOOSE FILTERS FOR ALTS ===
        if adx < 12:
            print(f" -> BLOCKED ADX <12")
            continue
        if abs(slope) < abs(sma[-1])*0.0001:
            print(f" -> BLOCKED SLOPE tiny")
            continue
        if vol_ratio < 0.90: # allow 0.9x not 1.15x
            print(f" -> BLOCKED VOL {vol_ratio:.2f}")
            continue
        # DAILY VS 4H REMOVED FOR ALTS - this was killing GRASS!
        # if (sma_d[-1]>sma_d[-5])!= (sma[-1]>sma[-5]): continue

        if shape in ["RANGE_CHOP","BOX_CONSOLIDATION","RECTANGLE_RANGE"]:
            print(f" -> BLOCKED SHAPE {shape}")
            continue

        is_buy = True
        if any(x in shape for x in ["BEARISH","BEAR","DESCENDING","BREAKDOWN","DOUBLE_TOP","HEAD_SHOULDERS","LOWER_LOW"]):
            is_buy=False
        if any(x in shape for x in ["BULLISH","BULL","ASCENDING","BREAKOUT","DOUBLE_BOTTOM","INV_HEAD","HIGHER_HIGH","CUP","FALLING_WEDGE"]):
            is_buy=True
        else:
            is_buy = sma[-1]>sma[-5]

        if is_buy and rsi>78:
            print(f" -> BLOCKED RSI high {rsi}")
            continue
        if not is_buy and rsi<22:
            print(f" -> BLOCKED RSI low {rsi}")
            continue

        k=f"{s}_{shape}_{ 'LONG' if is_buy else 'SHORT'}"
        if time.time()-COOLDOWN["signals"].get(k,0)<3600: # 1h cooldown not 2h
            print(f" -> COOLDOWN {k}")
            continue

        live=get_live_price(s) or d4h["c"][-1]
        tp1,tp2,sl,ch,cl = get_tps_sl(live, is_buy, d4h, d_daily)
        exp = ((tp2-live)/live*100) if is_buy else ((live-tp2)/live*100)

        ACTIVE[s]={"entry":live,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"crt_high":ch,"crt_low":cl,"time":time.time()}; save_a()
        COOLDOWN["signals"][k]=time.time(); save_c()

        tg(f"""{'🟢 BUY READY' if is_buy else '🔴 SELL READY'} {s}
━━━━━━━━━━━━━━
📐 SHAPE: {shape.replace('_',' ')}
📊 PVT: {'GREEN ABOVE RED BULL ✅' if sma[-1]>sma[-5] else 'GREEN BELOW RED BEAR ✅'}
💪 RSI: {rsi:.1f} | ADX: {adx:.1f} TREND ✅
💰 ENTRY {live:.5f}
🛑 SL {sl:.5f} ({abs(live-sl)/live*100:.2f}%)
🎯 TP1 {tp1:.5f}
🎯 TP2 {tp2:.5f} ({exp:.1f}% to CRT)
📦 CRT High {ch:.5f} Low {cl:.5f}
⏰ {get_time()}""")
        break
    print(f"=== SCAN DONE Hold:{list(ACTIVE.keys())} ===")

if "--once" in sys.argv:
    poll_telegram_commands()
    scan()
else:
    print(f"🚀 V81 GRASS EDITION STARTED {get_time()}")
    while True:
        try: poll_telegram_commands(); scan()
        except Exception as e: print(e)
        time.sleep(30)
