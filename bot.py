import json, math, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE, STATS_FILE = "active.json", "cooldown.json", "stats_v157.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 35, 3600
TOP_N_PER_SCAN = 2
NEAR_THRESHOLD = 0.05
RETEST_THRESHOLD = 0.03
RR_MIN = 0.7
MIN_SCORE_BASE = 65
try:
    with open("seasonality.json","r") as f:
        _sj=json.load(f)
        _sum=_sj.get("summary",{})
        def _wr(q):
            t=_sum.get(q,"")
            try: return float(t.split("WR")[1].split("%")[0])
            except: return 60.0
        Q_WR = {q:_wr(q) for q in ["Q1","Q2","Q3","Q4"]}
except:
    Q_WR = {"Q1":52,"Q2":63,"Q3":38,"Q4":71}
def get_seasonality():
    m=datetime.now(EAT).month
    q="Q4" if m>=10 else "Q3" if m>=7 else "Q2" if m>=4 else "Q1"
    wr=Q_WR.get(q,60)
    if wr<45: mult, min_score = 0.4, 75
    elif wr<55: mult, min_score = 0.8, 68
    elif wr<65: mult, min_score = 1.2, 62
    else: mult, min_score = 2.0, 55
    return q, wr, mult, min_score
session = requests.Session()
TAG = "V166-SEASONAL-Q4-2X-55"
TP_CONFIG = {"PUMP": {"CLOSE": [40,30,15,15]}, "TREND": {"CLOSE": [30,30,20,20]}}
PUMP_COINS = ["KOMA_USDT","GRASS_USDT","SAND_USDT","FARTCOIN_USDT","PEPE_USDT","BONK_USDT","WIF_USDT"]
def get_tp_config(sym): return (TP_CONFIG["PUMP"], "PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"], "TREND")
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f)
        return v if isinstance(v,type(d)) else d
    except: return d
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)) or "."; fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tp,path)
    except:
        try: os.unlink(tp)
        except: pass
        raise
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{}); STATS=load_json(STATS_FILE, {"closed": [], "open": {}})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def save_s(): atomic_save(STATS_FILE,STATS)
def fmt(p):
    if p is None: return "0"
    if p<0.01: return f"{p:.8f}"
    if p<1: return f"{p:.6f}"
    return f"{p:.4f}"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try:
        token = TELEGRAM_TOKEN.strip(); chat = str(TELEGRAM_CHAT).strip()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = session.post(url, json={"chat_id": chat, "text": m}, timeout=15)
        print(f"TG {r.status_code}"); print(m)
    except Exception as e: print(f"TG EX {e}"); print(m)
def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}
    sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=10).json(); d=r.get("data",r)
        if isinstance(d,dict) and "data" in d: d=d["data"]
        res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol", d.get("volume", [0]*len(d["close"])))]}
        for k in res: res[k]=res[k][:-1]
        if len(res["c"])<30: return None
        return res
    except: return None
def get_live_price(s):
    for t in [s,s.replace("_","")]:
        try:
            r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json(); return float((r.get("data",r))["lastPrice"])
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
    last_h, prev_h = swings_h[-1][1], swings_h[-2][1]
    last_l, prev_l = swings_l[-1][1], swings_l[-2][1]
    hh_type = "HH" if last_h > prev_h else "LH"
    ll_type = "HL" if last_l > prev_l else "LL"
    if hh_type=="HH" and ll_type=="HL": trend="UP"
    elif hh_type=="LH" and ll_type=="LL": trend="DOWN"
    else: trend="RANGE"
    broke_hh=False; broke_ll=False; broke_hh_strength=0; broke_ll_strength=0
    for i in range(len(c)-15, len(c)):
        try:
            rng = h[i]-l[i]
            if rng==0: continue
            close_pct = (c[i]-l[i])/rng*100
            if c[i] > last_h and close_pct >= 62:
                broke_hh=True; broke_hh_strength=max(broke_hh_strength, close_pct)
            if c[i] < last_l and close_pct <= 38:
                broke_ll=True; broke_ll_strength=close_pct if broke_ll_strength==0 else min(broke_ll_strength, close_pct)
        except: pass
    return {"last_high":last_h,"prev_high":prev_h,"last_low":last_l,"prev_low":prev_l,"hh_type":hh_type,"ll_type":ll_type,"trend":trend,"broke_hh":broke_hh,"broke_ll":broke_ll,"broke_hh_strength":broke_hh_strength,"broke_ll_strength":broke_ll_strength,"last_close":c[-1]}
def get_btc_filter():
    try:
        btc = kl("BTC_USDT","Min60")
        if not btc: return {"trend":"RANGE","hh_str":0,"ll_str":0}
        struct = get_last_structure(btc,80)
        if not struct: return {"trend":"RANGE","hh_str":0,"ll_str":0}
        return {"trend":struct["trend"],"hh_str":struct["broke_hh_strength"],"ll_str":struct["broke_ll_strength"]}
    except: return {"trend":"RANGE","hh_str":0,"ll_str":0}
def get_4h_sr_boxes(d4):
    h=d4["h"]; l=d4["l"]; lookback=50
    lows=[l[i] for i in range(len(l)-lookback, len(l)-2) if l[i] < l[i-1] and l[i] < l[i+1]]
    highs=[h[i] for i in range(len(h)-lookback, len(h)-2) if h[i] > h[i-1] and h[i] > h[i+1]]
    if not lows or not highs: return {"support_level": min(l[-20:]), "resist_level": max(h[-20:]), "gap_pct": 15}
    sup=min(lows); res=max(highs); gap=(res-sup)/sup*100 if sup>0 else 0
    return {"support_level":sup,"resist_level":res,"gap_pct":gap}
def get_1h_box(d1h):
    h=d1h["h"][-20:]; l=d1h["l"][-20:]; HH=max(h); LL=min(l); rng=HH-LL; mid=(HH+LL)/2
    if rng==0 or mid==0: return None
    if rng/mid>0.5: return None
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}
def check_pullback_15m(d15, box, direction):
    if not d15: return False,0,"no_data"
    live_c=d15["c"][-1]; rng=box["rng"] or 0.00001
    pct=(live_c-box["LL"])/rng*100
    return 30 <= pct <= 90, pct, f"{pct:.1f}%"
def check_entry_5m(d5, direction):
    if not d5 or len(d5["c"])<3: return False
    o,c=d5["o"][-1],d5["c"][-1]; o2=d5["o"][-2]
    return (c>o and c>=o2) if direction=="BUY" else (c<o and c<=o2)
def valid_signal_data(d):
    try:
        for k in ("entry","sl","tp1","tp2","tp3"):
            if not math.isfinite(float(d[k])): return False
        return True
    except: return False
def get_next_liquidity_auto(d4, live, is_buy, depth=0):
    if not d4 or len(d4["h"])<50:
        pcts=[0.015, 0.028, 0.045, 0.10]
        pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06
        price = live*(1+pct) if is_buy else live*(1-pct)
        return price, 0, True
    h=d4["h"][-100:]; l=d4["l"][-100:]
    swings_h=[]; swings_l=[]
    for i in range(10, len(h)-10):
        if h[i]==max(h[i-4:i+5]): swings_h.append(h[i])
        if l[i]==min(l[i-4:i+5]): swings_l.append(l[i])
    if is_buy:
        candidates = [x for x in set(swings_h) if x > live*1.003]
        close_candidates = []
        for lvl in candidates:
            dist = (lvl - live)/live*100
            cnt = sum(1 for x in swings_h if abs(x-lvl)/lvl < 0.003)
            if cnt >= 2 and 0.5 <= dist <= 4.0:
                close_candidates.append((lvl, cnt))
        close_candidates = sorted(list(set(close_candidates)), key=lambda x: x[0])
        if not close_candidates:
            pcts=[0.015, 0.028, 0.045, 0.10]
            pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06
            return live*(1+pct), 0, True
        if depth < len(close_candidates):
            price, cnt = close_candidates[depth]
            return price, cnt, False
        last_price, last_cnt = close_candidates[-1]
        return last_price * (1 + 0.006*(depth - len(close_candidates) +1)), last_cnt, False
    else:
        candidates = [x for x in set(swings_l) if x < live*0.997]
        close_candidates = []
        for lvl in candidates:
            dist = (live - lvl)/live*100
            cnt = sum(1 for x in swings_l if abs(x-lvl)/lvl < 0.003)
            if cnt >= 2 and 0.5 <= dist <= 4.0:
                close_candidates.append((lvl, cnt))
        close_candidates = sorted(list(set(close_candidates)), key=lambda x: x[0], reverse=True)
        if not close_candidates:
            pcts=[0.015, 0.028, 0.045, 0.10]
            pct = pcts[depth] if depth < len(pcts) else 0.10 + (depth-3)*0.06
            return live*(1-pct), 0, True
        if depth < len(close_candidates):
            price, cnt = close_candidates[depth]
            return price, cnt, False
        last_price, last_cnt = close_candidates[-1]
        return last_price * (1 - 0.006*(depth - len(close_candidates) +1)), last_cnt, False
def get_elite_score(sym, label, pct_label, btc_trend, direction, coin_trend, broke_strength):
    try: pb=float(str(pct_label).replace("%","").strip())
    except: pb=50
    s=50
    if label=="HH" and broke_strength>=62: s+=25
    elif label=="LL" and broke_strength<=38: s+=25
    elif label=="HL" and 30 <= pb <= 90: s+=20
    elif label=="LH" and 30 <= pb <= 90: s+=20
    else: s-=20
    if btc_trend==direction or (btc_trend=="UP" and direction=="BUY") or (btc_trend=="DOWN" and direction=="SELL"): s+=15
    if coin_trend==direction or (coin_trend=="UP" and direction=="BUY") or (coin_trend=="DOWN" and direction=="SELL"): s+=10
    if sym in ["FARTCOIN_USDT","WIF_USDT","PEPE_USDT","BONK_USDT","KOMA_USDT","SEI_USDT"]: s+=5
    return s
def send_stats_report():
    now=time.time()
    closed_7d=[x for x in STATS["closed"] if now-x.get("ts",0)<7*86400]
    wins=len([x for x in closed_7d if x["result"]=="WIN"]); losses=len([x for x in closed_7d if x["result"]=="LOSS"])
    total=wins+losses; wr=(wins/total*100) if total>0 else 0
    by_label={}
    for x in closed_7d:
        lb=x.get("label","?"); by_label.setdefault(lb,{"W":0,"L":0})
        if x["result"]=="WIN": by_label[lb]["W"]+=1
        else: by_label[lb]["L"]+=1
    label_str = " | ".join([f"{k}:{v['W']}W-{v['L']}L" for k,v in by_label.items()]) if by_label else "no data"
    by_sym={}
    for x in closed_7d:
        s=x.get("sym","?"); by_sym.setdefault(s,{"W":0,"L":0})
        if x["result"]=="WIN": by_sym[s]["W"]+=1
        else: by_sym[s]["L"]+=1
    best = sorted(by_sym.items(), key=lambda kv: kv[1]["W"]-kv[1]["L"], reverse=True)[:3]
    best_str = " | ".join([f"{k.replace('_USDT','')} {v['W']}W" for k,v in best]) if best else "no data"
    q, wr_q, mult, min_s = get_seasonality()
    msg=(f"STATS {TAG} {get_time()} [{q} WR:{wr_q:.0f}% x{mult} MIN:{min_s}]\nCLOSED (7d): {total} WIN {wins} LOSS {losses} = {wr:.0f}%\nBY LABEL: {label_str}\nBEST COIN: {best_str}\nOPEN: {len(STATS['open'])} pending")
    tg(msg)
def scan():
    q, wr_q, risk_mult, min_score_threshold = get_seasonality()
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    btc_info = get_btc_filter()
    btc_trend = btc_info["trend"]
    hh = btc_info["hh_str"]; ll = btc_info["ll_str"]
    effective_trend = btc_trend
    if btc_trend == "RANGE":
        if hh >= 62:
            effective_trend = "UP"
            print(f"BTC RANGE but HH {hh:.0f}% >=62% -> SMART UP")
        elif ll != 0 and ll <= 38:
            effective_trend = "DOWN"
            print(f"BTC RANGE but LL {ll:.0f}% <=38% -> SMART DOWN")
        else:
            print(f"BTC 1H TREND: {btc_trend} HH:{hh:.0f}% LL:{ll:.0f}% -> TRUE RANGE SLEEP")
            return
    print(f"BTC 1H TREND: {btc_trend} -> EFFECTIVE: {effective_trend} HH:{hh:.0f}% LL:{ll:.0f}%")
    btc_trend = effective_trend
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
        tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        runner_target=float(data.get("runner", tp3*1.15 if is_buy else tp3*0.85))
        label=data.get("label","?")
        if data.get("tp3_hit"):
            profit_pct = (p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            if profit_pct > 8:
                new_sl = entry*(1+profit_pct*0.5/100) if is_buy else entry*(1-profit_pct*0.5/100)
                if (is_buy and new_sl > sl) or (not is_buy and new_sl < sl):
                    data["sl"]=new_sl; save_a()
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c()
            STATS["closed"].append({"sym":sym,"result":"LOSS","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            emoji="🔴" if not is_buy else "🟢"
            tg(f"{emoji} STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)} [{label}] BTC:{btc_trend}"); ACTIVE.pop(sym,None); save_a(); send_stats_report(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True
            STATS["closed"].append({"sym":sym,"result":"WIN","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            tg(f"🟢 TP1 LIQ {sym.replace('_USDT','')} @ {fmt(p)} -> BE [{label}] BTC:{btc_trend} WIN"); send_stats_report()
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True; tg(f"🟢 TP2 LIQ {sym.replace('_USDT','')} @ {fmt(p)} [{label}] BTC:{btc_trend}")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a(); tg(f"🟢 TP3 SWEEP {sym.replace('_USDT','')} -> RUNNER {fmt(runner_target)} [{label}] BTC:{btc_trend} 30% TRAIL ON"); continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            d4=kl(sym,"Hour4")
            if d4:
                next_liq, cntN, is_pctN = get_next_liquidity_auto(d4, p, is_buy, 4)
                data["runner"]=next_liq; save_a()
                profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
                tagN = f"{cntN}x" if cntN>0 else "%"
                tg(f"🟢 RUNNER EXTEND {sym.replace('_USDT','')} +{profit:.2f}% @ {fmt(p)} -> NEXT {fmt(next_liq)}[{tagN}] [{label}] BTC:{btc_trend}")
                if profit >= 30:
                    COOLDOWN["daily_pnl"]+=profit; save_c()
                    tg(f"🟢 SUPER RUNNER 30%+ {sym.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)} [{label}]")
                    ACTIVE.pop(sym,None); save_a()
                continue
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=profit; save_c(); tg(f"🟢 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% @ {fmt(p)} [{label}] BTC:{btc_trend}"); ACTIVE.pop(sym,None); save_a()
    print(f"--- SCAN {TAG} {get_time()} BTC:{btc_trend} Q:{q} WR:{wr_q:.0f}% x{risk_mult} MIN:{min_score_threshold} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.12); d4=kl(sym,"Hour4"); time.sleep(0.12); h1=kl(sym,"Min60"); time.sleep(0.12); m15=kl(sym,"Min15"); time.sleep(0.12); m5=kl(sym,"Min5"); time.sleep(0.12)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            struct=get_last_structure(h1,80)
            if not struct: skipped[sym]="no_structure"; continue
            live=get_live_price(sym) or h1["c"][-1]
            box1h=get_1h_box(h1)
            if not box1h: skipped[sym]="no_1H_box"; continue
            direction=None; setup_type=None; retest_level=None; label=None; broke_str=0
            if struct["broke_hh"] and struct["broke_hh_strength"]>=62:
                dist = abs(live - struct["last_high"]) / live
                if dist <= RETEST_THRESHOLD:
                    direction="BUY"; setup_type=f"STRONG HH {struct['broke_hh_strength']:.0f}%"; retest_level=struct["last_high"]; label="HH"; broke_str=struct["broke_hh_strength"]
            if not direction and struct["broke_ll"] and (struct["broke_ll_strength"]<=38 or struct["broke_ll_strength"]==0):
                ll_strength = struct["broke_ll_strength"] if struct["broke_ll_strength"]!=0 else 25
                if ll_strength<=38:
                    dist = abs(live - struct["last_low"]) / live
                    if dist <= RETEST_THRESHOLD:
                        direction="SELL"; setup_type=f"STRONG LL {ll_strength:.0f}%"; retest_level=struct["last_low"]; label="LL"; broke_str=ll_strength
            if not direction and struct["ll_type"]=="HL" and struct["trend"]=="UP":
                dist = abs(live - struct["last_low"]) / live
                if dist <= NEAR_THRESHOLD:
                    if struct["hh_type"]=="HH":
                        direction="BUY"; setup_type="PULLBACK @HL [MOTHER HH>=62%]"; retest_level=struct["last_low"]; label="HL"; broke_str=70
            if not direction and struct["hh_type"]=="LH" and struct["trend"]=="DOWN":
                dist = abs(live - struct["last_high"]) / live
                if dist <= NEAR_THRESHOLD:
                    if struct["ll_type"]=="LL":
                        direction="SELL"; setup_type="PULLBACK @LH [MOTHER LL<=38%]"; retest_level=struct["last_high"]; label="LH"; broke_str=30
            if not direction: skipped[sym]=f"no_strong_break {struct['hh_type']}/{struct['ll_type']} HH:{struct['broke_hh_strength']:.0f}% LL:{struct['broke_ll_strength']:.0f}%"; continue
            if direction=="BUY" and btc_trend!="UP": skipped[sym]=f"btc_filter BUY need BTC UP got {btc_trend}"; continue
            if direction=="SELL" and btc_trend!="DOWN": skipped[sym]=f"btc_filter SELL need BTC DOWN got {btc_trend}"; continue
            if direction=="BUY" and btc_info["hh_str"]>0 and btc_info["hh_str"]<62: skipped[sym]=f"btc_weak HH {btc_info['hh_str']:.0f}% <62%"; continue
            if direction=="SELL" and btc_info["ll_str"]>0 and btc_info["ll_str"]>38: skipped[sym]=f"btc_weak LL {btc_info['ll_str']:.0f}% >38%"; continue
            sr4h=get_4h_sr_boxes(d4)
            if sr4h.get("gap_pct",0)<3: skipped[sym]="gap_small"; continue
            in_ok,pct_15m,pct_label=check_pullback_15m(m15,box1h,direction)
            if not in_ok: skipped[sym]=f"pullback_{pct_label}"; continue
            if not check_entry_5m(m5,direction): skipped[sym]="no_5m_engulf"; continue
            is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            sl=min(LL*0.996, live*0.985) if is_buy else max(HH*1.004, live*1.015)
            tp1, cnt1, is_pct1 = get_next_liquidity_auto(d4, live, is_buy, 0)
            tp2, cnt2, is_pct2 = get_next_liquidity_auto(d4, live, is_buy, 1)
            tp3, cnt3, is_pct3 = get_next_liquidity_auto(d4, live, is_buy, 2)
            runner, _, _ = get_next_liquidity_auto(d4, live, is_buy, 3)
            risk=(live-sl)/live*100 if is_buy else (sl-live)/live*100
            reward1=(tp1-live)/live*100 if is_buy else (live-tp1)/live*100
            rr=reward1/risk if risk!=0 else 0
            if rr<RR_MIN: skipped[sym]=f"rr_{rr:.2f}"; continue
            if q=="Q3" and wr_q<45 and label in ["LH","LL"]:
                skipped[sym]=f"seasonal_Q3_weak_skip_{label}"; continue
            score=get_elite_score(sym,label,pct_label,btc_trend,direction,struct["trend"],broke_str)
            if score<min_score_threshold: skipped[sym]=f"score_{score}_<_{min_score_threshold}"; continue
            cands.append((score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,pct_label,broke_str,rr))
        except Exception as e:
            skipped[sym]=f"ex_{e}"; continue
    cands=sorted(cands, key=lambda x: x[0], reverse=True)[:TOP_N_PER_SCAN]
    for score,sym,direction,label,live,sl,tp1,tp2,tp3,runner,pct_label,broke_str,rr in cands:
        is_buy=direction=="BUY"
        tp_cfg, tp_type = get_tp_config(sym)
        ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"is_buy":is_buy,"label":label,"score":score,"pct":pct_label,"rr":rr,"ts":time.time(),"tp_cfg":tp_cfg,"tp_type":tp_type}
        save_a()
        STATS["open"][sym]={"label":label,"entry":live,"ts":time.time()}; save_s()
        tag = f"{broke_str:.0f}%"
        tg(f"🟢 NEW {sym.replace('_USDT','')} {direction} [{label} {tag}] @ {fmt(live)} SL {fmt(sl)} TP {fmt(tp1)}/{fmt(tp2)}/{fmt(tp3)} RUNNER {fmt(runner)} PB {pct_label} SCORE {score} RR {rr:.2f} Q:{q} WR:{wr_q:.0f}% x{risk_mult} BTC:{btc_trend}")
    if not cands:
        print("No candidates, top skips:", list(skipped.items())[:8])

if __name__=="__main__":
    if "--once" in sys.argv:
        scan()
    else:
        while True:
            try: scan()
            except Exception as e:
                print(f"SCAN EX {e}")
                import traceback; traceback.print_exc()
            time.sleep(60)
