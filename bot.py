# BOT V38 SIMPLE - BUY SELL HOLD REVERSAL ONLY - NO ACTIVE CONFUSION
import time, json, os, requests, sys
from datetime import datetime
from zoneinfo import ZoneInfo

VERBOSE = False
SYMBOL_MAP = {"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys()); PERPS=list(SYMBOL_MAP.values())
FAST_SYMS = ["GRASSUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT","LABUSDT","SIRENUSDT"]

DOM_SENSITIVITY = {"FARTCOINUSDT":2.5,"GRASSUSDT":2.2,"KOMAUSDT":2.0,"SENTUSDT":1.6,"LABUSDT":2.4,"SIRENUSDT":2.0,"SANDUSDT":1.3,"TAOUSDT":1.1,"JASMYUSDT":1.2}
BTC_DOM_CACHE = {"value":58.5,"history":[],"last_fetch":0}
def get_btc_dominance():
    now=time.time()
    if now - BTC_DOM_CACHE["last_fetch"] < 300: return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]
    try:
        r=requests.get("https://api.coingecko.com/api/v3/global",timeout=10).json()
        btc_d=r["data"]["market_cap_percentage"]["btc"]
        BTC_DOM_CACHE["value"]=btc_d; BTC_DOM_CACHE["history"].append((now,btc_d))
        BTC_DOM_CACHE["history"]=[(t,v) for t,v in BTC_DOM_CACHE["history"] if now-t<14400]
        BTC_DOM_CACHE["last_fetch"]=now; return btc_d, BTC_DOM_CACHE["history"]
    except: return BTC_DOM_CACHE["value"], BTC_DOM_CACHE["history"]

def check_btc_filter(sym,is_buy):
    btc_d,hist=get_btc_dominance()
    if len(hist)<2: return True
    change=btc_d-hist[0][1]; eff=change*DOM_SENSITIVITY.get(sym,1.0)
    if change>=0.6 and eff>=0.9 and is_buy: return False
    if change<=-0.6 and eff<=-0.9 and not is_buy: return False
    return True

COOLDOWN_FILE="cooldown.json"; WALL_FILE="wall_alerts.json"
COOLDOWN={"signals":{}}; WALL_ALERTS={}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: COOLDOWN={"signals":{}}
if os.path.exists(WALL_FILE):
    try: WALL_ALERTS=json.load(open(WALL_FILE))
    except: WALL_ALERTS={}
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_wall(): open(WALL_FILE,"w").write(json.dumps(WALL_ALERTS))
LAST_TOP={}
def get_time_12hr():
    try: return datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%I:%M %p EAT")
    except: return datetime.now().strftime("%I:%M %p")
def log(msg):
    if VERBOSE: print(msg, flush=True)
def tg(msg):
    print(msg,flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        except Exception as e: print(f"TG error {e}")

def kl(sym,interval):
    def fetch(url_sym, inter):
        urls = [f"https://contract.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",f"https://futures.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}",f"https://api.mexc.com/api/v1/contract/kline/{url_sym}?interval={inter}"]
        for u in urls:
            try:
                r=requests.get(u, timeout=10).json()
                data=r.get("data",[])
                if not data: continue
                if isinstance(data,dict):
                    def f(x):
                        try: return float(x)
                        except: return 0.0
                    if len(data.get("close",[]))>10:
                        return {"o":[f(x) for x in data.get("open",[])],"h":[f(x) for x in data.get("high",[])],"l":[f(x) for x in data.get("low",[])],"c":[f(x) for x in data.get("close",[])],"v":[f(x) for x in data.get("vol",[])]}
                else:
                    o,h,l,c,v=[],[],[],[],[]
                    for k in data:
                        try: o.append(float(k[1])); h.append(float(k[2])); l.append(float(k[3])); c.append(float(k[4])); v.append(float(k[5]))
                        except: continue
                    if len(c)>10: return {"o":o,"h":h,"l":l,"c":c,"v":v}
            except: continue
        return None
    res = fetch(sym, interval)
    if res: return res
    if interval=="Min240":
        d60 = fetch(sym, "Min60")
        if not d60 or len(d60["c"])<200: return None
        o,h,l,c,v=[],[],[],[],[]
        for i in range(0, len(d60["c"])-3, 4):
            chunk_c = d60["c"][i:i+4]; chunk_o = d60["o"][i:i+4]; chunk_h = d60["h"][i:i+4]; chunk_l = d60["l"][i:i+4]; chunk_v = d60["v"][i:i+4]
            if len(chunk_c)<4: continue
            o.append(chunk_o[0]); h.append(max(chunk_h)); l.append(min(chunk_l)); c.append(chunk_c[-1]); v.append(sum(chunk_v))
        if len(c)>20: return {"o":o,"h":h,"l":l,"c":c,"v":v}
    return None

def get_4h_bias(d240):
    h,l,c=d240["h"],d240["l"],d240["c"]
    if len(c)<50: return None,0,0,""
    crt_low=min(l[-48:]); crt_high=max(h[-48:]); mid=(crt_low+crt_high)/2
    ema50=sum(c[-50:])/50
    if c[-1]>mid and c[-1]>ema50: bias="BULL"; key_level=crt_high
    elif c[-1]<mid and c[-1]<ema50: bias="BEAR"; key_level=crt_low
    else: bias="RANGE"; key_level=mid
    return bias,crt_low,crt_high,key_level

def detect_fvg(h,l,lookback=20):
    fvg_list=[]
    for i in range(len(h)-lookback, len(h)-2):
        if l[i+2] > h[i]: fvg_list.append({"type":"BULL","top":l[i+2],"bot":h[i]})
        if h[i+2] < l[i]: fvg_list.append({"type":"BEAR","top":l[i],"bot":h[i+2]})
    return fvg_list[-3:] if fvg_list else []

def get_1h_structure(d60):
    h,l,c,o=d60["h"],d60["l"],d60["c"],d60["o"]
    if len(c)<50: return "none","none",None,[],"none"
    up=sum(1 for i in range(-20,-1) if c[i]>c[i-1]); down=20-up
    trend="UP" if up>=13 else "DOWN" if down>=13 else "RANGE"
    last_high=max(h[-20:-1]); last_low=min(l[-20:-1])
    breaks="BOS_UP" if c[-1]>last_high else "BOS_DOWN" if c[-1]<last_low else "none"
    atr=sum([h[i]-l[i] for i in range(-14,0)])/14 if len(c)>=14 else 0
    ob=None
    for i in range(len(c)-2,len(c)-30,-1):
        if c[i]<o[i] and c[i+1]>o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: ob=(l[i],h[i],"BULL"); break
        if c[i]>o[i] and c[i+1]<o[i+1] and abs(c[i+1]-o[i+1])>atr*0.3: ob=(l[i],h[i],"BEAR"); break
    fvg=detect_fvg(h,l)
    tops=[]; bots=[]
    for i in range(3,len(h)-3):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i-3] and h[i]>h[i+1] and h[i]>h[i+2] and h[i]>h[i+3]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i-3] and l[i]<l[i+1] and l[i]<l[i+2] and l[i]<l[i+3]: bots.append(l[i])
    reversal="double_top" if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.008 else "double_bottom" if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.008 else "none"
    return trend,breaks,ob,fvg,reversal

def fbs_image_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p78=pl+prange*0.78; p58=pl+prange*0.58; p35=pl+prange*0.35; p22=pl+prange*0.22
    big_range_pct=(ph-pl)/(pl or 1)*100
    body=abs(pc-po); upper_wick=ph-max(pc,po); lower_wick=min(pc,po)-pl
    if pc>po and upper_wick>body*1.2 and cc<p78: return "WEAK_BULL_TRAP",ph,big_range_pct
    if pc<po and lower_wick>body*1.2 and cc>p22: return "WEAK_BEAR_TRAP",pl,big_range_pct
    if pc>=p58 and cc>=p35 and cl>=p22 and cc>co: return "BOS_UP_STRONG",ph,big_range_pct
    if pc<=p35 and cc<=p58 and ch<=p78 and cc<co: return "BOS_DOWN_STRONG",pl,big_range_pct
    return None,0,big_range_pct

def fbs_trend_pump_logic(h,l,c,o):
    if len(c)<3: return None,0,0
    ph,pl,po,pc=h[-2],l[-2],o[-2],c[-2]; ch,cl,co,cc=h[-1],l[-1],o[-1],c[-1]
    prange=ph-pl
    if prange==0: return None,0,0
    p78=pl+prange*0.78; p62=pl+prange*0.62; p38=pl+prange*0.38; p22=pl+prange*0.22
    p68=pl+prange*0.68; p32=pl+prange*0.32
    big_range_pct=(ph-pl)/(pl or 1)*100
    if pc>po:
        if cc < p78 and cc < co: return "WEAK_BULL_TRAP_TREND",ph,big_range_pct
        if pc >= p62 and cc >= p32 and cc > p22 and cc > co: return "BOS_UP_TREND_STRONG_32_68",ph,big_range_pct
    if pc<po:
        if cc > p22 and cc > co: return "WEAK_BEAR_TRAP_TREND",pl,big_range_pct
        if pc <= p38 and cc <= p68 and cc < p78 and cc < co: return "BOS_DOWN_TREND_STRONG_32_68",pl,big_range_pct
    return None,0,big_range_pct

def check_tbs(o,h,l,c,crt_low,crt_high,is_buy, has_ob, has_fvg):
    if len(c)<3: return False
    if has_ob and has_fvg:
        if is_buy and c[-1] > o[-1] and c[-1] > c[-2]: return True
        if not is_buy and c[-1] < o[-1] and c[-1] < c[-2]: return True
    if is_buy: return l[-2] < crt_low*1.002 and c[-1] > crt_low*0.998 and c[-1] > o[-1]
    else: return h[-2] > crt_high*0.998 and c[-1] < crt_high*1.002 and c[-1] < o[-1]

def check_wall_no_timer(s, c, h, crt_high_4h, crt_low_4h):
    live = c[-1]
    if len(c) < 10: return None
    if live < 1: round_wall = round(live*20)/20;
    else: round_wall = round(live*2)/2
    if round_wall <= live: round_wall += 0.05 if live<1 else 0.5
    dist_round = abs(round_wall - live); dist_crt = abs(crt_high_4h - live) if crt_high_4h > live else 999
    wall = round_wall if dist_round < dist_crt else crt_high_4h
    if wall <= live: return None
    dist_to_wall_pct = (wall - live) / live * 100
    if dist_to_wall_pct > 4 or dist_to_wall_pct < 0.15: return None
    dump_target = crt_low_4h + (crt_high_4h - crt_low_4h)*0.35 if crt_high_4h>0 and crt_low_4h>0 else wall*0.97
    now = time.time(); keyPrep = f"{s}_PREP"; keyHit = f"{s}_HIT"
    if 0.3 <= dist_to_wall_pct <= 1.5:
        if now - WALL_ALERTS.get(keyPrep,0) > 1800:
            WALL_ALERTS[keyPrep]=now; save_wall()
            return f"🧱 WALL PREP {s} | Roof {wall:.5f} | Now {live:.5f} ({dist_to_wall_pct:.2f}% below) | 65% holds = dump to {dump_target:.5f} | 35% break = exit | Watch wick close | {get_time_12hr()}"
    if dist_to_wall_pct < 0.35:
        if now - WALL_ALERTS.get(keyHit,0) > 900:
            WALL_ALERTS[keyHit]=now; save_wall()
            return f"🧱 WALL HIT NOW {s} {wall:.5f} | Now {live:.5f} | Close below = HOLD/SHORT, above = EXIT/LONG break | Dump {dump_target:.5f} | {get_time_12hr()}"
    return None

def check_reversal_now(s, c, h, l, o):
    if len(c)<5: return None
    body=abs(c[-1]-o[-1]); up_wick=h[-1]-max(c[-1],o[-1]); low_wick=min(c[-1],o[-1])-l[-1]
    if up_wick > body*1.5 and c[-1] < o[-1]: return f"✅ REVERSAL {s} BEAR WICK | Now {c[-1]:.5f} | Top reject - SELL/HOLD SHORT | {get_time_12hr()}"
    if low_wick > body*1.5 and c[-1] > o[-1]: return f"✅ REVERSAL {s} BULL WICK | Now {c[-1]:.5f} | Bottom reject - BUY/HOLD LONG | {get_time_12hr()}"
    if c[-1] < l[-2] and c[-2] > l[-2]: return f"🟡 HOLD {s} WEAK | Now {c[-1]:.5f} | Lower low - hold profit | {get_time_12hr()}"
    return None

def full_scan(s,p):
    d240=kl(p,"Min240"); d60=kl(p,"Min60"); d15=kl(p,"Min15"); d5=kl(p,"Min5")
    if not d240 or not d60 or not d15 or not d5: return
    c,o,h,l=d5["c"],d5["o"],d5["h"],d5["l"]; v=d5["v"]
    now=time.time(); time_12hr=get_time_12hr(); live_price=c[-1]
    bias_4h_tmp, crt_low_tmp, crt_high_tmp, _ = get_4h_bias(d240)
    if bias_4h_tmp:
        wall_msg = check_wall_no_timer(s, c, h, crt_high_tmp, crt_low_tmp)
        if wall_msg: tg(wall_msg)
        rev_msg = check_reversal_now(s,c,h,l,o)
        if rev_msg and s in ["GRASSUSDT","TAOUSDT","FARTCOINUSDT","SENTUSDT"]:
            tg(rev_msg)
    bias_4h,crt_low_4h,crt_high_4h,key_level=get_4h_bias(d240)
    if not bias_4h: return
    crt_low_1h=min(d60["l"][-24:]); crt_high_1h=max(d60["h"][-24:])
    trend_1h,breaks_1h,ob_1h,fvg_1h,reversal_1h=get_1h_structure(d60)
    has_fvg=len(fvg_1h)>0; has_ob=ob_1h is not None
    fbs15, top15, brp15 = fbs_image_logic(d15["h"],d15["l"],d15["c"],d15["o"])
    if not fbs15 or "STRONG" not in fbs15:
        fbs15_2, top15_2, brp15_2 = fbs_trend_pump_logic(d15["h"],d15["l"],d15["c"],d15["o"])
        if fbs15_2 and "STRONG" in fbs15_2: fbs15, top15, brp15 = fbs15_2, top15_2, brp15_2
    if not fbs15 or "STRONG" not in fbs15: return
    is_buy="UP" in fbs15; side="BUY" if is_buy else "SELL"; key=f"{s}_{side}"
    if bias_4h=="BULL" and not is_buy: return
    if bias_4h=="BEAR" and is_buy: return
    if trend_1h=="UP" and not is_buy: return
    if trend_1h=="DOWN" and is_buy: return
    if not has_ob and not has_fvg and "TREND" not in fbs15: return
    SAME_CD=150*60 if s in FAST_SYMS else 8*3600
    OPP_CD=90*60 if s in FAST_SYMS else 4*3600
    if now-COOLDOWN["signals"].get(key,{}).get("t",0)<SAME_CD: return
    if now-COOLDOWN["signals"].get(f"{s}_{'SELL' if is_buy else 'BUY'}",{}).get("t",0)<OPP_CD: return
    if key in LAST_TOP:
        last_top,last_time=LAST_TOP[key]
        if last_top!=0 and abs(top15-last_top)/(last_top or 1)<0.008 and (now-last_time)< (8*3600 if s in FAST_SYMS else 24*3600): return
    crt_low,crt_high = (crt_low_1h,crt_high_1h) if s in FAST_SYMS else (crt_low_4h,crt_high_4h)
    if not check_tbs(o,h,l,c,crt_low,crt_high,is_buy, has_ob, has_fvg): return
    if not check_btc_filter(s,is_buy): return
    COOLDOWN["signals"][key]={"t":now}; save()
    LAST_TOP[key]=(top15,now)
    fvg_txt=" + FVG" if has_fvg else ""
    tg(f"{'🟢 BUY' if is_buy else '🔴 SELL'} {s} | {fbs15} | CONFIRMED\n4H: {bias_4h} | 1H: {trend_1h} {breaks_1h} OB:{has_ob} {fvg_txt} Rev:{reversal_1h} | 15m Range:{brp15:.2f}% | {time_12hr}\nPrice: {live_price:.6f} | Entry Zone: {top15:.6f}")

print("=== BOT V38 SIMPLE BUY SELL HOLD REVERSAL ===",flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(f"{s} err {e}", flush=True)
    print("=== SCAN DONE V38 ===", flush=True)
else:
    while True:
        for s,p in zip(SYMBOLS,PERPS):
            try: full_scan(s,p)
            except Exception as e: print(f"{s} loop err {e}", flush=True)
        time.sleep(60)
