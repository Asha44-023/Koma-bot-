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

def kl(sym, interval):
    r=requests.get(f"https://contract.mexc.com/api/v1/contract/kline/{sym}",params={"interval":interval},timeout=10).json()
    if not r.get("success"): return None
    d=r.get("data",{})
    return {"o":[float(x) for x in d.get("open",[])],"h":[float(x) for x in d.get("high",[])],
            "l":[float(x) for x in d.get("low",[])],"c":[float(x) for x in d.get("close",[])],
            "v":[float(x) for x in d.get("vol",[])]}

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
    dd=kl(p,"Day1")
    ph,pl=(dd["h"][-2],dd["l"][-2]) if dd and len(dd["h"])>=2 else (max(h[-20:]),min(l[-20:]))

    sig=None; is_buy=False

    # BREAKOUT pump/dump catcher - added
    rh = max(h[-13:-1])
    rl = min(l[-13:-1])
    prev_rng = (rh - rl) / price * 100 if price>0 else 99
    if prev_rng < 1.8 and v15 >= 2.0:
        if c[-1] > rh and c[-1] > o[-1]:
            sig="BREAKOUT PUMP BUY"; is_buy=True
        elif c[-1] < rl and c[-1] < o[-1]:
            sig="BREAKOUT DUMP SELL"; is_buy=False

    if not sig and v15>=2.0:
        if c[-1]>o[-1] and rsi>55: sig="VOL BOSS BUY"; is_buy=True
        elif c[-1]<o[-1] and rsi<45: sig="VOL BOSS SELL"; is_buy=False
    if not sig and bull_sw and rsi>50: sig="SWEEP BUY"; is_buy=True
    if not sig and bear_sw and rsi<50: sig="SWEEP SELL"; is_buy=False
    if not sig and pat in ("double_bottom","triple_bottom") and v15>1.5: sig=f"{pat.upper()} BUY"; is_buy=True
    if not sig and pat in ("double_top","triple_top") and v15>1.5: sig=f"{pat.upper()} SELL"; is_buy=False
    if not sig: return

    now=time.time(); prev=COOLDOWN["signals"].get(s,{})
    is_flip=prev.get("dir") is not None and prev.get("dir")!=is_buy
    if v15>=3.0: pass
    elif is_flip:
        if now-prev.get("t",0)<60*60: return
    else:
        if prev.get("dir")==is_buy: return
        if now-prev.get("t",0)<240*60: return

    sl = min(l[-1],pl)*0.997 if is_buy else max(h[-1],ph)*1.003
    risk = abs(price - sl)
    if is_buy:
        tp1 = price + risk * 1.5
        tp2 = price + risk * 2.0
    else:
        tp1 = price - risk * 1.5
        tp2 = price - risk * 2.0

    COOLDOWN["signals"][s]={"t":now,"dir":is_buy}; save()
    nai=datetime.now(ZoneInfo("Africa/Nairobi")).strftime("%H:%M")
    tg(f"{'🟢' if is_buy else '🔴'} {s} {'BUY' if is_buy else 'SELL'} {sig} [PERP]\nEntry:{price:.6f} RSI:{rsi:.0f} V15:{v15:.1f}x V1H:{v1h:.1f}x Trend4H:{trend:+.2f}%\nJunction:{jun}\nSL:{sl:.6f} TP1:{tp1:.6f} TP2:{tp2:.6f} [{nai}]")

def volume_radar():
    for s,p in zip(SYMBOLS,PERPS):
        try:
            m1=kl(p,"Min1")
            if not m1 or len(m1["v"])<21: continue
            v=m1["v"]; spike=v[-1]/(sum(v[-21:-1])/20+1e-9)
            if spike>=3.0:
                print(f"⚡ 1m SPIKE {s} {spike:.1f}x - instant scan",flush=True)
                full_scan(s,p)
        except Exception as e: print(e,flush=True)

print("=== BOT V14 VOL-RADAR ===",flush=True)
if "--once" in sys.argv:
    for s,p in zip(SYMBOLS,PERPS):
        try:
            m1=kl(p,"Min1")
            if m1 and len(m1["v"])>=21:
                v1=m1["v"]; sp=v1[-1]/(sum(v1[-21:-1])/20+1e-9)
                if sp>=3.0: print(f"⚡ 1m SPIKE {s} {sp:.1f}x",flush=True)
            full_scan(s,p)
        except Exception as e: print(e,flush=True)
else:
    last15=0
    while True:
        volume_radar()
        if time.time()-last15>900:
            for s,p in zip(SYMBOLS,PERPS):
                try: full_scan(s,p)
                except: pass
            last15=time.time()
        time.sleep(60)
