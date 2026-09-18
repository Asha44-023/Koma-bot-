import time, json, os, requests, sys
from datetime import datetime
from zoneinfo import ZoneInfo

SYMBOLS = ["KOMAUSDT","GRASSUSDT","HEIUSDT","LABUSDT","SIRENUSDT","VELVETUSDT"]
PERPS = [s.replace("USDT","_USDT") for s in SYMBOLS]
COOLDOWN_FILE="cooldown.json"
COOLDOWN={"signals":{}}
if os.path.exists(COOLDOWN_FILE):
    try: COOLDOWN=json.load(open(COOLDOWN_FILE))
    except: pass
def save(): open(COOLDOWN_FILE,"w").write(json.dumps(COOLDOWN))
def tg(msg):
    print(msg, flush=True)
    tok=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""
    if tok and chat:
        try: requests.get(f"https://api.telegram.org/bot{tok}/sendMessage",params={"chat_id":chat,"text":msg},timeout=10)
        except: pass

ACTIVE = {}

def kl(sym, interval):
    r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}",params={"interval":interval},timeout=10).json()
    if not r.get("success"): return None
    d=r.get("data",{})
    return {"o":[float(x) for x in d.get("open",[])],"h":[float(x) for x in d.get("high",[])],
            "l":[float(x) for x in d.get("low",[])],"c":[float(x) for x in d.get("close",[])],
            "v":[float(x) for x in d.get("vol",[])]}

def get_atr(p):
    d=kl(p,"Min15")
    if not d or len(d["c"])<15: return None
    h,l,c=d["h"][-15:],d["l"][-15:],d["c"][-15:]
    trs=[max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1,len(h))]
    return sum(trs)/len(trs) if trs else None

def get_cvd(p, lookback=20):
    d=kl(p,"Min15")
    if not d or len(d["c"]) < lookback: return 0, 0, []
    c,o,v=d["c"][-lookback:],d["o"][-lookback:],d["v"][-lookback:]
    deltas=[v[i] if c[i]>o[i] else -v[i] for i in range(lookback)]
    cum=[]; s=0
    for dd in deltas:
        s+=dd; cum.append(s)
    recent=sum(deltas[-5:]); prev=sum(deltas[-10:-5])
    slope=recent-prev
    return s, slope, cum

def get_daily_levels(p):
    d=kl(p,"Min60")
    if not d or len(d["c"])<24: return None,None
    return max(d["h"][-24:]), min(d["l"][-24:])

def pattern(h,l):
    tops=[];bots=[]
    for i in range(2,len(h)-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: tops.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: bots.append(l[i])
    tops=tops[-3:];bots=bots[-3:]
    if len(tops)>=3 and max(tops)-min(tops)<sum(tops)/3*0.008: return "triple_top"
    if len(tops)>=2 and abs(tops[-1]-tops[-2])/tops[-2]<0.008: return "double_top"
    if len(bots)>=3 and max(bots)-min(bots)<sum(bots)/3*0.008: return "triple_bottom"
    if len(bots)>=2 and abs(bots[-1]-bots[-2])/bots[-2]<0.008: return "double_bottom"
    return "none"

def full_scan(s,p):
    d15=kl(p,"Min15"); h1=kl(p,"Min60")
    if not d15 or not h1: return
    c,o,h,l,v=d15["c"][-60:],d15["o"][-60:],d15["h"][-60:],d15["l"][-60:],d15["v"][-60:]
    price=c[-1]
    v15=v[-1]/(sum(v[-20:])/20+1e-9)
    hv=h1["v"]; v1h=hv[-1]/(sum(hv[-20:])/20+1e-9) if len(hv)>=20 else 1
    g=[max(c[-i]-c[-i-1],0) for i in range(1,15)]; lo=[max(c[-i-1]-c[-i],0) for i in range(1,15)]
    rsi=100-100/(1+(sum(g)/14)/(sum(lo)/14+1e-9))
    body=abs(c[-1]-o[-1])+1e-9
    bull_sw=(min(o[-1],c[-1])-l[-1])>2*body and c[-1]>o[-1] and v15>1.5
    bear_sw=(h[-1]-max(o[-1],c[-1]))>2*body and c[-1]<o[-1] and v15>1.5
    pat=pattern(h,l)
    trend=(h1["c"][-1]/h1["c"][-4]-1)*100 if len(h1["c"])>=4 else 0
    rng=(max(h[-12:])-min(l[-12:]))/price*100
    jun="none"
    if rng<1.8:
        jun="continual buying" if v1h>1.5 and price>sum(c[-12:])/12 else "continual selling" if v1h>1.5 and price<sum(c[-12:])/12 else "indecision - wait"
    cvd, cvd_slope, cvd_cum = get_cvd(p)
    dh, dl = get_daily_levels(p)

    if v15 < 1.3: return
    sig=None; is_buy=False

    box_h = max(h[-13:-1]); box_l = min(l[-13:-1]); box_mid=(box_h+box_l)/2
    box_rng=(box_h-box_l)/box_mid*100 if box_mid>0 else 99
    if box_rng<1.8 and v15>=1.5:
        if c[-1]>box_h and c[-1]>o[-1] and c[-1]>box_mid: sig="BREAKOUT PUMP BUY"; is_buy=True
        elif c[-1]<box_l and c[-1]<o[-1] and c[-1]<box_mid: sig="BREAKOUT DUMP SELL"; is_buy=False
    if not sig and v15>=2.0:
        if c[-1]>o[-1] and rsi>55: sig="VOL BOSS BUY"; is_buy=True
        elif c[-1]<o[-1] and rsi<45: sig="VOL BOSS SELL"; is_buy=False
    if not sig and bull_sw and rsi>50: sig="SWEEP BUY"; is_buy=True
    if not sig and bear_sw and rsi<50: sig="SWEEP SELL"; is_buy=False
    if not sig and pat in ("double_bottom","triple_bottom") and v15>1.5:
        sig=f"{pat.upper()} BUY" if cvd_slope>0 else f"{pat.upper()}_FADE SELL"; is_buy=cvd_slope>0
    if not sig and pat in ("double_top","triple_top") and v15>1.5:
        sig=f"{pat.upper()} SELL" if cvd_slope<0 else f"{pat.upper()}_FADE BUY"; is_buy=cvd_slope>=0
    if not sig: return

    # FIX 1: V1H
    if v1h < 1.0 and v15 < 3.5:
        print(f"Filtered {s} - V1H {v1h:.1f}x",flush=True); return
    # FIX 2: RSI
    if is_buy and rsi>70: print(f"Filtered BUY {s} RSI {rsi:.0f}",flush=True); return
    if not is_buy and rsi<35: print(f"Filtered SELL {s} RSI {rsi:.0f}",flush=True); return
    # FIX 3: Late
    recent_high=max(h[-20:]); recent_low=min(l[-20:])
    if not is_buy and (recent_high-price)/recent_high>0.03: print(f"Filtered SELL {s} late",flush=True); return
    if is_buy and (price-recent_low)/recent_low>0.03: print(f"Filtered BUY {s} late",flush=True); return
    # EYE FIX: Premium/Discount - exempt breakouts both ways
    high20=max(h[-20:]); low20=min(l[-20:])
    range_pos=(price-low20)/(high20-low20+1e-9)
    is_breakout = "BREAKOUT" in sig
    if not is_breakout:
        if is_buy and range_pos>0.5: print(f"Filtered BUY {s} premium {range_pos:.2f}",flush=True); return
        if not is_buy and range_pos<0.5: print(f"Filtered SELL {s} discount {range_pos:.2f}",flush=True); return
    # DAILY CEILING/FLOOR
    if dh and dl:
        if not is_buy and (price-dl)/price*100<0.8: print(f"Filtered SELL {s} into daily low",flush=True); return
        if is_buy and (dh-price)/price*100<0.8: print(f"Filtered BUY {s} into daily high",flush=True); return
    # FIX 4: Junction
    if jun=="indecision - wait": print(f"Filtered {s} junction",flush=True); return
    # CVD slope
    if is_buy and cvd_slope<0: print(f"Filtered BUY {s} CVD down",flush=True); return
    if not is_buy and cvd_slope>0: print(f"Filtered SELL {s} CVD up",flush=True); return
    # CVD DIVERGENCE
    if len(cvd_cum)>=20:
        price_low = min(c[-10:]) < min(c[-20:-10])
        cvd_higher = cvd_cum[-1] > min(cvd_cum[:-10])
        if not is_buy and price_low and cvd_higher:
            print(f"Filtered SELL {s} bull div",flush=True); return
        price_high = max(c[-10:]) > max(c[-20:-10])
        cvd_lower = cvd_cum[-1] < max(cvd_cum[:-10])
        if is_buy and price_high and cvd_lower:
            print(f"Filtered BUY {s} bear div",flush=True); return
    # Trend
    if not is_buy and trend>1.5: print(f"Filtered SELL {s} trend {trend:.1f}%",flush=True); return
    if is_buy and trend<-1.5: print(f"Filtered BUY {s} trend {trend:.1f}%",flush=True); return

    now=time.time(); prev=COOLDOWN["signals"].get(s,{})
    is_flip=prev.get("dir") is not None and prev.get("dir")!=is_buy
    if v15>=3.0: pass
    elif is_flip:
        if now-prev.get("t",0)<60*60: return
    else:
        if prev.get("dir")==is_buy: return
        if now-prev.get("t",0)<240*60: return

    atr=get_atr(p); risk=(atr*1.5) if atr else price*0.02; risk=min(risk,price*0.035)
    sl=price-risk if is_buy else price+risk
    tp1=price+risk*1.5 if is_buy else price-risk*1.5
    tp2=price+risk*2.0 if is_buy else price-risk*2.0

    COOLDOWN["signals"][s]={"t":now,"dir":is_buy}; save()
    ACTIVE[s]={"entry":price,"is_buy":is_buy,"t":now,"atr":atr,"sig":sig}
    nai=datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
    manage="Plan: Take 70% at TP1 -> move SL to BE | Timeout 15m"
    cvd_tag="🟢 buyers" if cvd_slope>0 else "🔴 sellers"
    dh_str=f"{dh:.6f}" if dh else "na"; dl_str=f"{dl:.6f}" if dl else "na"
    tg(f"{'🟢' if is_buy else '🔴'} {s} {'BUY' if is_buy else 'SELL'} {sig} [PERP]\nEntry:{price:.6f} RSI:{rsi:.0f} V15:{v15:.1f}x V1H:{v1h:.1f}x Trend4H:{trend:+.2f}%\nCVD:{cvd_slope:+.0f} {cvd_tag} RangePos:{range_pos:.2f}\nDay H:{dh_str} L:{dl_str} Junction:{jun}\nSL:{sl:.6f} TP1:{tp1:.6f} TP2:{tp2:.6f}\n{manage} [{nai}]")

def check_reversals():
    now=time.time()
    for s,p in zip(SYMBOLS,PERPS):
        pos=ACTIVE.get(s)
        if not pos: continue
        if now-pos["t"]>30*60: ACTIVE.pop(s,None); continue
        try:
            m1=kl(p,"Min1")
            if not m1 or not m1["c"]: continue
            cur=m1["c"][-1]; atr=pos["atr"]
            if not atr: continue
            if now-pos["t"]>15*60:
                tg(f"⏰ TIMEOUT {s} Entry:{pos['entry']:.6f} Now:{cur:.6f}"); ACTIVE.pop(s,None); continue
            against=(cur-pos["entry"]) if not pos["is_buy"] else (pos["entry"]-cur)
            if against>1.5*atr:
                tg(f"⚠️ V-REVERSAL {s} Entry:{pos['entry']:.6f} Now:{cur:.6f}"); ACTIVE.pop(s,None)
        except Exception as e: print(f"rev err {s}:{e}",flush=True)

def volume_radar():
    for s,p in zip(SYMBOLS,PERPS):
        try:
            m1=kl(p,"Min1")
            if not m1 or len(m1["v"])<21: continue
            v=m1["v"]; spike=v[-1]/(sum(v[-21:-1])/20+1e-9)
            if spike>=3.0:
                print(f"⚡ 1m SPIKE {s} {spike:.1f}x",flush=True); full_scan(s,p)
        except: pass

print("=== BOT V19.1 EYES ===",flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try: full_scan(s,p)
        except Exception as e: print(e,flush=True)
else:
    last15=0
    while True:
        volume_radar(); check_reversals()
        if time.time()-last15>900:
            for s,p in zip(SYMBOLS,PERPS):
                try: full_scan(s,p)
                except: pass
            last15=time.time()
        time.sleep(60)
