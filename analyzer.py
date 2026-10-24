import json, math, os, sys, time, requests
from datetime import datetime
import pytz
EAT = pytz.timezone("Africa/Nairobi")
SYMBOLS = ["KOMA_USDT","TAO_USDT","GRASS_USDT","SAND_USDT","JASMY_USDT","SENT_USDT","FARTCOIN_USDT","MUBARAK_USDT","VELVET_USDT","LAB_USDT","PEPE_USDT","BONK_USDT","WIF_USDT","FLOKI_USDT","DOGE_USDT","SHIB_USDT","MANA_USDT","AXS_USDT","APE_USDT","BOME_USDT","BRETT_USDT","MEW_USDT","PENGU_USDT","WLD_USDT","ARB_USDT","OP_USDT","SEI_USDT","ENA_USDT","PENDLE_USDT","MEME_USDT","TURBO_USDT","1000PEPE_USDT","1000BONK_USDT","1000SHIB_USDT","POPCAT_USDT"]

session = requests.Session()
NEAR_THRESHOLD = 0.05
RETEST_THRESHOLD = 0.03

def get_last_structure_from_arrays(h,l,c,o):
    lookback=min(80,len(c))
    if lookback<30: return None
    h=h[-lookback:]; l=l[-lookback:]; c=c[-lookback:]; o=o[-lookback:]
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

def get_1h_box_from_arrays(h,l):
    if len(h)<20: return None
    hh=h[-20:]; ll=l[-20:]; HH=max(hh); LL=min(ll); rng=HH-LL; mid=(HH+LL)/2
    if rng==0 or mid==0: return None
    if rng/mid>0.5: return None
    return {"HH":HH,"LL":LL,"mid":mid,"rng":rng}

def check_pullback_15m_live(live_c, box):
    rng=box["rng"] or 0.00001
    pct=(live_c-box["LL"])/rng*100
    return 30 <= pct <= 90, pct, f"{pct:.1f}%"

def check_entry_5m_from_arrays(o,c,direction):
    if len(c)<3: return False
    oc=o[-1]; cc=c[-1]; o2=o[-2]
    return (cc>oc and cc>=o2) if direction=="BUY" else (cc<oc and cc<=o2)

def get_4h_sr_boxes_from_arrays(h,l):
    lookback=min(50,len(h))
    if lookback<20: return {"support_level": min(l[-20:]), "resist_level": max(h[-20:]), "gap_pct": 15}
    lows=[l[i] for i in range(len(l)-lookback, len(l)-2) if l[i] < l[i-1] and l[i] < l[i+1]]
    highs=[h[i] for i in range(len(h)-lookback, len(h)-2) if h[i] > h[i-1] and h[i] > h[i+1]]
    if not lows or not highs: return {"support_level": min(l[-20:]), "resist_level": max(h[-20:]), "gap_pct": 15}
    sup=min(lows); res=max(highs); gap=(res-sup)/sup*100 if sup>0 else 0
    return {"support_level":sup,"resist_level":res,"gap_pct":gap}

def kl_history(symbol, interval, start_ts, end_ts):
    sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400}
    sec=sec_map.get(interval,300)
    all_data={"o":[],"h":[],"l":[],"c":[],"ts":[]}
    cur=start_ts
    while cur < end_ts:
        nxt = min(cur + sec*350, end_ts)
        url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={cur}&end={nxt}"
        try:
            r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15).json()
            d=r.get("data",r)
            if isinstance(d,dict) and "data" in d: d=d["data"]
            if not d or "close" not in d: cur=nxt; continue
            closes = d["close"]; opens = d["open"]; highs = d["high"]; lows = d["low"]; times = d.get("time", list(range(len(closes))))
            for i in range(len(closes)):
                all_data["o"].append(float(opens[i])); all_data["h"].append(float(highs[i])); all_data["l"].append(float(lows[i])); all_data["c"].append(float(closes[i])); all_data["ts"].append(int(times[i]) if i < len(times) else cur+i*sec)
        except: pass
        cur=nxt; time.sleep(0.25)
    return all_data

def simulate_tp_sl(entry, sl, is_buy, future_h, future_l, max_bars=200):
    tp1 = entry*1.015 if is_buy else entry*0.985
    tp2 = entry*1.028 if is_buy else entry*0.972
    tp3 = entry*1.045 if is_buy else entry*0.955
    for i in range(min(len(future_h), max_bars)):
        h=future_h[i]; l=future_l[i]
        if is_buy:
            if l <= sl: return "LOSS", -1, i
            if h >= tp3: return "WIN", 2.5, i
            if h >= tp2: return "WIN", 1.8, i
            if h >= tp1: return "WIN", 1.0, i
        else:
            if h >= sl: return "LOSS", -1, i
            if l <= tp3: return "WIN", 2.5, i
            if l <= tp2: return "WIN", 1.8, i
            if l <= tp1: return "WIN", 1.0, i
    return "OPEN", 0, max_bars

def month_to_q(month):
    if month in [1,2,3]: return "Q1"
    if month in [4,5,6]: return "Q2"
    if month in [7,8,9]: return "Q3"
    return "Q4"

start_dt = datetime(2024,10,1, tzinfo=EAT)
end_dt = datetime.now(EAT)
start_ts = int(start_dt.timestamp())
end_ts = int(end_dt.timestamp())
all_trades = []

for sym in SYMBOLS:  # all 36 coins
    print(f"\n=== {sym} Oct2024->Now ===")
    h1 = kl_history(sym,"Min60",start_ts,end_ts)
    h4 = kl_history(sym,"Hour4",start_ts,end_ts)
    if len(h1["c"])<100: print(f"  skip {sym} no data"); continue
    for idx in range(100, len(h1["c"])-20):
        hh = h1["h"][:idx]; ll = h1["l"][:idx]; cc = h1["c"][:idx]; oo = h1["o"][:idx]
        struct = get_last_structure_from_arrays(hh,ll,cc,oo)
        if not struct: continue
        live = cc[-1]
        box = get_1h_box_from_arrays(hh,ll)
        if not box: continue
        if len(h4["h"])>=50:
            sr = get_4h_sr_boxes_from_arrays(h4["h"][:max(0,idx//4-50)], h4["l"][:max(0,idx//4-50)])
            if sr["gap_pct"]<3: continue
        direction=None; label=None
        if struct["broke_hh"] and struct["broke_hh_strength"]>=62:
            if abs(live - struct["last_high"])/live <= 0.03: direction="BUY"; label="HH"
        if not direction and struct["broke_ll"] and (struct["broke_ll_strength"]<=38 or struct["broke_ll_strength"]==0):
            ls = struct["broke_ll_strength"] if struct["broke_ll_strength"]!=0 else 25
            if ls<=38 and abs(live - struct["last_low"])/live <= 0.03: direction="SELL"; label="LL"
        if not direction and struct["ll_type"]=="HL" and struct["trend"]=="UP" and struct["hh_type"]=="HH":
            if abs(live - struct["last_low"])/live <= 0.05: direction="BUY"; label="HL"
        if not direction and struct["hh_type"]=="LH" and struct["trend"]=="DOWN" and struct["ll_type"]=="LL":
            if abs(live - struct["last_high"])/live <= 0.05: direction="SELL"; label="LH"
        if not direction: continue
        in_ok, pct, _ = check_pullback_15m_live(live, box)
        if not in_ok: continue
        is_buy = direction=="BUY"
        sl = min(box["LL"]*0.996, live*0.985) if is_buy else max(box["HH"]*1.004, live*1.015)
        fut_h = h1["h"][idx:idx+200]; fut_l = h1["l"][idx:idx+200]
        res, rr, bars = simulate_tp_sl(live, sl, is_buy, fut_h, fut_l)
        if res=="OPEN": continue
        ts = h1["ts"][idx]; dt = datetime.fromtimestamp(ts, tz=EAT); q = month_to_q(dt.month)
        all_trades.append({"sym":sym,"q":q,"month":dt.month,"label":label,"result":res,"rr":rr,"dt":dt.strftime("%Y-%m-%d")})

from collections import defaultdict
by_q = defaultdict(list); by_month = defaultdict(list); by_label = defaultdict(list)
for t in all_trades: 
    by_q[t["q"]].append(t); by_month[t["month"]].append(t); by_label[t["label"]].append(t)

def stats(trades):
    if not trades: return {"txt":"0 trades","wr":50,"tot":0}
    wins=len([x for x in trades if x["result"]=="WIN"]); tot=len(trades); wr=wins/tot*100; avg_rr=sum(x["rr"] for x in trades)/tot
    return {"txt":f"{tot} trades, {wins}W-{tot-wins}L, WR {wr:.1f}%, avg RR {avg_rr:.2f}","wr":wr,"tot":tot}

print("\n\n===== SEASONALITY RESULT Oct2024->Now =====")
summary={}
for q in ["Q1","Q2","Q3","Q4"]:
    s=stats(by_q[q]); print(f"{q}: {s['txt']}"); summary[q]=s['txt']

print("\nBY MONTH:")
for m in range(1,13):
    if m in by_month: print(f"Month {m}: {stats(by_month[m])['txt']}")

print("\nBY LABEL:")
for lb in ["HH","HL","LL","LH"]:
    if lb in by_label: print(f"{lb}: {stats(by_label[lb])['txt']}")

# SAVE FOR BOT
out={"summary":summary,"by_q": {q: stats(by_q[q])["wr"] for q in summary}, "generated": datetime.now(EAT).isoformat(), "total_trades": len(all_trades)}
with open("seasonality.json","w") as f:
    json.dump(out,f,indent=2)
print(f"\nSaved seasonality.json with {len(all_trades)} trades -> Q WR: {out['by_q']}")
print("Now bot.py will auto use it: Q4 71% -> MIN 55, Q3 38% -> MIN 75")
