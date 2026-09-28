# BOT V67 FULL LOGIC - CRT + TBS + BOS + OB + FVG + LIQUIDITY + 62% BREAKOUT
import time, json, requests, fcntl, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
FAST_COINS={"SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"}
SLOW_COINS={"GRASSUSDT","TAOUSDT","SANDUSDT","JASMYUSDT"}

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
    spot_sym=sym.replace("_",""); spot_iv={"Min15":"15m","Min60":"60m","Min240":"4h","Day1":"1d"}.get(interval,"15m")
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

# === NEW WHOLE LOGIC FROM IMAGES ===

# 1. HTF D - CRT HIGH/LOW + KEY LEVELS
def get_crt_levels(d_daily):
    if len(d_daily["c"])<30: return None,None
    crt_high = max(d_daily["h"][-30:]) # 30D high = $ level from image
    crt_low = min(d_daily["l"][-30:]) # 30D low = liquidity
    return crt_high, crt_low

# 2. 4H - DIRECTION + TREND LINE + SUPPLY/DEMAND (Image 1, 10)
def analyze_4h_full(d, symbol):
    if len(d["c"])<60: return "RANGE", None
    rl=min(d["l"][-20:]); pl=min(d["l"][-50:-20]); ema50=sum(d["c"][-50:])/50; curr=d["c"][-1]
    thr=0.008 if symbol in FAST_COINS else 0.002
    trend="RANGE"
    if rl>pl*(1+thr) and curr>ema50: trend="BULL"
    elif rl<pl*(1-thr) and curr<ema50: trend="BEAR"
    else:
        lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2
        if curr>mid and curr>ema50: trend="BULL"
        elif curr<mid and curr<ema50: trend="BEAR"
    # Supply/Demand zones = last OBs
    demand = min(d["l"][-20:]); supply = max(d["h"][-20:])
    return trend, {"demand":demand,"supply":supply}

# 3. SUPPORT/RESIST + DOUBLE TOP/BOTTOM (Image 1 - #3, #4, #5)
def detect_double_pattern(d):
    if len(d["c"])<30: return None
    last_high = max(d["h"][-20:-5]); prev_high = max(d["h"][-30:-20])
    last_low = min(d["l"][-20:-5]); prev_low = min(d["l"][-30:-20])
    if abs(last_high-prev_high)/prev_high < 0.02: return "DOUBLE_TOP_BEAR"
    if abs(last_low-prev_low)/prev_low < 0.02: return "DOUBLE_BOTTOM_BULL"
    return None

# 4. TRIANGLE + TREND LINE BREAK (Image 1 - #6, #1)
def detect_triangle_break(d):
    if len(d["c"])<30: return None
    # Simplified: contracting highs and lows
    highs = d["h"][-20:]; lows = d["l"][-20:]
    higher_lows = lows[-1] > lows[-10]
    lower_highs = highs[-1] < highs[-10]
    if higher_lows and lower_highs: return "TRIANGLE"
    return None

# 5. 1H - OB + FVG + LIQUIDITY + BREAKER (Image 6 - How to Analyze)
def detect_ob_1h(d):
    bull=bear=False; ob_price=None
    if len(d["c"])<10: return False,False,None
    for i in range(-6,-1):
        body=abs(d["c"][i]-d["o"][i]); rng=d["h"][i]-d["l"][i] or 1
        if d["c"][i]<d["o"][i] and d["c"][-1]>d["h"][i] and body/rng>0.4:
            bull=True; ob_price=d["l"][i]
        if d["c"][i]>d["o"][i] and d["c"][-1]<d["l"][i] and body/rng>0.4:
            bear=True; ob_price=d["h"][i]
    return bull,bear,ob_price

def detect_fvg_1h(d):
    bull=bear=False; fvg_price=None
    if len(d["c"])<10: return False,False,None
    for i in range(-10,-2):
        if d["l"][i]>d["h"][i-2]: bull=True; fvg_price=(d["l"][i]+d["h"][i-2])/2
        if d["h"][i]<d["l"][i-2]: bear=True; fvg_price=(d["h"][i]+d["l"][i-2])/2
    return bull,bear,fvg_price

def detect_liquidity_1h(d):
    bull=bear=False
    if len(d["c"])<20: return False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2])
    if d["h"][-2]>recent_high and d["c"][-1]<recent_high: bear=True # liquidity grab short
    if d["l"][-2]<recent_low and d["c"][-1]>recent_low: bull=True # liquidity grab long
    return bull,bear

# 6. FBS STRONG BREAKOUT 62/38 RULE (Image 2 - Your main filter)
def fbs_strong_breakout_62(d):
    if len(d["c"])<3: return None,None,False
    ph=d["h"][-2]; pl=d["l"][-2]; pr=ph-pl or 1
    l62=pl+pr*0.62; l38=pl+pr*0.38
    cc=d["c"][-1]; co=d["o"][-1]; pc=d["c"][-2]
    # STRONG BULLISH: prev close above 62% + curr above 38% + green
    if pc>=l62 and cc>=l38 and cc>co: return "BOS_UP", True, True
    # STRONG BEARISH: prev close below 38% + curr below 62% + red
    if pc<=l38 and cc<=l62 and cc<co: return "BOS_DOWN", False, True
    # WEAK - DO NOT ENTER (Image 2 left side)
    return None,None,False

# 7. CRT + TBS (Turtle Body Soup) - From your last image
def check_crt_tbs(d_daily, d_15m):
    if not d_daily or not d_15m or len(d_daily["c"])<20 or len(d_15m["c"])<20: return None,False
    crt_high,crt_low=get_crt_levels(d_daily)
    recent_high=max(d_15m["h"][-20:-2]); recent_low=min(d_15m["l"][-20:-2])
    h=d_15m["h"][-2]; l=d_15m["l"][-2]; c2=d_15m["c"][-2]; c1=d_15m["c"][-1]
    # Body Soup - re-enter and close opposite = STRONG reversal
    if c2>crt_high and c1<crt_high: return "TBS_BEARD_BEAR", True
    if c2<crt_low and c1>crt_low: return "TBS_BULL", True
    if c2>recent_high and c1<recent_high: return "BODY SOUP BEAR", True
    if c2<recent_low and c1>recent_low: return "BODY SOUP BULL", True
    return None,False

def get_overall_market_trend():
    bulls=bears=0
    for s in SYMBOLS:
        d=kl(SYMBOL_MAP[s],"Min240")
        if not d: continue
        b,_=analyze_4h_full(d,s)
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
        if last=="BULLISH" and overall=="BEARISH": tg(f"⚠️ MARKET REVERSING BULL->BEAR\n{overall_str}\n{get_time()}")
        elif last=="BEARISH" and overall=="BULLISH": tg(f"⚠️ MARKET REVERSING BEAR->BULL\n{overall_str}\n{get_time()}")
        elif last=="RANGE": tg(f"🔥 BREAKOUT RANGE->{overall}\n{overall_str}\n{get_time()}")
        LAST_TREND["trend"]=overall; save_t()
    elif overall!=last: LAST_TREND["trend"]=overall; save_t()
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
            JOURNAL["wins"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"WIN","pnl":round(pnl*100,2)}); save_j()
            tg(f"✅ WIN {s} +{pnl*100:.1f}%\n{get_time()}"); del ACTIVE[s]; save_a(); continue
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            JOURNAL["losses"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"LOSS","pnl":round(pnl*100,2)}); save_j()
            tg(f"❌ LOSS {s} {pnl*100:.1f}%\n{get_time()}"); del ACTIVE[s]; save_a(); continue

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
        d_daily=kl(SYMBOL_MAP[s],"Day1"); d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d15=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d15: continue

        # === FULL LOGIC STACK FROM IMAGES ===
        bias_4h, sd = analyze_4h_full(d240,s)
        crt_high,crt_low = get_crt_levels(d_daily) if d_daily else (None,None)
        double_pat = detect_double_pattern(d60)
        triangle = detect_triangle_break(d60)

        # 1H confluence
        bo,ro,ob_price = detect_ob_1h(d60)
        bf,rf,fvg_price = detect_fvg_1h(d60)
        bl,rl = detect_liquidity_1h(d60)

        # 15m breakout + TBS
        tbs_type,is_tbs = check_crt_tbs(d_daily,d15)
        fbs,is_buy_fbs,is_strong = fbs_strong_breakout_62(d15)

        # Determine direction from multiple confirmations
        is_buy = None
        if is_tbs:
            if "BULL" in tbs_type: is_buy=True
            elif "BEAR" in tbs_type: is_buy=False
        elif is_strong and fbs:
            is_buy = is_buy_fbs
        elif double_pat:
            if "BULL" in double_pat: is_buy=True
            elif "BEAR" in double_pat: is_buy=False
        else:
            # fallback to 4H + 1H confluence
            if bo or bf or bl: is_buy=True
            if ro or rf or rl: is_buy=False

        if is_buy is None: continue
        if not is_strong and not is_tbs: continue # FBS rule: DO NOT ENTER WEAK

        # Filter with 4H trend - no conflict
        if bias_4h=="BULL" and not is_buy: continue
        if bias_4h=="BEAR" and is_buy: continue

        # Final confluence check - need at least OB or FVG or Liquidity (Image 6)
        if is_buy and not (bo or bf or bl or is_tbs): continue
        if not is_buy and not (ro or rf or rl or is_tbs): continue

        cd_key=f"{s}_{'LONG' if is_buy else 'SHORT'}"; cooldown_time=900 if is_tbs else 1800
        if time.time()-COOLDOWN["signals"].get(cd_key,0)<cooldown_time: continue

        # ENTRY TECHNIQUES - 50% of engulfing (Image 2 right side)
        engulf_high = d15["h"][-2]; engulf_low = d15["l"][-2]
        if is_buy:
            # Limit at 50% of engulfing
            entry = (engulf_high+engulf_low)/2
            sl = ob_price if ob_price and ob_price < entry else engulf_low*0.998
            tp1 = entry* (1.05 if s in SLOW_COINS else 1.10)
            tp2 = entry* (1.10 if s in SLOW_COINS else 1.25)
            tp_crt = crt_high if crt_high else tp2
        else:
            entry = (engulf_high+engulf_low)/2
            sl = ob_price if ob_price and ob_price > entry else engulf_high*1.002
            tp1 = entry* (0.95 if s in SLOW_COINS else 0.90)
            tp2 = entry* (0.90 if s in SLOW_COINS else 0.75)
            tp_crt = crt_low if crt_low else tp2

        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"time":time.time(),"sl":sl}; save_a()
        COOLDOWN["signals"][cd_key]=time.time(); save_c()

        reason = tbs_type or fbs or double_pat or "OB+FVG+LIQ"
        if is_buy:
            tg(f"🟢 BUY {s}\n{reason} | 4H:{bias_4h}\nENTRY {entry:.5f} (50% ENGULF)\nTP1 {tp1:.5f}\nTP2 {tp2:.5f} -> CRT {tp_crt:.5f}\nSL {sl:.5f}\n{get_time()}")
        else:
            tg(f"🔴 SELL {s}\n{reason} | 4H:{bias_4h}\nENTRY {entry:.5f} (50% ENGULF)\nTP1 {tp1:.5f}\nTP2 {tp2:.5f} -> CRT {tp_crt:.5f}\nSL {sl:.5f}\n{get_time()}")
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
    print(f"BOT V67 FULL SMC LOGIC | {get_time()}")
    if "--trend" in sys.argv:
        o,_=get_overall_market_trend(); print(f"Overall: {o}"); exit(0)
    if "--once" in sys.argv: scan(); exit(0)
    while True:
        try: scan()
        except Exception as e: print(f"err {e}")
        time.sleep(60)
