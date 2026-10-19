import json, math, os, sys, time, tempfile, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE, STATS_FILE = "active.json", "cooldown.json", "stats_v153.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 20, 3600
NEAR_THRESHOLD = 0.05
session = requests.Session()
TAG = "V155-BTC-FILTER-ALL"
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
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{})
STATS=load_json(STATS_FILE, {"closed": [], "open": {}})
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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print(f"NO TG CREDS"); print(m); return
    try:
        token = TELEGRAM_TOKEN.strip()
        chat = str(TELEGRAM_CHAT).strip()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = session.post(url, json={"chat_id": chat, "text": m}, timeout=15)
        print(f"TG {r.status_code}: {r.text[:300]}"); print(m)
    except Exception as e:
        print(f"TG EXCEPTION {e}"); print(m)
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
    h=d["h"][-lookback:]; l=d["l"][-lookback:]
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
    return {"last_high":last_h,"prev_high":prev_h,"last_low":last_l,"prev_low":prev_l,"hh_type":hh_type,"ll_type":ll_type,"trend":trend}
def get_btc_filter():
    try:
        btc = kl("BTC_USDT","Min60")
        if not btc: return "RANGE"
        struct = get_last_structure(btc,80)
        return struct["trend"] if struct else "RANGE"
    except: return "RANGE"
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
    return 30 <= pct <= 75, pct, f"{pct:.1f}%"
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
    if not d4 or len(d4["h"])<20: return live*1.02 if is_buy else live*0.98
    h=d4["h"][-100:]; l=d4["l"][-100:]
    highs=[]; lows=[]
    for i in range(5, len(h)-5):
        if h[i]==max(h[i-5:i+6]): highs.append(h[i])
        if l[i]==min(l[i-5:i+6]): lows.append(l[i])
    highs=sorted(list(set(highs))); lows=sorted(list(set(lows)), reverse=True)
    if is_buy:
        cands=[x for x in highs if x>live*1.003]
        if not cands: return live*1.02
        return sorted(cands)[depth] if len(cands)>depth else sorted(cands)[-1]
    else:
        cands=[x for x in lows if x<live*0.997]
        if not cands: return live*0.98
        return sorted(cands, reverse=True)[depth] if len(cands)>depth else sorted(cands, reverse=True)[-1]
def send_stats_report():
    now=time.time()
    closed_7d=[x for x in STATS["closed"] if now-x.get("ts",0)<7*86400]
    wins=len([x for x in closed_7d if x["result"]=="WIN"]); losses=len([x for x in closed_7d if x["result"]=="LOSS"])
    total=wins+losses; wr=(wins/total*100) if total>0 else 0
    by_label={}
    for x in closed_7d:
        lb=x.get("label","?"); by_label.setdefault(lb, {"W":0,"L":0})
        if x["result"]=="WIN": by_label[lb]["W"]+=1
        else: by_label[lb]["L"]+=1
    label_str=" ".join([f"{k}:{v['W']}W{v['L']}L" for k,v in by_label.items()]) or "no data"
    oldest_days=0
    if STATS["open"]:
        oldest=min([v["entry_time"] for v in STATS["open"].values()]); oldest_days=int((now-oldest)/86400)
    msg=(f"📊 STATS {TAG} {get_time()}\nCLOSED (7d): {total} WIN {wins} LOSS {losses} = {wr:.0f}%\nBY LABEL: {label_str}\nOPEN: {len(STATS['open'])} pending (oldest Day {oldest_days})")
    tg(msg)
def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    btc_trend = get_btc_filter()
    print(f"BTC 1H TREND: {btc_trend}")
    expired=[]
    for sym_open, od in list(STATS["open"].items()):
        if time.time()-od["entry_time"]>7*86400:
            expired.append(sym_open); STATS["open"].pop(sym_open, None)
    if expired: save_s(); tg(f"⏳ EXPIRED (7d): {', '.join(expired)}")
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
        tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        runner_target=float(data.get("runner", tp3*1.15 if is_buy else tp3*0.85))
        label=data.get("label","?")
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c()
            STATS["closed"].append({"sym":sym,"result":"LOSS","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)} [{label}]"); ACTIVE.pop(sym,None); save_a(); send_stats_report(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True
            STATS["closed"].append({"sym":sym,"result":"WIN","label":label,"ts":time.time()}); STATS["open"].pop(sym,None); save_s()
            tg(f"💚 TP1 LIQ {sym.replace('_USDT','')} @ {fmt(p)} -> BE [{label}] WIN"); send_stats_report()
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True; tg(f"💚💚 TP2 LIQ {sym.replace('_USDT','')} @ {fmt(p)} [{label}]")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a(); tg(f"💚💚💚 TP3 LIQ {sym.replace('_USDT','')} -> RUNNER {fmt(runner_target)} [{label}]"); continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=profit; save_c(); tg(f"🚀 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% @ {fmt(p)} [{label}]"); ACTIVE.pop(sym,None); save_a()
    print(f"--- SCAN {TAG} {get_time()} BTC:{btc_trend} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} open:{len(STATS['open'])} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: return
    cands=[]; skipped={}; near_ll=[]
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
            dist_hh=abs(live-struct["last_high"])/live; dist_ll=abs(live-struct["last_low"])/live
            at_hh=dist_hh<=0.025; at_ll=dist_ll<=0.025
            if not (at_hh or at_ll):
                if dist_hh<=NEAR_THRESHOLD or dist_ll<=NEAR_THRESHOLD:
                    near_ll.append(f"{sym.replace('_USDT','')} {dist_hh*100:.1f}%/{dist_ll*100:.1f}% to {struct['hh_type']}/{struct['ll_type']}")
                skipped[sym]=f"not_at_last {struct['hh_type']}/{struct['ll_type']}"; continue
            if at_hh: label=struct["hh_type"]; direction="SELL"; setup_type=f"REV @{label}" if label=="HH" else f"CONT @{label}"
            else: label=struct["ll_type"]; direction="BUY"; setup_type=f"CONT @{label}" if label=="HL" else f"REV @{label}"
            if btc_trend=="UP" and direction=="SELL": skipped[sym]=f"btc_up_skip_sell"; continue
            if btc_trend=="DOWN" and direction=="BUY": skipped[sym]=f"btc_down_skip_buy"; continue
            sr4h=get_4h_sr_boxes(d4)
            if sr4h.get("gap_pct",0)<3: skipped[sym]=f"gap_small {sr4h.get('gap_pct',0):.1f}%"; continue
            in_ok,pct_15m,pct_label=check_pullback_15m(m15,box1h,direction)
            if not in_ok: skipped[sym]=f"pullback_{pct_label}_need_30-75%"; continue
            if not check_entry_5m(m5,direction): skipped[sym]="no_5m_engulf"; continue
            is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            sl=min(LL*0.996, live*0.992) if is_buy else max(HH*1.004, live*1.008)
            tp1=get_next_liquidity_auto(d4, live, is_buy, 0)
            tp2=get_next_liquidity_auto(d4, tp1, is_buy, 0)
            tp3=get_next_liquidity_auto(d4, tp2, is_buy, 0)
            runner=get_next_liquidity_auto(d4, tp3, is_buy, 0)
            cfg,typ=get_tp_config(sym)
            rr=(tp1-live)/(live-sl) if is_buy and live!=sl else (live-tp1)/(sl-live) if not is_buy and sl!=live else 0
            if rr<0.2: skipped[sym]=f"rr_low {rr:.2f}"; continue
            if time.time()-COOLDOWN["signals"].get(sym,0)<SYMBOL_COOLDOWN_SECONDS: skipped[sym]="cooldown"; continue
            tag="💚 BUY" if is_buy else "❤️ SELL"
            msg=(f"{tag} {sym.replace('_USDT','')} @ {fmt(live)} [{setup_type}] {struct['trend']} BTC:{btc_trend}\n📍 {label} {struct['trend']} | 1H {fmt(LL)}-{fmt(HH)} 15M {pct_label}\n🛡️ SL {fmt(sl)} 🎯 TP1 LIQ {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} RUNNER {fmt(runner)} [{TAG} {label}]")
            cands.append((rr,sym,msg,live,is_buy,sl,tp1,tp2,tp3,runner,cfg,label))
        except Exception as e: skipped[sym]=f"err {e}"; print(f"{sym} err {e}")
    cands.sort(key=lambda x:x[0], reverse=True)
    print(f"FOUND {len(cands)} | BTC:{btc_trend} | SKIPPED: {skipped}")
    if near_ll: print(f"👀 NEAR (5% pipeline): {', '.join(near_ll)}")
    if not cands: return
    for it in cands:  # SEND ALL
        if len(ACTIVE)>=MAX_ACTIVE: 
            print(f"MAX {MAX_ACTIVE} hit, {len(cands)} found"); break
        rr,sym,msg,entry,is_buy,sl,tp1,tp2,tp3,runner,cfg,label=it
        ACTIVE[sym]={"entry":entry,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"cfg_close":cfg["CLOSE"],"time":time.time(),"tp1_hit":False,"tp2_hit":False,"tp3_hit":False,"type":get_tp_config(sym)[1],"label":label}
        STATS["open"][sym]={"entry_time":time.time(),"label":label,"live":entry,"tp1":tp1}
        COOLDOWN["signals"][sym]=time.time(); save_a(); save_c(); save_s(); tg(msg); time.sleep(0.5)

if "--once" in sys.argv: scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(900)
