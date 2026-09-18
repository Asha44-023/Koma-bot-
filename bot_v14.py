import requests, time, json, os, numpy as np
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN=os.environ.get("TELEGRAM_TOKEN","")
TELEGRAM_CHAT=os.environ.get("TELEGRAM_CHAT_ID","")
def tg(m):
    if not TELEGRAM_TOKEN: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id":TELEGRAM_CHAT,"text":m,"parse_mode":"HTML"},timeout=10)
    except: pass

BASE="https://fapi.binance.com"; SYMS=["GRASSUSDT","VELVETUSDT","LABUSDT","HEIUSDT","SENTUSDT","SIRENUSDT","KOMAUSDT"]
STATE_FILE="/tmp/bot_state_v20.json"

def save():
    try: json.dump({"state":STATE,"signals":COOLDOWN["signals"],"last_seen":COOLDOWN["last_seen"],"boot_time":BOOT_TIME},open(STATE_FILE,"w"))
    except: pass
def load():
    try:
        d=json.load(open(STATE_FILE)); STATE.update(d.get("state",{}))
        COOLDOWN["signals"].update(d.get("signals",{})); COOLDOWN["last_seen"].update(d.get("last_seen",{}))
        return d.get("boot_time", time.time())
    except: return time.time()

STATE={}; COOLDOWN={"signals":{},"last_seen":{}}; BOOT_TIME=load()

def kl(s,i):
    try:
        r=requests.get(f"{BASE}/fapi/v1/klines",params={"symbol":s,"interval":i,"limit":100},timeout=10).json()
        return np.array([[float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in r])
    except: return None

def vol_profile(d):
    v=d[:,4]; bv=d[:,4]*(d[:,4]>0)*(d[:,3]>d[:,0]); sv=d[:,4]-bv
    buy_pct=100*np.sum(bv[-20:])/(np.sum(v[-20:])+1e-9); sell_pct=100-buy_pct
    vx=np.mean(v[-5:])/(np.mean(v[-20:-5])+1e-9)
    return {"vol_x":vx,"buy_pct":buy_pct,"sell_pct":sell_pct}

def bos_choch(d):
    h,l=d[:,1],d[:,2]; hh=np.max(h[-10:-1]); ll=np.min(l[-10:-1]); c=d[-1,3]
    if c>hh: return "BOS_UP"
    if c<ll: return "BOS_DOWN"
    return None

def trend_pa(d):
    c=d[:,3]; ema20=np.mean(c[-20:]); ema50=np.mean(c[-50:])
    body=c[-1]-d[-1,0]; rng=d[-1,1]-d[-1,2]+1e-9
    if c[-1]>ema20>c[-50:].mean() and body>0.3*rng: return "bullish_engulfing"
    if c[-1]<ema20<ema50 and body<-0.3*rng: return "bearish_engulfing"
    return "none"

def full_scan(s):
    d15=kl(s,"15m"); d1h=kl(s,"1h")
    if d15 is None or d1h is None: return
    price=d15[-1,3]
    bos=bos_choch(d15); pat=trend_pa(d15)
    e20_1h=np.mean(d1h[:,3][-20:]); e50_1h=np.mean(d1h[:,3][-50:])
    trend15="UP" if d15[-1,3]>np.mean(d15[:,3][-20:]) else "DOWN"
    trend1h="UP" if d1h[-1,3]>e20_1h else "DOWN"
    state="ALIGNED_UP" if trend15=="UP" and trend1h=="UP" else "ALIGNED_DOWN" if trend15=="DOWN" and trend1h=="DOWN" else None
    if not state:
        print(f"skip {s} 15m:{trend15} 1h:{trend1h} disagree",flush=True); return
    if not bos and pat=="none":
        print(f"quiet {s} no structure",flush=True); return
    vp=vol_profile(d15)

    # Early warning: volume building but not enough for entry
    if vp["vol_x"] >= 1.0 and vp["vol_x"] < 1.2 and (bos or pat!= "none"):
        now_ew = time.time()
        prev_ew = COOLDOWN["signals"].get(f"EW_{s}", {})
        if now_ew - prev_ew.get("t", 0) > 30*60:
            COOLDOWN["signals"][f"EW_{s}"] = {"t": now_ew}
            save()
            tg(f"⚠️ <b>{s} building</b> [{state}]\n"
               f"Structure: {bos or ''} {pat}\n"
               f"Vol: {vp['vol_x']:.2f}x Buy {vp['buy_pct']:.0f}% Sell {vp['sell_pct']:.0f}%\n"
               f"Price: {price} - watching for 1.2x entry")
        print(f"watch {s} {vp['vol_x']:.2f}x {state}",flush=True)
        return

    if vp["vol_x"]<1.2:
        print(f"quiet {s} {vp['vol_x']:.2f}x {state}",flush=True); return
    sig="BUY" if state=="ALIGNED_UP" and vp["buy_pct"]>55 else "SELL" if state=="ALIGNED_DOWN" and vp["sell_pct"]>55 else None
    if not sig:
        print(f"quiet {s} vol ok but delta weak {vp['buy_pct']:.0f}/{vp['sell_pct']:.0f}",flush=True); return
    now=time.time(); prev=COOLDOWN["signals"].get(s,{})
    if now-prev.get("t",0)<6*3600:
        print(f"cooldown {s}",flush=True); return
    COOLDOWN["signals"][s]={"t":now,"sig":sig}; save()
    m=("🟢" if sig=="BUY" else "🔴")+f" <b>{s} {sig}</b> [{state}]\nStructure: {bos or ''} {pat}\nVol: {vp['vol_x']:.2f}x Buy {vp['buy_pct']:.0f}% Sell {vp['sell_pct']:.0f}%\nPrice: {price}"
    tg(m); print(m,flush=True)

if __name__=="__main__":
    import sys
    print("=== BOT V20.1 - 15m+1h ===",flush=True)
    for s in SYMS: full_scan(s)
    if "--once" not in sys.argv:
        while True:
            time.sleep(60)
            for s in SYMS: full_scan(s)
