import json, math, os, sys, time, tempfile, requests, io
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 5, 3600
session = requests.Session()
TAG = "BOT-V150-SWEEP"
TP_CONFIG = {"PUMP": {"CLOSE": [40,30,15,15]}, "TREND": {"CLOSE": [30,30,20,20]}}
PUMP_COINS = ["KOMA_USDT","GRASS_USDT","SAND_USDT"]
def get_tp_config(sym): return (TP_CONFIG["PUMP"], "PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"], "TREND")
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f)
        return v if isinstance(v,type(d)) else d
    except: return d
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)); fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tp,path)
    except:
        try: os.unlink(tp)
        except: pass
        raise
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def save_a(): atomic_save(ACTIVE_FILE,ACTIVE)
def save_c(): atomic_save(COOLDOWN_FILE,COOLDOWN)
def fmt(p):
    if p is None: return "0"
    if p<0.01: return f"{p:.8f}"
    if p<1: return f"{p:.6f}"
    return f"{p:.4f}"
def tg(m):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: print(m); return
    try: session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT,"text":m},timeout=10)
    except: pass
    print(m)
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
def atr_from_kl(d,period=14):
    h,l,c=d["h"],d["l"],d["c"]; tr=[]
    for i in range(1,len(c)): tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    if len(tr)<period: return tr[-1] if tr else 0.0001
    return sum(tr[-period:])/period

def check_sweep_1h(d1h, box, direction, atr_val):
    """ V150 NEW: 1.5x ATR Sweep Detector """
    if not d1h or not box or atr_val==0: return False, 0.0
    HH,LL=box["HH"],box["LL"]
    # check last 5 x 1H candles
    for i in range(-5,0):
        try:
            h=d1h["h"][i]; l=d1h["l"][i]; c=d1h["c"][i]
            if direction=="SELL":
                wick_above = h - HH
                # must wick above HH and close back below
                if wick_above > atr_val*0.5 and c < HH:
                    strength = wick_above/atr_val
                    if 0.5 <= strength <= 3.0: # 0.5x-3x = sweep, >3x = breakout
                        return True, strength
            else:
                wick_below = LL - l
                if wick_below > atr_val*0.5 and c > LL:
                    strength = wick_below/atr_val
                    if 0.5 <= strength <= 3.0:
                        return True, strength
        except: continue
    return False, 0.0

def is_origin_of_explosive_move(d, idx):
    if idx < 30 or idx > len(d["c"])-4: return False, 0
    origin_low = min(d["l"][idx-2:idx+1]); origin_high = max(d["h"][idx-2:idx+1])
    if (origin_high-origin_low)/d["c"][idx]*100 > 2.0: return False, 0
    move = (d["c"][idx+3]-d["c"][idx])/d["c"][idx]*100
    if abs(move) < 2.5: return False, 0
    return True, move
def check_fresh_and_liquidity(d, zl, zh, ztype):
    touches = 0
    for i in range(len(d["c"])-4, max(0, len(d["c"])-100), -1):
        if d["l"][i] <= zh and d["h"][i] >= zl: touches += 1
    return touches <= 2, True, touches
def get_4h_trend_structure(d4):
    s10=sum(d4["c"][-10:])/10; s20=sum(d4["c"][-20:])/20
    if s10>s20*1.001: return "UP","MA"
    if s10<s20*0.999: return "DOWN","MA"
    return "RANGE","RANGE"
def get_4h_sr_boxes(d4, sym=""):
    lookback=70; lows=d4["l"][-lookback:]; highs=d4["h"][-lookback:]
    swing_lows=[]; swing_highs=[]; perfect_supports=[]; perfect_resists=[]
    for i in range(30, len(d4["c"])-4):
        ok, move = is_origin_of_explosive_move(d4, i)
        if not ok: continue
        zl = min(d4["l"][i-2:i+1]); zh = max(d4["h"][i-2:i+1])
        fresh,_,_ = check_fresh_and_liquidity(d4, zl, zh, "DEMAND" if move>0 else "SUPPLY")
        if fresh:
            if move>0: perfect_supports.append(zl)
            else: perfect_resists.append(zh)
    for i in range(2, len(lows)-2):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]: swing_lows.append(lows[i])
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]: swing_highs.append(highs[i])
    live_est=d4["c"][-1]
    if perfect_supports: support = sum(sorted(perfect_supports)[-2:])/2 if len(perfect_supports)>=2 else perfect_supports[-1]
    else:
        lows_below=[x for x in swing_lows if x < live_est*1.08]
        support=sum(sorted(lows_below)[-2:])/2 if len(lows_below)>=2 else (lows_below[0] if lows_below else min(lows[-20:]))
    if perfect_resists: resist = sum(sorted(perfect_resists)[:2])/2 if len(perfect_resists)>=2 else perfect_resists[-1]
    else:
        highs_above=[x for x in swing_highs if x > live_est*0.92]
        resist=sum(sorted(highs_above)[:2])/2 if len(highs_above)>=2 else (highs_above[0] if highs_above else max(highs[-20:]))
    atr=atr_from_kl(d4,14); box_pct=max(0.01, min(0.025, (atr/support)*0.5)) if support>0 else 0.015
    if support>0 and (resist-support)/support < 0.03:
        mid=(support+resist)/2; support=mid*0.985; resist=mid*1.015
    gap_pct=(resist-support)/support*100 if support>0 else 0
    return {"SUPPORT_LOW":support*(1-box_pct),"SUPPORT_HIGH":support*(1+box_pct),"RESIST_LOW":resist*(1-box_pct),"RESIST_HIGH":resist*(1+box_pct),"support_level":support,"resist_level":resist,"gap_pct":gap_pct,"perfect_score": len(perfect_supports)+len(perfect_resists),"fresh_supply":len(perfect_resists),"fresh_demand":len(perfect_supports)}
def get_dynamic_duration(d1, live, target_price):
    daily_moves = [abs(d1["c"][i]-d1["c"][i-1])/d1["c"][i-1]*100 for i in range(-6, -1) if d1["c"][i-1]!=0]
    if not daily_moves: return 2.0, "2.0 days"
    avg_move = sum(daily_moves)/len(daily_moves) or 1
    distance = abs(target_price-live)/live*100 if live>0 else 0
    days = max(0.3, min(10, distance/avg_move))
    if days < 0.5: dur=f"{int(days*24)}h"
    elif days < 1: dur=f"{days*24:.0f}h"
    elif days < 7: dur=f"{days:.1f} days"
    else: dur=f"{days:.0f} days"
    return days, dur
def get_1h_box(d1h, sym=""):
    h=d1h["h"][-20:]; l=d1h["l"][-20:]; HH=max(h); LL=min(l); rng=HH-LL; mid=(HH+LL)/2
    if rng==0 or mid==0: return None
    if rng/mid>0.50:
        h2=d1h["h"][-10:]; l2=d1h["l"][-10:]; HH2=max(h2); LL2=min(l2); rng2=HH2-LL2; mid2=(HH2+LL2)/2
        if rng2/mid2>0.50: return None
        return {"HH":HH2,"LL":LL2,"mid":mid2,"rng":rng2}
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}
def daily_ship(d1):
    h=d1["h"][-20:]; l=d1["l"][-20:]; return "RECT","BOTH",max(h),min(l)
def check_pullback_15m(d15, box, direction):
    if not d15: return False,0
    live_c=d15["c"][-1]; rng=box["rng"] or 0.00001
    return box["LL"]+rng*0.20 <= live_c <= box["LL"]+rng*0.80, (live_c-box["LL"])/rng*100
def check_entry_5m(d5, direction):
    if not d5 or len(d5["c"])<3: return False
    o,c=d5["o"][-1],d5["c"][-1]; o2=d5["o"][-2]
    return (c>o and c>=o2) if direction=="BUY" else (c<o and c<=o2)
def next_liquidity(d1,HH,LL,direction):
    h=d1["h"][-20:]; l=d1["l"][-20:]; liq_up=[x for x in h if x>HH]; liq_down=[x for x in l if x<LL]
    if direction=="BUY":
        lv=sorted(set(liq_up)); return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*1.02) if len(lv)==1 else (HH*1.03,HH*1.06)
    else:
        lv=sorted(set(liq_down),reverse=True); return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*0.98) if len(lv)==1 else (LL*0.97,LL*0.94)
def valid_signal_data(d):
    try:
        for k in ("entry","sl","tp1","tp2","tp3"):
            if not math.isfinite(float(d[k])): return False
        return True
    except: return False
def scan():
    today=get_today()
    if COOLDOWN.get("last_day")!=today: COOLDOWN["daily_pnl"]=0.0; COOLDOWN["last_day"]=today; save_c()
    for sym,data in list(ACTIVE.items()):
        if not valid_signal_data(data): ACTIVE.pop(sym,None); save_a(); continue
        p=get_live_price(sym)
        if not p: continue
        entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
        tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
        runner_target=float(data.get("runner", tp3*1.15 if is_buy else tp3*0.85))
        if is_buy and not (sl<entry<tp1<tp2<tp3): ACTIVE.pop(sym,None); save_a(); continue
        if not is_buy and not (tp3<tp2<tp1<entry<sl): ACTIVE.pop(sym,None); save_a(); continue
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); ACTIVE.pop(sym,None); save_a(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True; tg(f"💚 TP1 {sym.replace('_USDT','')} @ {fmt(p)} -> SL BE")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True; tg(f"💚💚 TP2 {sym.replace('_USDT','')} @ {fmt(p)}")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a(); tg(f"💚💚💚 TP3 {sym.replace('_USDT','')} -> RUNNER {fmt(runner_target)}"); continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100; COOLDOWN["daily_pnl"]+=profit; save_c(); tg(f"🚀 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)}"); ACTIVE.pop(sym,None); save_a()
    print(f"--- SCAN {TAG} {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT or len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.15); d4=kl(sym,"Hour4"); time.sleep(0.15); h1=kl(sym,"Min60"); time.sleep(0.15); m15=kl(sym,"Min15"); time.sleep(0.15); m5=kl(sym,"Min5"); time.sleep(0.15)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            sr4h=get_4h_sr_boxes(d4,sym)
            if not sr4h or sr4h.get("gap_pct",0) < 2.5: skipped[sym]=f"gap_small {sr4h.get('gap_pct',0) if sr4h else 0:.1f}%"; continue
            trend_4h,_ = get_4h_trend_structure(d4); sr4h["trend_4h"]=trend_4h
            box1h=get_1h_box(h1, sym)
            if not box1h: skipped[sym]="no_1H_box"; continue
            atr1h = atr_from_kl(h1,14)
            live=get_live_price(sym) or h1["c"][-1]
            in_resist= sr4h["RESIST_LOW"]*0.985 <= live <= sr4h["RESIST_HIGH"]*1.025
            in_support= sr4h["SUPPORT_LOW"]*0.975 <= live <= sr4h["SUPPORT_HIGH"]*1.015
            direction="SELL" if in_resist or live>box1h["mid"] else "BUY"
            target_for_duration = sr4h["resist_level"] if direction=="BUY" else sr4h["support_level"]
            exp_days_val, dur_str = get_dynamic_duration(d1, live, target_for_duration)
            in_20_80, pct_15m = check_pullback_15m(m15,box1h,direction)
            if not in_20_80: skipped[sym]=f"no_pullback_{pct_15m:.1f}%"; continue
            if not check_entry_5m(m5,direction): skipped[sym]="no_5m_engulf"; continue
            ship,_,_,_=daily_ship(d1); is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]; liq1,liq2=next_liquidity(d1,HH,LL,direction)
            if is_buy:
                sl_base = min(LL*0.996, live*0.992); risk_pct = max(0.4, min(2.5, abs(live-sl_base)/live*100))
                dist = abs(sr4h["resist_level"]-live)/live*100
                tp1=live*(1+risk_pct*1.5/100); tp2=live*(1+dist*0.6/100); tp3=live*(1+dist*0.9/100); runner=live*(1+dist*1.2/100); sl=max(sl_base, live*0.97)
            else:
                sl_base = max(HH*1.004, live*1.008); risk_pct = max(0.4, min(2.5, abs(sl_base-live)/live*100))
                dist = abs(live-sr4h["support_level"])/live*100
                tp1=live*(1-risk_pct*1.5/100); tp2=live*(1-dist*0.6/100); tp3=live*(1-dist*0.9/100); runner=live*(1-dist*1.2/100); sl=min(sl_base, live*1.03)
            cfg, typ = get_tp_config(sym)
            if is_buy:
                if not (sl<live<tp1<tp2<tp3): skipped[sym]="bad_levels"; continue
                rr=(tp2-live)/(live-sl) if live!=sl else 0
            else:
                if not (tp3<tp2<tp1<live<sl): skipped[sym]="bad_levels"; continue
                rr=(live-tp2)/(sl-live) if sl!=live else 0
            if rr<0.4: skipped[sym]=f"rr_low {rr:.2f}"; continue

            # === QUALITY FILTER v2 + SWEEP v3 ===
            gap = sr4h.get("gap_pct",0)
            perfect = sr4h.get("perfect_score",0)
            swept, sweep_x = check_sweep_1h(h1, box1h, direction, atr1h)
            # 1.5x logic: if no sweep, block unless very big gap
            if not swept and gap < 12:
                skipped[sym]=f"no_sweep_{sweep_x:.1f}x GAP{gap:.1f}% P{perfect}"; continue
            if perfect==0 and gap < 10:
                skipped[sym]=f"low_quality GAP {gap:.1f}% Perfect 0"; continue
            if gap < 5:
                skipped[sym]=f"gap_too_small {gap:.1f}%"; continue
            if direction=="BUY" and trend_4h=="DOWN" and (gap<15 or perfect==0):
                skipped[sym]=f"buy_vs_down GAP {gap:.1f}% P{perfect}"; continue
            if direction=="SELL" and trend_4h=="UP" and (gap<15 or perfect==0):
                skipped[sym]=f"sell_vs_up GAP {gap:.1f}% P{perfect}"; continue
            # === END FILTER ===

            if time.time()-COOLDOWN["signals"].get(sym,0)<SYMBOL_COOLDOWN_SECONDS: skipped[sym]="cooldown"; continue
            sweep_tag = f"SWEEP {sweep_x:.1f}x" if swept else f"NoSweep GAP{gap:.0f}%"
            tag="💚 BUY" if is_buy else "❤️ SELL"
            msg=(f"{tag} {sym.replace('_USDT','')} @ {fmt(live)} RR:{rr:.2f} {sweep_tag}\n📍 {'PUMP' if is_buy else 'DUMP'} {dur_str} → {fmt(target_for_duration)} ({dist:.1f}%) Perfect:{perfect}\n4H {trend_4h} GAP {gap:.1f}% 15M {pct_15m:.1f}%\n🛡️ SL {fmt(sl)} 🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} RUNNER {fmt(runner)} [{TAG}]")
            cands.append((rr,sym,msg,live,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,dur_str,direction))
        except Exception as e: skipped[sym]=f"err {e}"; print(f"{sym} err {e}")
    cands.sort(key=lambda x:x[0], reverse=True); print(f"FOUND {len(cands)} | SKIPPED: {skipped}")
    if not cands: return
    for it in cands[:3]:
        if len(ACTIVE)>=MAX_ACTIVE: break
        rr,sym,msg,entry,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,dur_str,direction=it
        ACTIVE[sym]={"entry":entry,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"cfg_close":cfg["CLOSE"],"HH":HH,"LL":LL,"time":time.time(),"face":ship,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False,"type":get_tp_config(sym)[1]}
        COOLDOWN["signals"][sym]=time.time(); save_a(); save_c(); tg(msg); time.sleep(1)
if "--once" in sys.argv:
    scan()
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        print("Sleep 15 min...")
        time.sleep(900)
