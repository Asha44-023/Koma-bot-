# BOT V66.1 SIMPLE - BUY/SELL with TP/SL + Reversal Only
import time, json, requests, fcntl, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
FAST_COINS={"SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"}
SLOW_COINS={"GRASSUSDT","TAOUSDT","SANDUSDT","JASMYUSDT"}

JULY_LEVELS={
    "GRASSUSDT":0.60,"TAOUSDT":302.49,"JASMYUSDT":0.004947,
    "SANDUSDT":0.04277,"FARTCOINUSDT":0.1705,"SENTUSDT":0.02105,
    "SIRENUSDT":0.02279,"LABUSDT":0.05348,"KOMAUSDT":0.018985
}
AUTO_TP={
    "GRASSUSDT":{"sl":0.022,"tp4":0.30},"KOMAUSDT":{"sl":0.022,"tp4":0.30},
    "FARTCOINUSDT":{"sl":0.025,"tp4":0.28},"SENTUSDT":{"sl":0.022,"tp4":0.22},
    "SANDUSDT":{"sl":0.012,"tp4":0.10},"TAOUSDT":{"sl":0.015,"tp4":0.12},
    "JASMYUSDT":{"sl":0.015,"tp4":0.12},"LABUSDT":{"sl":0.025,"tp4":0.35},"SIRENUSDT":{"sl":0.022,"tp4":0.25}
}

COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"; LOCK_FILE="/tmp/bot.lock"; JOURNAL_FILE="winloss.json"; WEEK_FILE="week_tracker.json"; TREND_FILE="last_trend.json"
COOLDOWN={"signals":{}}; ACTIVE={}; JOURNAL={"wins":0,"losses":0,"history":[]}
WEEK={"start_date":datetime.now().strftime("%Y-%m-%d"),"end_date":(datetime.now()+timedelta(days=7)).strftime("%Y-%m-%d")}
LAST_TREND={"trend":"RANGE"}

def save_c(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_a(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
def save_j(): open(JOURNAL_FILE,"w").write(json.dumps(JOURNAL, indent=2))
def save_w(): open(WEEK_FILE,"w").write(json.dumps(WEEK, indent=2))
def save_t(): open(TREND_FILE,"w").write(json.dumps(LAST_TREND))
def get_time():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")
def get_eat_hour():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).hour
    except: return datetime.now(timezone(timedelta(hours=3))).hour
def tg(msg):
    print(msg,flush=True)
    try:
        import os; token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
        if token and chat: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
    except: pass
def get_live_price(sym):
    try: return float(requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={sym}", timeout=4).json()["price"])
    except: return None
def kl(sym,interval):
    headers={"User-Agent":"Mozilla/5.0"}
    spot_sym=sym.replace("_",""); spot_iv={"Min15":"15m","Min60":"60m","Min240":"4h"}.get(interval,"15m")
    urls=[f"https://contract.mexc.com/api/v1/contract/kline/{sym}?interval={interval}",f"https://api.mexc.com/api/v3/klines?symbol={spot_sym}&interval={spot_iv}&limit=200"]
    for url in urls:
        try:
            r=requests.get(url,timeout=10,headers=headers).json()
            data=r.get("data",[]) if isinstance(r,dict) else r
            if isinstance(data,dict) and "close" in data and len(data["close"])>20: return {"o":[float(x) for x in data["open"]],"h":[float(x) for x in data["high"]],"l":[float(x) for x in data["low"]],"c":[float(x) for x in data["close"]]}
            if isinstance(data,list) and len(data)>20:
                o,h,l,c=[],[],[],[]
                for k in data:
                    try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4]))
                    except: continue
                if len(c)>20: return {"o":o,"h":h,"l":l,"c":c}
        except: continue
    return None
def analyze_4h(d, symbol):
    if len(d["c"])<60: return "RANGE"
    rl=min(d["l"][-20:]); pl=min(d["l"][-50:-20]); ema50=sum(d["c"][-50:])/50; curr=d["c"][-1]
    thr=0.008 if symbol in FAST_COINS else 0.002
    if rl>pl*(1+thr) and curr>ema50: return "BULL"
    if rl<pl*(1-thr) and curr<ema50: return "BEAR"
    lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2
    if symbol in SLOW_COINS:
        if curr>mid and curr>ema50: return "BULL"
        if curr<mid and curr<ema50: return "BEAR"
    return "RANGE"
def detect_ob_1h(d):
    bull=bear=False
    if len(d["c"])<10: return False,False
    for i in range(-6,-1):
        body=abs(d["c"][i]-d["o"][i]); rng=d["h"][i]-d["l"][i] or 1
        if d["c"][i]<d["o"][i] and d["c"][-1]>d["h"][i] and body/rng>0.4: bull=True
        if d["c"][i]>d["o"][i] and d["c"][-1]<d["l"][i] and body/rng>0.4: bear=True
    return bull,bear
def detect_fvg_1h(d):
    bull=bear=False
    if len(d["c"])<10: return False,False
    for i in range(-10,-2):
        if d["l"][i]>d["h"][i-2]: bull=True
        if d["h"][i]<d["l"][i-2]: bear=True
    return bull,bear
def detect_liquidity_1h(d):
    bull=bear=False
    if len(d["c"])<20: return False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2])
    if d["h"][-2]>recent_high and d["c"][-1]<recent_high: bear=True
    if d["l"][-2]<recent_low and d["c"][-1]>recent_low: bull=True
    return bull,bear
def detect_breaker_1h(d):
    bull=bear=False
    if len(d["c"])<20: return False,False
    for i in range(-18,-5):
        ob_high=d["h"][i]; ob_low=d["l"][i]
        if d["c"][i]<d["o"][i]:
            broken=any(d["c"][j]>ob_high for j in range(i+1,-2))
            if broken and d["l"][-1]<=ob_high and d["l"][-1]>=ob_low*0.995: bull=True
        if d["c"][i]>d["o"][i]:
            broken=any(d["c"][j]<ob_low for j in range(i+1,-2))
            if broken and d["h"][-1]>=ob_low and d["h"][-1]<=ob_high*1.005: bear=True
    return bull,bear
def check_1h_confluence(d1, is_buy, is_slow):
    bf,rf=detect_fvg_1h(d1); bo,ro=detect_ob_1h(d1); bl,rl=detect_liquidity_1h(d1); bb,rb=detect_breaker_1h(d1)
    if is_buy: return (bo or bb or bl or bf) if is_slow else (bo or bb)
    else: return (ro or rb or rl or rf) if is_slow else (ro or rb)
def fbs_strong_breakout(h,l,c,o):
    if len(c)<3: return None,None
    ph=h[-2]; pl=l[-2]; pc=c[-2]; cc=c[-1]; co=o[-1]; pr=ph-pl or 1; l62=pl+pr*0.62; l38=pl+pr*0.38
    if pc>=l62 and cc>=l38 and cc>co: return "BOS_UP", True
    if pc<=l38 and cc<=l62 and cc<co: return "BOS_DOWN", False
    return None,None
def check_turtle_soup_liquidity(d):
    if len(d["c"])<20: return None,False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2]); h=d["h"][-2]; l=d["l"][-2]; c2=d["c"][-2]; c1=d["c"][-1]
    rng=d["h"][-2]-d["l"][-2] or 1; uw=(d["h"][-2]-max(d["c"][-2],d["o"][-2]))/rng if rng else 0; lw=(min(d["c"][-2],d["o"][-2])-d["l"][-2])/rng if rng else 0
    if c2>recent_high and c1<recent_high: return "BODY SOUP BEAR", True, False
    if c2<recent_low and c1>recent_low: return "BODY SOUP BULL", True, False
    if h>recent_high and c1<recent_high and uw>=0.6: return "WICK GRAB BEAR", False, True
    if l<recent_low and c1>recent_low and lw>=0.6: return "WICK GRAB BULL", False, True
    return None,False,False
def get_overall_market_trend():
    bulls=bears=0
    for s in SYMBOLS:
        d=kl(SYMBOL_MAP[s],"Min240")
        if not d: continue
        b=analyze_4h(d,s)
        if b=="BULL": bulls+=1
        elif b=="BEAR": bears+=1
    if bulls>=6: return f"BULLISH {bulls}/9", "BULLISH"
    if bears>=6: return f"BEARISH {bears}/9", "BEARISH"
    return f"RANGE {bulls}B {bears}S", "RANGE"
def check_market_reversal():
    global LAST_TREND
    overall_str, overall = get_overall_market_trend()
    last = LAST_TREND.get("trend","RANGE")
    if last!=overall and overall!="RANGE":
        if last=="BULLISH" and overall=="BEARISH":
            tg(f"⚠️ MARKET REVERSING BULL->BEAR\n{overall_str}\nClose LONGS, look SHORTS\n{get_time()}")
        elif last=="BEARISH" and overall=="BULLISH":
            tg(f"⚠️ MARKET REVERSING BEAR->BULL\n{overall_str}\nClose SHORTS, look LONGS\n{get_time()}")
        elif last=="RANGE" and overall!="RANGE":
            tg(f"🔥 BREAKOUT RANGE->{overall}\n{overall_str}\n{get_time()}")
        LAST_TREND["trend"]=overall; save_t()
    elif overall!=last:
        LAST_TREND["trend"]=overall; save_t()
    return overall_str
def manage():
    global ACTIVE,JOURNAL
    if not ACTIVE: return
    for s in list(ACTIVE.keys()):
        d5=kl(SYMBOL_MAP[s],"Min15")
        if not d5: continue
        pos=ACTIVE[s]; is_buy=pos["is_buy"]; entry=pos["entry"]; cur=get_live_price(s) or d5["c"][-1]
        pnl=(cur-entry)/entry if is_buy else (entry-cur)/entry
        sl=pos.get("sl", entry*(1-0.022) if is_buy else entry*(1+0.022))
        tp4=AUTO_TP[s]["tp4"]
        if pnl>=tp4:
            JOURNAL["wins"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"WIN","pnl":round(pnl*100,2)})
            save_j(); tg(f"✅ EXIT WIN {s}\n{'LONG' if is_buy else 'SHORT'} +{pnl*100:.1f}%\nENTRY {entry:.5f} -> EXIT {cur:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            JOURNAL["losses"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"LOSS","pnl":round(pnl*100,2)})
            save_j(); tg(f"❌ EXIT LOSS {s}\n{'LONG' if is_buy else 'SHORT'} {pnl*100:.1f}%\nENTRY {entry:.5f} -> EXIT {cur:.5f}\nSL {sl:.5f}\n{get_time()}"); del ACTIVE[s]; save_a(); continue

def scan():
    global COOLDOWN,ACTIVE
    manage()
    overall_str = check_market_reversal()
    print(f"{overall_str} | {get_time()} Holding {list(ACTIVE.keys())}")
    if ACTIVE and len(ACTIVE)>=2: return
    for s in SYMBOLS:
        if s in ACTIVE: continue
        if len(ACTIVE)>=2: break
        is_slow=s in SLOW_COINS
        d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d5: continue
        bias=analyze_4h(d240,s); cur_price=get_live_price(s) or d5["c"][-1]; july=JULY_LEVELS.get(s,cur_price); hour=get_eat_hour()
        if cur_price>july*1.005: day_is_buy=True
        elif cur_price<july*0.995: day_is_buy=False
        else: day_is_buy=True
        if 9<=hour<=15 and day_is_buy: is_dump_window=True
        else: is_dump_window=False
        tbs_type,is_body,is_grab=check_turtle_soup_liquidity(d5)
        if is_grab: continue
        fbs,is_buy=fbs_strong_breakout(d5["h"],d5["l"],d5["c"],d5["o"])
        if tbs_type:
            if "BULL" in tbs_type: is_buy=True
            elif "BEAR" in tbs_type: is_buy=False
        if not fbs and not is_body: continue
        if day_is_buy and not is_buy: continue
        if not day_is_buy and is_buy: continue
        if is_dump_window and not is_body: continue
        if bias=="BULL" and not is_buy: continue
        if bias=="BEAR" and is_buy: continue
        ok=check_1h_confluence(d60,is_buy,is_slow=is_slow)
        if not ok and is_body: ok=True
        if not ok: continue
        cd_key=f"{s}_{'LONG' if is_buy else 'SHORT'}"; cooldown_time=900 if is_body else 2700
        if time.time()-COOLDOWN["signals"].get(cd_key,0)<cooldown_time: continue
        entry=d5["h"][-2]*1.001 if is_buy else d5["l"][-2]*0.999
        cfg=AUTO_TP[s]; sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        # TP from charts
        if s in FAST_COINS:
            tp1 = entry*1.10 if is_buy else entry*0.90
            tp2 = entry*1.25 if is_buy else entry*0.75
        else:
            tp1 = entry*1.05 if is_buy else entry*0.95
            tp2 = entry*1.10 if is_buy else entry*0.90

        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time(),"sl":sl}; save_a()
        COOLDOWN["signals"][cd_key]=time.time(); save_c()

        if is_buy:
            tg(f"🟢 BUY {s}\nENTRY {entry:.5f}\nTP1 {tp1:.5f}\nTP2 {tp2:.5f}\nSL {sl:.5f}\n{get_time()}")
        else:
            tg(f"🔴 SELL {s}\nENTRY {entry:.5f}\nTP1 {tp1:.5f}\nTP2 {tp2:.5f}\nSL {sl:.5f}\n{get_time()}")
        print(f"SIGNAL {'BUY' if is_buy else 'SELL'} {s} E{entry:.5f} SL{sl:.5f}")
        break

if __name__=="__main__":
    import os; fp=open(LOCK_FILE,"w")
    try: fcntl.flock(fp,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except:
        if "--once" not in sys.argv and "--trend" not in sys.argv: print("Bot already running"); exit(1)
    try:
        if os.path.exists(WEEK_FILE): WEEK=json.load(open(WEEK_FILE))
        else: save_w()
        if os.path.exists(JOURNAL_FILE): JOURNAL=json.load(open(JOURNAL_FILE))
        else: save_j()
        if os.path.exists(COOLDOWN_FILE): COOLDOWN=json.load(open(COOLDOWN_FILE))
        if os.path.exists(ACTIVE_FILE): ACTIVE=json.load(open(ACTIVE_FILE))
        if os.path.exists(TREND_FILE): LAST_TREND=json.load(open(TREND_FILE))
        else: save_t()
    except: pass
    print(f"BOT V66.1 SIMPLE WITH TP/SL | {get_time()}")
    if "--trend" in sys.argv:
        o,_=get_overall_market_trend()
        print(f"Overall: {o}"); exit(0)
    if "--once" in sys.argv: scan(); exit(0)
    while True:
        try: scan()
        except Exception as e: print(f"err {e}")
        time.sleep(60)
