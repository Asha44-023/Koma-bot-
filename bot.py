# BOT V65.1 FINAL 9/9 - July Exact + AutoTP + Hybrid + Time + Trend + OB/FVG/Turtle
import time, json, requests, fcntl, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYMBOL_MAP={"GRASSUSDT":"GRASS_USDT","KOMAUSDT":"KOMA_USDT","FARTCOINUSDT":"FARTCOIN_USDT","SENTUSDT":"SENT_USDT","SANDUSDT":"SAND_USDT","TAOUSDT":"TAO_USDT","JASMYUSDT":"JASMY_USDT","LABUSDT":"LAB_USDT","SIRENUSDT":"SIREN_USDT"}
SYMBOLS=list(SYMBOL_MAP.keys())
FAST_COINS={"SIRENUSDT","LABUSDT","KOMAUSDT","FARTCOINUSDT","SENTUSDT"}
SLOW_COINS={"GRASSUSDT","TAOUSDT","SANDUSDT","JASMYUSDT"}

# === V65.1 FINAL JULY - 9/9 FROM YOUR DOTTED LINES ===
JULY_LEVELS={
    "GRASSUSDT":0.60,
    "TAOUSDT":302.49,
    "JASMYUSDT":0.004947,
    "SANDUSDT":0.04277,
    "FARTCOINUSDT":0.1705,
    "SENTUSDT":0.02105,
    "SIRENUSDT":0.02279,
    "LABUSDT":0.05348,
    "KOMAUSDT":0.018985
}

AUTO_TP={
    "GRASSUSDT":{"tp1":0.05,"tp2":0.10,"sl":0.022,"tp4":0.30},
    "TAOUSDT":{"tp1":0.06,"tp2":0.125,"sl":0.015,"tp4":0.12},
    "JASMYUSDT":{"tp1":0.05,"tp2":0.11,"sl":0.015,"tp4":0.12},
    "SANDUSDT":{"tp1":0.05,"tp2":0.09,"sl":0.012,"tp4":0.10},
    "FARTCOINUSDT":{"tp1":0.12,"tp2":0.28,"sl":0.025,"tp4":0.28},
    "SENTUSDT":{"tp1":0.08,"tp2":0.18,"sl":0.022,"tp4":0.22},
    "SIRENUSDT":{"tp1":0.10,"tp2":0.25,"sl":0.022,"tp4":0.25},
    "LABUSDT":{"tp1":0.15,"tp2":0.35,"sl":0.025,"tp4":0.35},
    "KOMAUSDT":{"tp1":0.12,"tp2":0.30,"sl":0.022,"tp4":0.30}
}

COOLDOWN_FILE="cooldown.json"; ACTIVE_FILE="active.json"; LOCK_FILE="/tmp/bot.lock"; JOURNAL_FILE="winloss.json"; WEEK_FILE="week_tracker.json"
COOLDOWN={"signals":{}}; ACTIVE={}; JOURNAL={"wins":0,"losses":0,"history":[]}
WEEK={"start_date":datetime.now().strftime("%Y-%m-%d"),"end_date":(datetime.now()+timedelta(days=7)).strftime("%Y-%m-%d")}

def save_c(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def save_a(): open(ACTIVE_FILE,"w").write(json.dumps(ACTIVE))
def save_j(): open(JOURNAL_FILE,"w").write(json.dumps(JOURNAL, indent=2))
def save_w(): open(WEEK_FILE,"w").write(json.dumps(WEEK, indent=2))
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

def get_smart_plan(symbol, price):
    july=JULY_LEVELS.get(symbol,price); hour=get_eat_hour(); cfg=AUTO_TP.get(symbol,{"tp1":0.05,"tp2":0.10,"sl":0.022})
    if price>july*1.005: day_bias="BUY_WHOLE_DAY"; is_buy=True
    elif price<july*0.995: day_bias="SELL_WHOLE_DAY"; is_buy=False
    else: day_bias="AT_JULY"; is_buy=True
    if 9<=hour<=15: time_action="WAIT DUMP 9AM-3PM -> ENTER 8PM"; entry=july*1.005
    elif hour>=20 or hour<=2: time_action="ENTER_NOW PUMP WINDOW 8PM-2AM"; entry=price*0.998 if is_buy else price*1.002
    else: time_action="HOLD"; entry=july*1.005
    if is_buy: tp1=entry*(1+cfg["tp1"]); tp2=entry*(1+cfg["tp2"]); sl=july*0.975; exit_t="Tomorrow 10AM EAT"
    else: tp1=entry*(1-cfg["tp1"]); tp2=entry*(1-cfg["tp2"]); sl=july*1.025; exit_t="Tomorrow 2AM EAT"
    return {"july":july,"day_bias":day_bias,"is_buy":is_buy,"entry":entry,"tp1":tp1,"tp2":tp2,"sl":sl,"exit_time":exit_t,"hour":hour,"time_action":time_action,"tp_cfg":cfg}

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
    if len(d["c"])<60: return "RANGE","need 60",0,0,d["c"][-1] if d["c"] else 0
    rl=min(d["l"][-20:]); pl=min(d["l"][-50:-20]); rh=max(d["h"][-20:]); ema50=sum(d["c"][-50:])/50; curr=d["c"][-1]
    is_fast=symbol in FAST_COINS; thr=0.008 if is_fast else 0.002
    higher_low=rl>pl*(1+thr); lower_low=rl<pl*(1-thr)
    lo=min(d["l"][-48:]); hi=max(d["h"][-48:]); mid=(lo+hi)/2
    if higher_low and curr>ema50: return "BULL", f"HL {pl:.4f}->{rl:.4f}", rl, rh, rh*1.08
    if lower_low and curr<ema50: return "BEAR", f"LL {pl:.4f}->{rl:.4f}", rl, rh, rl*0.92
    if not is_fast:
        if curr>mid and curr>ema50: return "BULL", f"Above mid {mid:.4f}", rl, rh, rh*1.08
        if curr<mid and curr<ema50: return "BEAR", f"Below mid {mid:.4f}", rl, rh, rl*0.92
    return "RANGE", f"Range {pl:.4f}->{rl:.4f}", rl, rh, curr

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
            broken=False
            for j in range(i+1,-2):
                if d["c"][j]>ob_high: broken=True; break
            if broken and d["l"][-1]<=ob_high and d["l"][-1]>=ob_low*0.995: bull=True
        if d["c"][i]>d["o"][i]:
            broken=False
            for j in range(i+1,-2):
                if d["c"][j]<ob_low: broken=True; break
            if broken and d["h"][-1]>=ob_low and d["h"][-1]<=ob_high*1.005: bear=True
    return bull,bear
def check_1h_confluence(d1, is_buy, is_slow):
    bull_fvg,bear_fvg=detect_fvg_1h(d1); bull_ob,bear_ob=detect_ob_1h(d1); bull_liq,bear_liq=detect_liquidity_1h(d1); bull_brk,bear_brk=detect_breaker_1h(d1)
    if is_buy: ok=(bull_ob or bull_brk or bull_liq or bull_fvg) if is_slow else (bull_ob or bull_brk); reason=f"OB:{bull_ob} FVG:{bull_fvg} LIQ:{bull_liq} BRK:{bull_brk}"
    else: ok=(bear_ob or bear_brk or bear_liq or bear_fvg) if is_slow else (bear_ob or bear_brk); reason=f"OB:{bear_ob} FVG:{bear_fvg} LIQ:{bear_liq} BRK:{bear_brk}"
    return ok, reason
def fbs_strong_breakout(h,l,c,o):
    if len(c)<3: return None,None
    ph=h[-2]; pl=l[-2]; pc=c[-2]; cc=c[-1]; co=o[-1]; pr=ph-pl or 1; level_62=pl+pr*0.62; level_38=pl+pr*0.38
    if pc>=level_62 and cc>=level_38 and cc>co: return "BOS_UP_STRONG", True
    if pc<=level_38 and cc<=level_62 and cc<co: return "BOS_DOWN_STRONG", False
    return None,None
def check_turtle_soup_liquidity(d):
    if len(d["c"])<20: return None,False,False
    recent_high=max(d["h"][-20:-2]); recent_low=min(d["l"][-20:-2]); h=d["h"][-2]; l=d["l"][-2]; c2=d["c"][-2]; c1=d["c"][-1]
    rng2=d["h"][-2]-d["l"][-2] or 1; upper_wick2=(d["h"][-2]-max(d["c"][-2],d["o"][-2]))/rng2 if rng2 else 0; lower_wick2=(min(d["c"][-2],d["o"][-2])-d["l"][-2])/rng2 if rng2 else 0
    if c2>recent_high and c1<recent_high: return "TURTLE BODY SOUP BEAR", True, False
    if c2<recent_low and c1>recent_low: return "TURTLE BODY SOUP BULL", True, False
    if h>recent_high and c1<recent_high and upper_wick2>=0.6: return "TURTLE WICK GRAB BEAR", False, True
    if l<recent_low and c1>recent_low and lower_wick2>=0.6: return "TURTLE WICK GRAB BULL", False, True
    if h>recent_high and c1<recent_high: return "TURTLE WICK SOUP BEAR", False, False
    if l<recent_low and c1>recent_low: return "TURTLE WICK SOUP BULL", False, False
    return None,False,False
def get_overall_market_trend():
    bulls=bears=0
    for s in SYMBOLS:
        d=kl(SYMBOL_MAP[s],"Min240")
        if not d: continue
        b,_,_,_,_=analyze_4h(d,s)
        if b=="BULL": bulls+=1
        elif b=="BEAR": bears+=1
    if bulls>=6: return f"BULLISH {bulls}/9"
    if bears>=6: return f"BEARISH {bears}/9"
    return f"RANGE {bulls}B {bears}S"
def build_report(is_forced=False):
    total=JOURNAL["wins"]+JOURNAL["losses"]; wr=(JOURNAL["wins"]/total*100) if total else 0; overall=get_overall_market_trend()
    title=f"FORCE REPORT {get_time()}" if is_forced else f"WEEK FINAL {WEEK['start_date']}->{WEEK['end_date']}"
    msg=f"{title}\nOVERALL: {overall}\nW:{JOURNAL['wins']} L:{JOURNAL['losses']} WR:{wr:.1f}%\n------------\n"
    per={}
    for h in JOURNAL["history"]:
        c=h["coin"]
        if c not in per: per[c]={"w":0,"l":0}
        if h["result"]=="WIN": per[c]["w"]+=1
        else: per[c]["l"]+=1
    for coin,st in per.items():
        tot=st["w"]+st["l"]; wrr=(st["w"]/tot*100) if tot else 0; msg+=f"{coin}: W{st['w']} L{st['l']} {wrr:.0f}%\n"
    if ACTIVE:
        msg+="HOLDING:\n"
        for s,pos in ACTIVE.items():
            cur=get_live_price(s) or 0; entry=pos["entry"]; pnl=(cur-entry)/entry if pos["is_buy"] else (entry-cur)/entry
            msg+=f"{s} {'LONG' if pos['is_buy'] else 'SHORT'} {pnl*100:+.2f}% LIVE {cur:.5f}\n"
    msg+="------------\nV65.1 AUTO PLANS:\n"
    for s in SYMBOLS:
        p=get_live_price(s)
        if not p: continue
        plan=get_smart_plan(s,p)
        msg+=f"{s} {plan['day_bias']} E:{plan['entry']:.5f} TP1:+{plan['tp_cfg']['tp1']*100:.0f}% TP2:+{plan['tp_cfg']['tp2']*100:.0f}% SL:{plan['sl']:.5f} {plan['time_action']}\n"
    return msg
def check_telegram_commands():
    try:
        import os; token=os.getenv("TELEGRAM_BOT_TOKEN")
        if not token: return None
        r=requests.get(f"https://api.telegram.org/bot{token}/getUpdates?offset=-20&timeout=2", timeout=5).json()
        if "result" in r:
            for upd in r["result"][-5:]:
                txt=upd.get("message",{}).get("text","").lower().strip(); date=upd.get("message",{}).get("date",0)
                if time.time()-date<180:
                    if txt.startswith("/report"): return "report"
                    if txt.startswith("/resetweek"): return "resetweek"
    except: pass
    return None
def check_week_report():
    try:
        end=datetime.strptime(WEEK["end_date"],"%Y-%m-%d"); now=datetime.now()
        if now.date()>=end.date():
            tg(build_report(False)); WEEK["start_date"]=now.strftime("%Y-%m-%d"); WEEK["end_date"]=(now+timedelta(days=7)).strftime("%Y-%m-%d"); JOURNAL["wins"]=0; JOURNAL["losses"]=0; JOURNAL["history"]=[]; save_w(); save_j()
    except: pass
def manage():
    global ACTIVE,JOURNAL
    if not ACTIVE: return
    for s in list(ACTIVE.keys()):
        d5=kl(SYMBOL_MAP[s],"Min15")
        if not d5: continue
        pos=ACTIVE[s]; is_buy=pos["is_buy"]; entry=pos["entry"]; cur=get_live_price(s) or d5["c"][-1]; pnl=(cur-entry)/entry if is_buy else (entry-cur)/entry
        sl=pos.get("sl", entry*(1-0.022) if is_buy else entry*(1+0.022)); tp4=AUTO_TP[s]["tp4"]
        if pnl>=tp4:
            JOURNAL["wins"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"WIN","pnl":round(pnl*100,2),"dir":"LONG" if is_buy else "SHORT"}); save_j(); tg(f"TP4 WIN {s} {'LONG' if is_buy else 'SHORT'} +{pnl*100:.1f}% | {get_time()}"); del ACTIVE[s]; save_a(); continue
        if (is_buy and cur<=sl) or (not is_buy and cur>=sl):
            JOURNAL["losses"]+=1; JOURNAL["history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"coin":s,"result":"LOSS","pnl":round(pnl*100,2),"dir":"LONG" if is_buy else "SHORT"}); save_j(); print(f"SL {s}"); del ACTIVE[s]; save_a(); continue

def scan():
    global COOLDOWN,ACTIVE
    manage(); check_week_report()
    cmd=check_telegram_commands()
    if cmd=="report": tg(build_report(True))
    elif cmd=="resetweek": WEEK["start_date"]=datetime.now().strftime("%Y-%m-%d"); WEEK["end_date"]=(datetime.now()+timedelta(days=7)).strftime("%Y-%m-%d"); JOURNAL["wins"]=0; JOURNAL["losses"]=0; JOURNAL["history"]=[]; save_w(); save_j(); tg("Week reset")
    if ACTIVE and len(ACTIVE)>=2:
        print(f"Holding {list(ACTIVE.keys())}")
        for s in SYMBOLS:
            pr=get_live_price(s)
            if pr: pl=get_smart_plan(s,pr); print(f"AUTO {s} {pl['day_bias']} E:{pl['entry']:.5f} TP1 {pl['tp1']:.5f} (+{pl['tp_cfg']['tp1']*100:.0f}%) TP2 {pl['tp2']:.5f} (+{pl['tp_cfg']['tp2']*100:.0f}%) SL {pl['sl']:.5f}")
        return
    for s in SYMBOLS:
        if s in ACTIVE: continue
        if len(ACTIVE)>=2: break
        is_slow=s in SLOW_COINS
        d240=kl(SYMBOL_MAP[s],"Min240"); d60=kl(SYMBOL_MAP[s],"Min60"); d5=kl(SYMBOL_MAP[s],"Min15")
        if not d240 or not d60 or not d5: continue
        bias,_,_,_,_=analyze_4h(d240,s); cur_price=get_live_price(s) or d5["c"][-1]; plan=get_smart_plan(s,cur_price)
        print(f"AUTO {s} {cur_price:.5f} July:{plan['july']:.5f} {plan['day_bias']} | E:{plan['entry']:.5f} TP1:{plan['tp1']:.5f} (+{plan['tp_cfg']['tp1']*100:.0f}%) TP2:{plan['tp2']:.5f} (+{plan['tp_cfg']['tp2']*100:.0f}%) SL:{plan['sl']:.5f} | {plan['time_action']} | {get_time()}")
        tbs_type,is_body,is_grab=check_turtle_soup_liquidity(d5)
        if is_grab: print(f"GRAB HOLD {s} {tbs_type}"); continue
        fbs,is_buy=fbs_strong_breakout(d5["h"],d5["l"],d5["c"],d5["o"])
        if tbs_type:
            if "BULL" in tbs_type: is_buy=True
            elif "BEAR" in tbs_type: is_buy=False
        if not fbs and not is_body: continue
        if plan["day_bias"]=="BUY_WHOLE_DAY" and not is_buy: print(f"JULY BLOCK SHORT {s}"); continue
        if plan["day_bias"]=="SELL_WHOLE_DAY" and is_buy: print(f"JULY BLOCK LONG {s}"); continue
        if 9<=plan["hour"]<=15 and plan["day_bias"]=="BUY_WHOLE_DAY" and not is_body: print(f"TIME WAIT 8PM {s}"); continue
        if bias=="BULL" and not is_buy: print(f"TREND BLOCK SHORT {s} BULL"); continue
        if bias=="BEAR" and is_buy: print(f"TREND BLOCK LONG {s} BEAR"); continue
        ok,reason_1h=check_1h_confluence(d60,is_buy,is_slow=is_slow)
        if not ok and is_body: ok=True; reason_1h+=f" +{tbs_type} BODY"
        if not ok: continue
        cd_key=f"{s}_{'LONG' if is_buy else 'SHORT'}"; cooldown_time=900 if is_body else 2700
        if time.time()-COOLDOWN["signals"].get(cd_key,0)<cooldown_time: print(f"COOLDOWN {cd_key}"); continue
        ph=d5["h"][-2]; pl_c=d5["l"][-2]
        if is_slow: entry=plan["entry"]; sl=plan["sl"]
        else: entry=d5["h"][-2]*1.001 if is_buy else d5["l"][-2]*0.999; cfg=AUTO_TP[s]; sl=entry*(1-cfg["sl"]) if is_buy else entry*(1+cfg["sl"])
        tp1=plan["tp1"]; tp2=plan["tp2"]; dir_str="BUY/LONG" if is_buy else "SELL/SHORT"
        print(f"SIGNAL {s} {dir_str} E:{entry:.5f} TP1:{tp1:.5f} TP2:{tp2:.5f} SL:{sl:.5f} EXIT:{plan['exit_time']} | {get_time()}")
        ACTIVE[s]={"entry":entry,"is_buy":is_buy,"bias":bias,"setup":f"V65.1 {plan['day_bias']} {fbs or ''}+{tbs_type or ''} TP +{plan['tp_cfg']['tp1']*100:.0f}/+{plan['tp_cfg']['tp2']*100:.0f}%","time":time.time(),"tp1":tp1,"tp2":tp2,"sl":sl,"exit_time":plan["exit_time"]}; save_a()
        COOLDOWN["signals"][cd_key]=time.time(); save_c()
        tg(f"V65.1 SIGNAL {s} {dir_str}\nBias:{plan['day_bias']}\nENTRY:{entry:.5f}\nTP1:{tp1:.5f} (+{plan['tp_cfg']['tp1']*100:.0f}%)\nTP2:{tp2:.5f} (+{plan['tp_cfg']['tp2']*100:.0f}%)\nSL:{sl:.5f}\nEXIT:{plan['exit_time']}\n{plan['time_action']}")
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
    except: pass
    print(f"BOT V65.1 FINAL 9/9 | {get_time()} | Overall: {get_overall_market_trend()}")
    if "--trend" in sys.argv: print(build_report(True)); exit(0)
    if "--once" in sys.argv: scan(); exit(0)
    while True:
        try: scan()
        except Exception as e: print(f"err {e}")
        time.sleep(60)
