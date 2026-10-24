import json, math, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    GREEN = Fore.GREEN + Style.BRIGHT
    RED = Fore.RED + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    BLUE = Fore.CYAN + Style.BRIGHT
    MAGENTA = Fore.MAGENTA + Style.BRIGHT
    RESET = Style.RESET_ALL
except:
    GREEN=RED=YELLOW=BLUE=MAGENTA=RESET=""

SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE, STATS_FILE = "active.json", "cooldown.json", "stats_v157.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE = -8.0, 35
TOP_N_PER_SCAN = 2
NEAR_THRESHOLD = 0.05
RETEST_THRESHOLD = 0.03
RR_MIN = 0.7
try:
    with open("seasonality.json","r") as f:
        _sj=json.load(f); _sum=_sj.get("summary",{})
        def _wr(q):
            t=_sum.get(q,""); 
            try: return float(t.split("WR")[1].split("%")[0])
            except: return 60.0
        Q_WR = {q:_wr(q) for q in ["Q1","Q2","Q3","Q4"]}
except: Q_WR = {"Q1":52,"Q2":63,"Q3":38,"Q4":71}
def get_seasonality():
    m=datetime.now(EAT).month; q="Q4" if m>=10 else "Q3" if m>=7 else "Q2" if m>=4 else "Q1"; wr=Q_WR.get(q,60)
    if wr<45: mult, min_score = 0.4, 75
    elif wr<55: mult, min_score = 0.8, 68
    elif wr<65: mult, min_score = 1.2, 62
    else: mult, min_score = 2.0, 55
    return q, wr, mult, min_score
session = requests.Session(); TAG = "V169-FBS-RETRY-BOXFIX"
TP_CONFIG = {"PUMP": {"CLOSE": [40,30,15,15]}, "TREND": {"CLOSE": [30,30,20,20]}}
PUMP_COINS = ["KOMA_USDT","GRASS_USDT","SAND_USDT","FARTCOIN_USDT","PEPE_USDT","BONK_USDT","WIF_USDT"]
def get_tp_config(sym): return (TP_CONFIG["PUMP"], "PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"], "TREND")
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f); return v if isinstance(v,type(d)) else d
    except: return d
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)) or "."; fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno()); os.replace(tp,path)
    except:
        try: os.unlink(tp)
        except: pass; raise
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{}); STATS=load_json(STATS_FILE, {"closed": [], "open": {}})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def save_s(): atomic_save(STATS_FILE,STATS)
def fmt(p):
    if p is None: return "0"; 
    if p<0.01: return f"{p:.8f}"; 
    if p<1: return f"{p:.6f}"; return f"{p:.4f}"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try:
        token = TELEGRAM_TOKEN.strip(); chat = str(TELEGRAM_CHAT).strip(); url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = session.post(url, json={"chat_id": chat, "text": m}, timeout=15); print(f"TG {r.status_code}"); print(m)
    except Exception as e: print(f"TG EX {e}"); print(m)
def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}; sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    for attempt in range(3):
        try:
            r=session.get(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"},timeout=15)
            if r.status_code==429:
                print(f"{YELLOW}429 rate limit {symbol} {interval} sleep 5s{RESET}"); time.sleep(5+attempt*3); continue
            j=r.json(); d=j.get("data",j)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            if not d or "open" not in d: time.sleep(1); continue
            res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol", d.get("volume", [0]*len(d["close"])))]}
            for k in res: res[k]=res[k][:-1]
            if len(res["c"])<30: time.sleep(0.5); continue
            return res
        except Exception as e:
            print(f"{YELLOW}kl ex {symbol} {interval} {e} retry {attempt+1}{RESET}"); time.sleep(2+attempt*2)
    return None
def get_live_price(s):
    for t in [s,s.replace("_","")]:
        try: r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json(); return float((r.get("data",r))["lastPrice"])
        except: pass
    return None
def get_last_structure(d, lookback=80):
    if not d or len(d["c"])<lookback: return None
    h=d["h"][-lookback:]; l=d["l"][-lookback:]; c=d["c"][-lookback:]; o=d["o"][-lookback:]
    swings_h=[]; swings_l=[]
    for i in range(5, len(h)-5):
        if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]: swings_h.append((i, h[i]))
        if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]: swings_l.append((i, l[i]))
    if len(swings_h)<2 or len(swings_l)<2: return None
    last_h, prev_h = swings_h[-1][1], swings_h[-2][1]; last_l, prev_l = swings_l[-1][1], swings_l[-2][1]
    hh_type = "HH" if last_h > prev_h else "LH"; ll_type = "HL" if last_l > prev_l else "LL"
    if hh_type=="HH" and ll_type=="HL": trend="UP"
    elif hh_type=="LH" and ll_type=="LL": trend="DOWN"
    else: trend="RANGE"
    broke_hh=False; broke_ll=False; broke_hh_strength=0; broke_ll_strength=0; weak_bull=0; weak_bear=0
    for i in range(len(c)-15, len(c)):
        try:
            rng = h[i]-l[i]; 
            if rng==0: continue; close_pct = (c[i]-l[i])/rng*100
            if c[i] > last_h:
                if close_pct >= 62: broke_hh=True; broke_hh_strength=max(broke_hh_strength, close_pct)
                else: weak_bull = max(weak_bull, close_pct)
            if c[i] < last_l:
                if close_pct <= 38: broke_ll=True; broke_ll_strength=close_pct if broke_ll_strength==0 else min(broke_ll_strength, close_pct)
                else: weak_bear = max(weak_bear, close_pct) if weak_bear!=0 else close_pct
        except: pass
    return {"last_high":last_h,"prev_high":prev_h,"last_low":last_l,"prev_low":prev_l,"hh_type":hh_type,"ll_type":ll_type,"trend":trend,"broke_hh":broke_hh,"broke_ll":broke_ll,"broke_hh_strength":broke_hh_strength,"broke_ll_strength":broke_ll_strength,"weak_bull":weak_bull,"weak_bear":weak_bear,"last_close":c[-1]}
def get_3m_trend(d1):
    if not d1 or len(d1["c"])<90: return {"trend_3m":"RANGE","pct_3m":0}
    try: now_close = d1["c"][-1]; ago_90 = d1["c"][-90]; pct = (now_close - ago_90) / ago_90 * 100 if ago_90>0 else 0; t="UP" if pct>=5 else "DOWN" if pct<=-5 else "RANGE"; return {"trend_3m":t,"pct_3m":pct}
    except: return {"trend_3m":"RANGE","pct_3m":0}
def get_btc_filter():
    try:
        btc_d1 = kl("BTC_USDT","Day1"); btc_h1 = kl("BTC_USDT","Min60"); t3m = get_3m_trend(btc_d1)
        if not btc_d1 or t3m["pct_3m"]==0:
            print(f"{YELLOW}BTC API fail, using Q4 fallback UP 24%{RESET}")
            return {"trend":"UP","hh_str":70,"ll_str":0,"pct_3m":24.0}
        if not btc_h1: return {"trend":t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else "UP","hh_str":0,"ll_str":0,"pct_3m":t3m["pct_3m"]}
        struct = get_last_structure(btc_h1,80)
        if not struct: return {"trend":t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else "UP","hh_str":0,"ll_str":0,"pct_3m":t3m["pct_3m"]}
        trend = t3m["trend_3m"] if t3m["trend_3m"]!="RANGE" else struct["trend"]
        if trend=="RANGE": trend="UP"
        return {"trend":trend,"hh_str":struct["broke_hh_strength"],"ll_str":struct["broke_ll_strength"],"pct_3m":t3m["pct_3m"]}
    except Exception as e:
        print(f"{YELLOW}BTC filter ex {e}, fallback UP{RESET}")
        return {"trend":"UP","hh_str":70,"ll_str":0,"pct_3m":24.0}
def get_4h_sr_boxes(d4):
    h=d4["h"]; l=d4["l"]; lookback=50; lows=[l[i] for i in range(len(l)-lookback, len(l)-2) if l[i] < l[i-1] and l[i] < l[i+1]]; highs=[h[i] for i in range(len(h)-lookback, len(h)-2) if h[i] > h[i-1] and h[i] > h[i+1]]
    if not lows or not highs: return {"support_level": min(l[-20:]), "resist_level": max(h[-20:]), "gap_pct": 15}
    sup=min(lows); res=max(highs); gap=(res-sup)/sup*100 if sup>0 else 0; return {"support_level":sup,"resist_level":res,"gap_pct":gap}
def get_1h_box(d1h):
    h=d1h["h"][-20:]; l=d1h["l"][-20:]; HH=max(h); LL=min(l); rng=HH-LL; mid=(HH+LL)/2; 
    if rng==0 or mid==0: return None; 
    if rng/mid>1.5: return None
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}
def check_pullback_15m(d15, box, direction):
    if not d15: return False,0,"no_data"; live_c=d15["c"][-1]; rng=box["rng"] or 0.00001; pct=(live_c-box["LL"])/rng*100
    if direction=="BUY": ok = 15 <= pct <= 55
    else: ok = 60 <= pct <= 105; return ok, pct, f"{pct:.1f}%"
def check_entry_5m(d5, direction):
    if not d5 or len(d5["c"])<3: return False; o,c=d5["o"][-1],d5["c"][-1]; o2=d5["o"][-2]; return (c>o and c>=o2) if direction=="BUY" else (c<o and c<=o2)
def valid_signal_data(d):
    try: 
        for k in ("entry","sl","tp1","tp2","tp3"):
            if not math.isfinite(float(d[k])): return False
        return True
    except: return False
def get_next_liquidity_auto(d4, live, is_buy, depth=0):
    if not d4 or len(d4["h"])<50:
        pcts=[0.015, 0.028, 0.045, 0.10]; pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06; price = live*(1+pct) if is_buy else live*(1-pct); return price, 0, True
    h=d4["h"][-100:]; l=d4["l"][-100:]; swings_h=[]; swings_l=[]
    for i in range(10, len(h)-10):
        if h[i]==max(h[i-4:i+5]): swings_h.append(h[i])
        if l[i]==min(l[i-4:i+5]): swings_l.append(l[i])
    if is_buy:
        candidates = [x for x in set(swings_h) if x > live*1.003]; close_candidates = []
        for lvl in candidates:
            dist = (lvl - live)/live*100; cnt = sum(1 for x in swings_h if abs(x-lvl)/lvl < 0.003)
            if cnt >= 2 and 0.5 <= dist <= 4.0: close_candidates.append((lvl, cnt))
        close_candidates = sorted(list(set(close_candidates)), key=lambda x: x[0])
        if not close_candidates: pcts=[0.015, 0.028, 0.045, 0.10]; pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06; return live*(1+pct), 0, True
        if depth < len(close_candidates): price, cnt = close_candidates[depth]; return price, cnt, False
        last_price, last_cnt = close_candidates[-1]; return last_price * (1 + 0.006*(depth - len(close_candidates) +1)), last_cnt, False
    else:
        candidates = [x for x in set(swings_l) if x < live*0.997]; close_candidates = []
        for lvl in candidates:
            dist = (live - lvl)/live*100; cnt = sum(1 for x in swings_l if abs(x-lvl)/lvl < 0.003)
            if cnt >= 2 and 0.5 <= dist <= 4.0: close_candidates.append((lvl, cnt))
        close_candidates = sorted(list(set(close_candidates)), key=lambda x: x[0], reverse=True)
        if not close_candidates: pcts=[0.015, 0.028, 0.045, 0.10]; pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06; return live*(1-pct), 0, True
        if depth < len(close_candidates): price, cnt = close_candidates[depth]; return price, cnt, False
        last_price, last_cnt = close_candidates[-1]; return last_price * (1 - 0.006*(depth - len(close_candidates) +1)), last_cnt, False
def get_elite_score(sym, label, pct_label, btc_trend, direction, coin_trend, broke_strength):
    try: pb=float(str(pct_label).replace("%","").strip())
    except: pb=50
    s=50
    if label=="HH" and broke_strength>=62: s+=25
    elif label=="LL" and broke_strength<=38: s+=25
    elif label=="HL" and 15 <= pb <= 55: s+=20
    elif label=="LH" and 60 <= pb <= 105: s+=20
    else: s-=20
    if btc_trend==direction or (btc_trend=="UP" and direction=="BUY") or (btc_trend=="DOWN" and direction=="SELL"): s+=15
    if coin_trend==direction or (coin_trend=="UP" and direction=="BUY") or (coin_trend=="DOWN" and direction=="SELL"): s+=10
    if sym in ["FARTCOIN_USDT","WIF_USDT","PEPE_USDT","BONK_USDT","KOMA_USDT","SEI_USDT"]: s+=5
    return s
def scan():
    q, wr_q, risk_mult, min_score_threshold = get_seasonality(); today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    if len(ACTIVE) >= MAX_ACTIVE: print(f"{RED}MAX ACTIVE {len(ACTIVE)}/{MAX_ACTIVE}{RESET}")
    btc_info = get_btc_filter(); btc_trend = btc_info["trend"]; hh = btc_info["hh_str"]; ll = btc_info["ll_str"]; effective_trend = btc_trend
    if btc_trend == "RANGE" and btc_info.get("pct_3m",0) != 0:
        if hh >= 62: effective_trend = "UP"
        elif ll != 0 and ll <= 38: effective_trend = "DOWN"
        else: print(f"{YELLOW}BTC 3M {btc_info.get('pct_3m',0):.1f}% RANGE -> SLEEP{RESET}"); return
    btc_trend = effective_trend
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym); 
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]); tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"]); runner_target=float(data.get("runner", tp3*1.15 if is_buy else tp3*0.85)); label=data.get("label","?")
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c(); STATS["closed"].append({"sym":sym,"result":"LOSS","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            print(f"{RED}STOP {sym} {pnl:.2f}%{RESET}"); tg(f"STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)} [{label}] BTC:{btc_trend}"); ACTIVE.pop(sym,None); save_a(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True; print(f"{GREEN}TP1 {sym} -> BE{RESET}"); tg(f"🟢 TP1 LIQ {sym.replace('_USDT','')} @ {fmt(p)} -> BE [{label}] BTC:{btc_trend} WIN")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True; print(f"{GREEN}TP2 {sym}{RESET}"); tg(f"🟢 TP2 LIQ {sym.replace('_USDT','')} @ {fmt(p)} [{label}] BTC:{btc_trend}")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a(); print(f"{GREEN}TP3 SWEEP {sym} -> RUNNER{RESET}"); tg(f"🟢 TP3 SWEEP {sym.replace('_USDT','')} -> RUNNER {fmt(runner_target)} [{label}] BTC:{btc_trend} 30% TRAIL ON"); continue
    if len(ACTIVE) >= MAX_ACTIVE: return
    print(f"{BLUE}--- SCAN {TAG} {get_time()} BTC:{btc_trend} 3M:{btc_info.get('pct_3m',0):.1f}% Q:{q} WR:{wr_q:.0f}% ---{RESET}")
    print(f"{YELLOW}--- FBS BREAKOUT CHECK ---{RESET}")
    for sym in SYMBOLS[:12]:
        try:
            h1 = kl(sym,"Min60"); 
            if not h1: continue; st = get_last_structure(h1,80); 
            if not st: continue
            if st.get("weak_bull",0)>0 and not st["broke_hh"]: print(f"{RED}{sym}: WEAK BULL {st['weak_bull']:.0f}% DO NOT ENTER X{RESET}")
            if st.get("weak_bear",0)>0 and not st["broke_ll"]: print(f"{RED}{sym}: WEAK BEAR {st['weak_bear']:.0f}% DO NOT ENTER X{RESET}")
            if st["broke_hh"]: print(f"{GREEN}{sym}: STRONG BULL {st['broke_hh_strength']:.0f}% ENTER OK{RESET}")
            if st["broke_ll"]: print(f"{BLUE}{sym}: STRONG BEAR {st['broke_ll_strength']:.0f}% ENTER OK{RESET}")
            time.sleep(0.8)
        except: pass
    print(f"{YELLOW}--- END FBS CHECK ---{RESET}")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.8); d4=kl(sym,"Hour4"); time.sleep(0.8); h1=kl(sym,"Min60"); time.sleep(0.8); m15=kl(sym,"Min15"); time.sleep(0.8); m5=kl(sym,"Min5"); time.sleep(1.0)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            coin_3m = get_3m_trend(d1); struct=get_last_structure(h1,80); 
            if not struct: skipped[sym]="no_structure"; continue
            live=get_live_price(sym) or h1["c"][-1]; box1h=get_1h_box(h1); 
            if not box1h: skipped[sym]="no_1H_box"; continue
            if struct.get("weak_bull",0) > 0 and not struct["broke_hh"]: skipped[sym]=f"FBS_WEAK_BULL {struct['weak_bull']:.0f}%"; continue
            if struct.get("weak_bear",0) > 0 and not struct["broke_ll"]: skipped[sym]=f"FBS_WEAK_BEAR {struct['weak_bear']:.0f}%"; continue
            direction=None; label=None; broke_str=0
            if struct["broke_hh"] and struct["broke_hh_strength"]>=62:
                dist = abs(live - struct["last_high"]) / live
                if dist <= RETEST_THRESHOLD: direction="BUY"; label="HH"; broke_str=struct["broke_hh_strength"]
            if not direction and struct["broke_ll"] and (struct["broke_ll_strength"]<=38 or struct["broke_ll_strength"]==0):
                ll_strength = struct["broke_ll_strength"] if struct["broke_ll_strength"]!=0 else 25
                if ll_strength<=38:
                    dist = abs(live - struct["last_low"]) / live
                    if dist <= RETEST_THRESHOLD: direction="SELL"; label="LL"; broke_str=ll_strength
            if not direction and struct["ll_type"]=="HL" and (struct["trend"]=="UP" or coin_3m["trend_3m"]=="UP" or btc_trend=="UP"):
                dist = abs(live - struct["last_low"]) / live
                if dist <= NEAR_THRESHOLD: direction="BUY"; label="HL"; broke_str=70
            if not direction and struct["hh_type"]=="LH" and (struct["trend"]=="DOWN" or coin_3m["trend_3m"]=="DOWN" or btc_trend=="DOWN"):
                dist = abs(live - struct["last_high"]) / live
                if dist <= NEAR_THRESHOLD: direction="SELL"; label="LH"; broke_str=30
            if not direction: skipped[sym]=f"no_break {struct['hh_type']}/{struct['ll_type']}"; continue
            if direction=="BUY" and btc_trend!="UP": skipped[sym]=f"btc filter BUY need UP got {btc_trend}"; continue
            if direction=="SELL" and btc_trend!="DOWN": skipped[sym]=f"btc filter SELL need DOWN got {btc_trend}"; continue
            sr4h=get_4h_sr_boxes(d4); 
            if sr4h.get("gap_pct",0)<3: skipped[sym]="gap_small"; continue
            in_ok,pct_15m,pct_label=check_pullback_15m(m15,box1h,direction); 
            if not in_ok: skipped[sym]=f"pullback_{pct_label}"; continue
            if not check_entry_5m(m5,direction): skipped[sym]="no_5m_engulf"; continue
            is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]; sl=min(LL*0.996, live*0.985) if is_buy else max(HH*1.004, live*1.015)
            tp1, _, _ = get_next_liquidity_auto(d4, live, is_buy, 0); tp2, _, _ = get_next_liquidity_auto(d4, live, is_buy, 1); tp3, _, _ = get_next_liquidity_auto(d4, live, is_buy, 2); runner, _, _ = get_next_liquidity_auto(d4, live, is_buy, 3)
            risk=(live-sl)/live*100 if is_buy else (sl-live)/live*100; reward1=(tp1-live)/live*100 if is_buy else (live-tp1)/live*100; rr=reward1/risk if risk!=0 else 0
            if rr<RR_MIN: skipped[sym]=f"rr_{rr:.2f}"; continue
            score=get_elite_score(sym,label,pct_label,btc_trend,direction,struct["trend"],broke_str)
            if score<min_score_threshold: skipped[sym]=f"score_{score}"; continue
            cands.append((score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,pct_label,broke_str,rr,coin_3m))
        except Exception as e: skipped[sym]=f"ex_{e}"; continue
    cands=sorted(cands, key=lambda x: x[0], reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,pct_label,broke_str,rr,coin_3m in cands:
        is_buy=direction=="BUY"; tp_cfg, tp_type = get_tp_config(sym); ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":label,"score":score,"pct":pct_label,"rr":rr,"ts":time.time(),"tp_cfg":tp_cfg,"tp_type":tp_type}; save_a(); STATS["open"][sym]={"label":label,"entry":live,"ts":time.time()}; save_s()
        col = GREEN if is_buy else RED; print(f"{col}NEW {sym} {direction} [{label} {broke_str:.0f}%] SCORE {score}{RESET}")
        tg(f"NEW {sym.replace('_USDT','')} {direction} [{label} {broke_str:.0f}%] @ {fmt(live)} SL {fmt(sl)} TP {fmt(tp1)}/{fmt(tp2)}/{fmt(tp3)} RUNNER {fmt(runner)} PB {pct_label} SCORE {score} RR {rr:.2f} Q:{q} WR:{wr_q:.0f}% BTC:{btc_trend} 3M:{btc_info.get('pct_3m',0):.1f}%")
    if not cands: print(f"{YELLOW}No cands, skips:{RESET}", list(skipped.items())[:8])

if __name__=="__main__":
    if "--once" in sys.argv: scan()
    else:
        while True:
            try: scan()
            except Exception as e: print(f"{RED}SCAN EX {e}{RESET}"); import traceback; traceback.print_exc()
            time.sleep(900)
