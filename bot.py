import json, math, os, sys, time, tempfile, requests, io
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT"]
TELEGRAM_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE, COOLDOWN_FILE = "active.json", "cooldown.json"
DAILY_LOSS_LIMIT, MAX_ACTIVE, SYMBOL_COOLDOWN_SECONDS = -8.0, 5, 7200
session = requests.Session()
COUNTER_MIN_RR = 0.5
TREND_MIN_RR = 0.4
TAG = "BOT-V148.5.2-5COIN-RELAXED"
TP_CONFIG = {"PUMP": {"TP1": 1.0, "TP2": 2.8, "TP3": 6.0, "RUNNER_TARGET": 20.0, "CLOSE": [40,30,15,15]}, "TREND": {"TP1": 1.5, "TP2": 4.0, "TP3": 8.5, "RUNNER_TARGET": 15.0, "CLOSE": [30,30,20,20]},}
PUMP_COINS = ["KOMA_USDT","GRASS_USDT","SAND_USDT"]
def get_tp_config(sym):
    return (TP_CONFIG["PUMP"], "PUMP") if sym in PUMP_COINS else (TP_CONFIG["TREND"], "TREND")
def calc_tps(sym, live, is_buy):
    cfg, typ = get_tp_config(sym)
    if is_buy:
        tp1 = live*(1+cfg["TP1"]/100); tp2=live*(1+cfg["TP2"]/100); tp3=live*(1+cfg["TP3"]/100); runner=live*(1+cfg["RUNNER_TARGET"]/100)
    else:
        tp1 = live*(1-cfg["TP1"]/100); tp2=live*(1-cfg["TP2"]/100); tp3=live*(1-cfg["TP3"]/100); runner=live*(1-cfg["RUNNER_TARGET"]/100)
    return tp1,tp2,tp3,runner,cfg,typ
def get_time(): return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today(): return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
    try:
        with open(p,"r") as f: v=json.load(f)
        return v if isinstance(v,type(d)) else d
    except: return d
ACTIVE=load_json(ACTIVE_FILE,{}); COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("signals",{}); COOLDOWN.setdefault("daily_pnl",0.0); COOLDOWN.setdefault("last_day",get_today())
def atomic_save(path,data):
    d=os.path.dirname(os.path.abspath(path)); fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
    try:
        with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tp,path)
    except:
        try: os.unlink(tp)
        except: pass
        raise
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
def send_chart(sym, d4, sr4h, live, direction, exp_hours):
    try:
        closes = d4["c"][-70:]
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12,6))
        ax.plot(closes, color='white', linewidth=1.2, label='4H close')
        ax.axhspan(sr4h["SUPPORT_LOW"], sr4h["SUPPORT_HIGH"], color='#00ff88', alpha=0.25)
        ax.axhspan(sr4h["RESIST_LOW"], sr4h["RESIST_HIGH"], color='#ff4444', alpha=0.28)
        ax.axhline(sr4h["support_level"], color='#00ff88', ls='--', alpha=0.7)
        ax.axhline(sr4h["resist_level"], color='#ff4444', ls='--', alpha=0.7)
        ax.axhline(live, color='yellow', ls=':', lw=1.5, label=f'LIVE {fmt(live)}')
        ax.set_title(f'{sym.replace("_USDT","")} 4H {sr4h.get("trend_4h","")} | GAP {sr4h.get("gap_pct",0):.1f}% | ~{exp_hours}h', fontsize=9)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(alpha=0.15)
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close(fig)
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            session.post(url, data={"chat_id": TELEGRAM_CHAT, "caption": f"{sym.replace('_USDT','')} {direction} — {TAG}"}, files={"photo": (f"{sym}.png", buf, "image/png")}, timeout=15)
    except Exception as e:
        print(f"chart err {e}")
def kl(symbol,interval):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}
    sec=sec_map.get(interval,300); end=int(time.time()); start=end-sec*400
    url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
    try:
        r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=10).json()
        d=r.get("data",r)
        if isinstance(d,dict) and "data" in d: d=d["data"]
        res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol", d.get("volume", [0]*len(d["close"])))]}
        for k in res: res[k]=res[k][:-1]
        if len(res["c"])<30: return None
        return res
    except: return None
def get_live_price(s):
    for t in [s,s.replace("_","")]:
        try:
            r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json()
            return float((r.get("data",r))["lastPrice"])
        except: pass
    return None
def atr_from_kl(d,period=14):
    h,l,c=d["h"],d["l"],d["c"]; tr=[]
    for i in range(1,len(c)): tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    if len(tr)<period: return tr[-1] if tr else 0.0001
    return sum(tr[-period:])/period
def get_4h_trend_structure(d4):
    lows = d4["l"][-30:]; highs = d4["h"][-30:]
    swing_lows = []; swing_highs = []
    for i in range(2, len(lows)-2):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]: swing_lows.append((i, lows[i]))
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]: swing_highs.append((i, highs[i]))
    if len(swing_lows)>=2 and len(swing_highs)>=2:
        lh1, lh2 = swing_highs[-1][1], swing_highs[-2][1]
        ll1, ll2 = swing_lows[-1][1], swing_lows[-2][1]
        if lh1 > lh2 and ll1 > ll2: return "UP", "HH & HL"
        if lh1 < lh2 and ll1 < ll2: return "DOWN", "LH & LL"
    s10=sum(d4["c"][-10:])/10; s20=sum(d4["c"][-20:])/20
    if s10>s20*1.001: return "UP", "MA10>MA20"
    if s10<s20*0.999: return "DOWN", "MA10<MA20"
    return "RANGE", "RANGE"
def get_4h_sr_boxes(d4, sym=""):
    lookback = 50
    lows = d4["l"][-lookback:]; highs = d4["h"][-lookback:]
    swing_lows = []; swing_highs = []
    for i in range(2, len(lows)-2):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]: swing_lows.append(lows[i])
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]: swing_highs.append(highs[i])
    support = sum(swing_lows[-2:])/2 if len(swing_lows)>=2 else min(lows[-15:])
    resist = sum(swing_highs[-2:])/2 if len(swing_highs)>=2 else max(highs[-15:])
    atr = atr_from_kl(d4, 14)
    box_pct = max(0.008, min(0.03, (atr / support) * 0.6)) if support>0 else 0.015
    gap_pct = (resist - support) / support * 100 if support>0 else 0
    return {"SUPPORT_LOW": support*(1-box_pct), "SUPPORT_HIGH": support*(1+box_pct),"RESIST_LOW": resist*(1-box_pct), "RESIST_HIGH": resist*(1+box_pct),"support_level": support, "resist_level": resist,"sup_touches": len(swing_lows), "res_touches": len(swing_highs),"gap_pct": gap_pct, "used_lookback": lookback,}
def check_bos_choch(d15, direction):
    if not d15 or len(d15["c"])<12: return True, "BOS relaxed"
    highs = d15["h"][-12:-1]; lows = d15["l"][-12:-1]
    last_high = max(highs); last_low = min(lows)
    curr_close = d15["c"][-1]
    if direction=="BUY" and curr_close > last_high:
        return True, f"BOS_UP {curr_close:.4f} > {last_high:.4f}"
    if direction=="SELL" and curr_close < last_low:
        return True, f"BOS_DOWN {curr_close:.4f} < {last_low:.4f}"
    return True, f"BOS info H{last_high:.4f} L{last_low:.4f}"
def check_fvg_ob(d15, direction):
    if len(d15["c"])<5: return True, "FVG relaxed"
    h = d15["h"]; l = d15["l"]
    for i in range(-1, -4, -1):
        try:
            if direction=="BUY" and l[i] > h[i-2]:
                return True, f"FVG_BULL {fmt(h[i-2])}-{fmt(l[i])}"
            if direction=="SELL" and h[i] < l[i-2]:
                return True, f"FVG_BEAR {fmt(l[i-2])}-{fmt(h[i])}"
        except: pass
    return True, "FVG/OB ok"
def daily_ship(d1):
    h=d1["h"][-20:]; l=d1["l"][-20:]; c=d1["c"][-20:]
    if len(h)<20: return "RECT","BOTH",max(h),min(l)
    HH=max(h); LL=min(l); rng=HH-LL or 0.00001; h0,h1=h[0],h[-1]; l0,l1=l[0],l[-1]; flat=rng*0.35
    if abs(h1-h0)<flat and l1>l0+flat: return "ASC_TRI","UP",HH,LL
    if abs(l1-l0)<flat and h1<h0-flat: return "DESC_TRI","DOWN",HH,LL
    if h1<h0-flat and l1>l0+flat: return "SYM_TRI","BOTH",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat and c[-1]>sum(c[-12:-6])/6: return "RECT_ACC","UP",HH,LL
    if abs(h1-h0)<flat and abs(l1-l0)<flat: return "RECT_DIST","DOWN",HH,LL
    if h1>h0+flat and l1>l0+flat: return "RISE_WEDGE","DOWN",HH,LL
    if h1<h0-flat and l1<l0-flat: return "FALL_WEDGE","UP",HH,LL
    return "RECT","BOTH",HH,LL
def get_1h_box(d1h, sym=""):
    h=d1h["h"][-20:]; l=d1h["l"][-20:]; HH=max(h); LL=min(l); rng=HH-LL; mid=(HH+LL)/2
    if rng==0 or mid==0: return None
    max_rng_pct = 0.50 if sym in PUMP_COINS else 0.32
    if rng/mid>max_rng_pct:
        h2=d1h["h"][-10:]; l2=d1h["l"][-10:]; HH2=max(h2); LL2=min(l2); rng2=HH2-LL2; mid2=(HH2+LL2)/2
        if rng2/mid2>max_rng_pct: return None
        return {"HH":HH2,"LL":LL2,"mid":mid2,"rng":rng2}
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}
def check_pullback_15m(d15, box, direction):
    if not d15: return False, 0
    live_c=d15["c"][-1]; rng = box["rng"]
    if rng==0: return False, 0
    zone_low = box["LL"] + rng*0.20
    zone_high = box["LL"] + rng*0.80
    pct = (live_c - box["LL"]) / rng * 100
    in_zone = zone_low <= live_c <= zone_high
    return in_zone, pct
def check_entry_5m(d5, direction):
    if not d5 or len(d5["c"])<3: return False
    o,c=d5["o"][-1],d5["c"][-1]; o2,c2=d5["o"][-2],d5["c"][-2]
    return (c>o and c>=o2) if direction=="BUY" else (c<o and c<=o2)
def next_liquidity(d1,HH,LL,direction):
    h=d1["h"][-20:]; l=d1["l"][-20:]
    liq_up=[x for x in h if x>HH]; liq_down=[x for x in l if x<LL]
    if direction=="BUY":
        lv=sorted(set(liq_up))
        return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*1.02) if len(lv)==1 else (HH*1.03,HH*1.06)
    else:
        lv=sorted(set(liq_down),reverse=True)
        return (lv[0],lv[1]) if len(lv)>=2 else (lv[0],lv[0]*0.98) if len(lv)==1 else (LL*0.97,LL*0.94)
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
        cfg_close=data.get("cfg_close",[40,30,15,15])
        if is_buy and not (sl<entry<tp1<tp2<tp3): ACTIVE.pop(sym,None); save_a(); continue
        if not is_buy and not (tp3<tp2<tp1<entry<sl): ACTIVE.pop(sym,None); save_a(); continue
        if (is_buy and p<=sl) or (not is_buy and p>=sl):
            pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            COOLDOWN["daily_pnl"]+=pnl; save_c()
            tg(f"{'🟢' if pnl>0 else '🔴'} STOP {sym.replace('_USDT','')} {pnl:.2f}% @ {fmt(p)}"); ACTIVE.pop(sym,None); save_a(); continue
        changed=False
        if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):
            data["tp1_hit"]=True; data["sl"]=entry; changed=True
            tg(f"💚 TP1 {sym.replace('_USDT','')} @ {fmt(p)} (-{cfg_close[0]}% closed) -> SL BE")
        if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):
            data["tp1_hit"]=True; data["tp2_hit"]=True; data["sl"]=tp1; changed=True
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚 TP2 {sym.replace('_USDT','')} +{pnl_now:.2f}%")
        if changed: save_a()
        if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
            data["tp3_hit"]=True; data["sl"]=tp2; save_a()
            pnl_now=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            tg(f"💚💚💚 TP3 {sym.replace('_USDT','')} +{pnl_now:.2f}% -> RUNNER to {fmt(runner_target)}")
            continue
        if data.get("tp3_hit") and ((is_buy and p>=runner_target) or (not is_buy and p<=runner_target)):
            profit=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100
            COOLDOWN["daily_pnl"]+=profit; save_c()
            tg(f"🚀 RUNNER {sym.replace('_USDT','')} +{profit:.2f}% CLOSED @ {fmt(p)}")
            ACTIVE.pop(sym,None); save_a()
    print(f"--- SCAN {TAG} {get_time()} daily:{COOLDOWN.get('daily_pnl',0):.2f}% active:{len(ACTIVE)} ---")
    if COOLDOWN.get("daily_pnl",0)<=DAILY_LOSS_LIMIT: return
    if len(ACTIVE)>=MAX_ACTIVE: return
    cands=[]; skipped={}
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: skipped[sym]="active"; continue
            d1=kl(sym,"Day1"); time.sleep(0.15); d4=kl(sym,"Hour4"); time.sleep(0.15); h1=kl(sym,"Min60"); time.sleep(0.15); m15=kl(sym,"Min15"); time.sleep(0.15); m5=kl(sym,"Min5"); time.sleep(0.15)
            if not d1 or not d4 or not h1 or not m15 or not m5: skipped[sym]="kl_fail"; continue
            sr4h=get_4h_sr_boxes(d4,sym)
            if not sr4h: skipped[sym]="no_4h_SR"; continue
            trend_4h, trend_reason = get_4h_trend_structure(d4)
            sr4h["trend_4h"]=trend_4h
            box1h=get_1h_box(h1, sym)
            if not box1h: skipped[sym]="no_1H_box"; continue
            live=get_live_price(sym) or h1["c"][-1]
            atr4=atr_from_kl(d4,14); atr1=atr_from_kl(h1,14)
            in_resist= sr4h["RESIST_LOW"]*0.985 <= live <= sr4h["RESIST_HIGH"]*1.025
            in_support= sr4h["SUPPORT_LOW"]*0.975 <= live <= sr4h["SUPPORT_HIGH"]*1.015
            direction=None; target_box=""; exp_hours=16
            if in_resist:
                direction="SELL"; dist=abs(live-sr4h["support_level"]); exp_candles=max(2,min(12,dist/(atr4 or dist*0.2))); exp_hours=int(exp_candles*4); target_box=f'GREEN {fmt(sr4h["SUPPORT_LOW"])}-{fmt(sr4h["SUPPORT_HIGH"])}'
            elif in_support:
                direction="BUY"; dist=abs(sr4h["resist_level"]-live); exp_candles=max(2,min(12,dist/(atr4 or dist*0.2))); exp_hours=int(exp_candles*4); target_box=f'RED {fmt(sr4h["RESIST_LOW"])}-{fmt(sr4h["RESIST_HIGH"])}'
            else:
                if live < box1h["mid"]: direction="BUY"
                else: direction="SELL"
                target_box=f'1H MID {fmt(box1h["LL"])}-{fmt(box1h["HH"])}'
                dist=abs(box1h["HH"]-box1h["LL"]); exp_candles=max(2,min(12,dist/(atr1 or dist*0.2))); exp_hours=int(exp_candles*1)
            in_20_80, pct_15m = check_pullback_15m(m15,box1h,direction)
            if not in_20_80:
                skipped[sym]=f"no_pullback_20-80_{pct_15m:.1f}%"; continue
            bos_ok, bos_msg = check_bos_choch(m15, direction)
            fvg_ok, fvg_msg = check_fvg_ob(m15, direction)
            if not check_entry_5m(m5,direction): skipped[sym]="no_5m_engulf_relaxed"; continue
            ship,_,_,_=daily_ship(d1); is_buy=direction=="BUY"; HH,LL=box1h["HH"],box1h["LL"]
            liq1,liq2=next_liquidity(d1,HH,LL,direction)
            tp1_raw,tp2_raw,tp3_raw,runner_raw,cfg,typ=calc_tps(sym,live,is_buy)
            if is_buy:
                tp1=max(tp1_raw,liq1 if liq1>live else tp1_raw); tp2=max(tp2_raw,liq2 if liq2>live else tp2_raw); tp3=max(tp3_raw,tp2*1.02); runner=max(runner_raw,tp3*1.12)
                if in_support: sl=min(LL*0.996, live*0.992, sr4h["SUPPORT_LOW"]*0.99)
                else: sl=LL*0.994
                sl=max(sl, live*0.97)
            else:
                tp1=min(tp1_raw,liq1 if liq1<live else tp1_raw); tp2=min(tp2_raw,liq2 if liq2<live else tp2_raw); tp3=min(tp3_raw,tp2*0.98); runner=min(runner_raw,tp3*0.88)
                if in_resist: sl=max(HH*1.004, live*1.008, sr4h["RESIST_HIGH"]*1.01)
                else: sl=HH*1.006
                sl=min(sl, live*1.03)
            if is_buy:
                if not (sl<live<tp1<tp2<tp3): skipped[sym]="bad_levels"; continue
                rr=(tp2-live)/(live-sl) if live!=sl else 0
            else:
                if not (tp3<tp2<tp1<live<sl): skipped[sym]="bad_levels"; continue
                rr=(live-tp2)/(sl-live) if sl!=live else 0
            is_counter=(direction=="BUY" and trend_4h=="DOWN") or (direction=="SELL" and trend_4h=="UP")
            if is_counter and rr<COUNTER_MIN_RR: skipped[sym]=f"counter_rr_low {rr:.2f}"; continue
            if not is_counter and rr<TREND_MIN_RR: skipped[sym]=f"trend_rr_low {rr:.2f}"; continue
            if time.time()-COOLDOWN["signals"].get(sym,0)<SYMBOL_COOLDOWN_SECONDS: skipped[sym]="cooldown"; continue
            tag="🔄 COUNTER BUY" if is_buy and is_counter else "🔄 COUNTER SELL" if not is_buy and is_counter else "💚 BUY" if is_buy else "❤️ SELL"
            stop_pct=(sl/live-1)*100
            msg=(f"{tag} {sym.replace('_USDT','')} @ {fmt(live)} [{typ} {cfg['TP1']}/{cfg['TP2']}/{cfg['TP3']}%] RR:{rr:.2f}\n4H TREND: {trend_4h} ({trend_reason}) | GREEN {fmt(sr4h['SUPPORT_LOW'])}-{fmt(sr4h['SUPPORT_HIGH'])} | RED {fmt(sr4h['RESIST_LOW'])}-{fmt(sr4h['RESIST_HIGH'])} | GAP {sr4h['gap_pct']:.1f}%\n1H BOX: {fmt(LL)}-{fmt(HH)} rng {(box1h['rng']/box1h['mid']*100):.2f}%\n✅ 15M {pct_15m:.1f}% IN 20-80% | {bos_msg} | {fvg_msg} | 5M {direction} ENGULF RELAXED\nPos: {'IN RED → SHORT to GREEN' if in_resist else 'IN GREEN → LONG to RED' if in_support else '1H MID REVERSION'} | Target {target_box} | ⏱️ ~{exp_hours}h\n🛡️ SL {fmt(sl)} ({stop_pct:+.2f}%)\n🎯 TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)} RUNNER {fmt(runner)} [{TAG}]")
            cands.append((rr,sym,msg,live,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,d4,exp_hours,direction))
        except Exception as e:
            skipped[sym]=f"err {e}"; print(f"{sym} err {e}")
    cands.sort(key=lambda x:x[0], reverse=True)
    print(f"FOUND {len(cands)} | SKIPPED: {skipped}")
    if not cands: return
    for it in cands[:3]:
        if len(ACTIVE)>=MAX_ACTIVE: break
        rr,sym,msg,entry,is_buy,sl,tp1,tp2,tp3,runner,cfg,HH,LL,ship,sr4h,d4,exp_hours,direction=it
        ACTIVE[sym]={"entry":entry,"is_buy":is_buy,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"runner":runner,"cfg_close":cfg["CLOSE"],"HH":HH,"LL":LL,"time":time.time(),"face":ship,"tp1_hit":False,"tp2_hit":False,"tp3_hit":False,"type":get_tp_config(sym)[1]}
        COOLDOWN["signals"][sym]=time.time(); save_a(); save_c()
        tg(msg)
        send_chart(sym,d4,sr4h,entry,direction,exp_hours)
        time.sleep(1.5)

if "--once" in sys.argv:
    for i in range(3):
        try: scan()
        except Exception as e: print(f"scan {i} err {e}")
        if i < 2:
            print(f"sleep 240s before next scan in same run...")
            time.sleep(240)
else:
    while True:
        try: scan()
        except Exception as e: print(e)
        time.sleep(300)
