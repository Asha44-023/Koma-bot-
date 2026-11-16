import json,os,time,tempfile,requests,argparse
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";HISTORY_FILE="movers_history.json"
session=requests.Session()
TAG="V800-PUMP-DUMP"
GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; CYAN="\033[96m"; RESET="\033[0m"; BOLD="\033[1m"

def get_time():return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today():return datetime.now(EAT).strftime("%Y-%m-%d")
def get_yesterday():return (datetime.now(EAT)-timedelta(days=1)).strftime("%Y-%m-%d")
def get_2days_ago():return (datetime.now(EAT)-timedelta(days=2)).strftime("%Y-%m-%d")
def load_json(p,d):
 try:
  with open(p,"r") as f:v=json.load(f);return v if isinstance(v,type(d)) else d
 except:return d
def atomic_save(path,data):
 d=os.path.dirname(os.path.abspath(path)) or ".";fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
 try:
  with os.fdopen(fd,"w") as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno());os.replace(tp,path)
 except:
  try:os.unlink(tp)
  except:pass;raise
ACTIVE=load_json(ACTIVE_FILE,{});COOLDOWN=load_json(COOLDOWN_FILE,{});COOLDOWN.setdefault("daily_pnl",0.0);COOLDOWN.setdefault("last_day",get_today())
def save_a():atomic_save(ACTIVE_FILE,ACTIVE)
def fmt(p):
 try:
  p=float(p)
  if p<0.01:return f"{p:.8f}".rstrip('0').rstrip('.')
  if p<1:return f"{p:.6f}".rstrip('0').rstrip('.')
  return f"{p:.4f}".rstrip('0').rstrip('.')
 except:return "0"
def round_level(p):
 try:
  p=float(p)
  if p==0: return 0
  if p>=1000:return round(p/50)*50
  if p>=100:return round(p/5)*5
  if p>=10:return round(p*2)/2
  if p>=1:return round(p*100)/100
  if p>=0.1:return round(p*1000)/1000
  if p>=0.01:return round(p*10000)/10000
  if p>=0.001:return round(p*100000)/100000
  if p>=0.0001:return round(p*1000000)/1000000
  if p>=0.00001:return round(p*10000000)/10000000
  return round(p*100000000)/100000000
 except:return p
def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m,"parse_mode":"HTML"},timeout=15)
 except Exception as e:print(f"tg err {e}")
def format_signal_msg(sig, sym):
    mover_tag = f" 🔥 {sig.get('mover_label','')}" if sig.get('is_mover') else ""
    sl_pct = (sig['sl']-sig['entry'])/sig['entry']*100 if sig["side"]=="BUY" else (sig['entry']-sig['sl'])/sig['entry']*100
    if sig["side"]=="BUY":
        return (f"🟢🟢🟢 <b>BUY {sym}</b>{mover_tag} 🟢🟢🟢\nEntry: <b>{fmt(sig['entry'])}</b>\n🛑 SL: <b>{fmt(sig['sl'])}</b> ({sl_pct:+.2f}%)\n🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['tp1']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 50%\n🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['tp2']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 30%\n🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['tp3']-sig['entry'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n{sig['reason']}\n[{get_time()}] | {TAG}")
    else:
        return (f"🔴🔴🔴 <b>SELL {sym}</b>{mover_tag} 🔴🔴🔴\nEntry: <b>{fmt(sig['entry'])}</b>\n🛑 SL: <b>{fmt(sig['sl'])}</b> ({-sl_pct:+.2f}%)\n🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['entry']-sig['tp1'])/sig['entry']*100):+.2f}%) - Close 50%\n🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['entry']-sig['tp2'])/sig['entry']*100):+.2f}%) - Close 30%\n🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['entry']-sig['tp3'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n{sig['reason']}\n[{get_time()}] | {TAG}")
def format_exit_msg(sym, side, live, reason, pnl, entry, sl):
    emoji="🛑" if "SL" in reason else "⚠️"
    return (f"{emoji} <b>EXIT {sym} {side}</b>\nExit: <b>{fmt(live)}</b> | Entry: {fmt(entry)} | SL: {fmt(sl)}\nReason: {reason}\nPnL: <b>{pnl:+.2f}%</b>")

def kl(symbol,interval,min_candles=30):
 sec_map={"Min1":60,"Min5":300,"Min15":900,"Min30":1800,"Min60":3600,"Hour1":3600,"Hour4":14400,"Day1":86400,"Week1":604800}
 sec=sec_map.get(interval,900); api_interval=interval
 if interval=="Hour1": api_interval="Min60"
 if interval=="Min1": api_interval="Min5"
 if interval=="Week1": api_interval="Day1"; sec=86400
 end=int(time.time()); start=end-sec*500
 url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={api_interval}&start={start}&end={end}"
 for _ in range(3):
  try:
   r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15);j=r.json();d=j.get("data",j)
   if isinstance(d,dict) and "data" in d:d=d["data"]
   if not d or "open" not in d:continue
   res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",[0]*len(d["close"]))]}
   if len(res["c"])<min_candles:continue
   return res
  except Exception as e:
   print(f"kl err {symbol} {interval} {e}");time.sleep(1)
 return None
def get_live(s):
 for t in [s,s.replace("_",""),s.replace("_USDT","USDT")]:
  try:
   r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json();data=r.get("data",r)
   if isinstance(data,list): data=data[0] if data else {}
   lp=data.get("lastPrice") or data.get("last_price") or data.get("price")
   if lp and float(lp)>0:return float(lp)
  except:pass
 return None

def get_mexc_movers():
    # Returns {sym: {"label": "+48.4% GAINER", "chg": 48.4}}
    movers={}
    try:
        r=session.get("https://contract.mexc.com/api/v1/contract/ticker",timeout=15).json()
        data=r.get("data",[])
        if isinstance(data,dict): data=[data]
        if not isinstance(data,list): return movers
        parsed=[]
        for it in data:
            try:
                sym=it.get("symbol","")
                if not sym.endswith("_USDT"): continue
                chg=float(it.get("riseFallRate",0) or 0)
                if -2.5 < chg < 2.5 and chg != 0: chg = chg*100
                vol_usd=float(it.get("amount24",0) or 0)
                if vol_usd==0:
                    lp=float(it.get("lastPrice",0) or 0)
                    vol_usd=float(it.get("volume24",0) or 0)*lp
                if vol_usd < 500000: continue
                parsed.append((sym,chg,vol_usd))
            except: continue
        gainers=[x for x in parsed if 30 <= x[1] <= 300]
        losers=[x for x in parsed if -90 <= x[1] <= -30]
        gainers=sorted(gainers, key=lambda x: x[1], reverse=True)[:5]
        losers=sorted(losers, key=lambda x: x[1])[:5]
        for sym,chg,_ in gainers: movers[sym]={"label":f"+{chg:.1f}% GAINER","chg":chg}
        for sym,chg,_ in losers: movers[sym]={"label":f"{chg:.1f}% LOSER","chg":chg}
        print(f"MOVERS TODAY: { {k:v['label'] for k,v in movers.items()} }")
        try:
            hist=load_json(HISTORY_FILE,{})
            # Save as {sym: chg} for runner check tomorrow
            hist[get_today()]={k:v["chg"] for k,v in movers.items()}
            for k in list(hist.keys()):
                if k < get_2days_ago(): del hist[k]
            atomic_save(HISTORY_FILE,hist)
        except Exception as e: print(f"history err {e}")
    except Exception as e: print(f"movers err {e}")
    return movers

def get_yesterday_movers():
    # Returns {sym: chg_yesterday}
    try:
        hist=load_json(HISTORY_FILE,{})
        y=hist.get(get_yesterday(),{})
        d2=hist.get(get_2days_ago(),{})
        out={}
        # hist values can be old format {sym: "label"} or new {sym: chg}
        def parse_chg(v):
            if isinstance(v,(int,float)): return float(v)
            try:
                # "+48.4% GAINER" -> 48.4
                s=str(v).replace("%","").replace("GAINER","").replace("LOSER","").strip()
                return float(s.split()[0])
            except: return 0
        for sym,v in y.items(): out[sym]=parse_chg(v)
        for sym,v in d2.items():
            if sym not in out: out[sym]=parse_chg(v)
        return out
    except: return {}

# ================= V800 - PUMP / DUMP - NO BOS, NO STRUCTURE =================
def get_daily_mid(sym):
    # Only thing we need from Daily: mid of 90d range
    try:
        d1=kl(sym,"Day1",min_candles=60)
        if not d1 or len(d1["c"])<60: return None
        h=d1["h"]; l=d1["l"]
        high_90=max(h[-90:]); low_90=min(l[-90:])
        mid=(high_90+low_90)/2
        return mid, high_90, low_90
    except: return None

def v800_signal(sym, live, chg_today, chg_yest, label):
    """
    YOUR RULE:
    Pumped +30 to +300%:
      - live ABOVE mid = HAS TO PUMP MORE -> BUY
      - live BELOW mid = Fake pump, HAS TO DUMP -> SELL
    Dumped -30 to -90%:
      - live BELOW mid = HAS TO DUMP MORE -> SELL
      - live ABOVE mid = Fake dump, HAS TO PUMP -> BUY
    Runner: today + yesterday same direction = RUNNER CONFIRMED, stronger
    """
    mid_data=get_daily_mid(sym)
    if not mid_data:
        return None, f"No daily mid for {sym} - skip"
    mid, high_90, low_90 = mid_data
    above_mid = live > mid

    # Runner check
    is_runner=False
    runner_txt=""
    if chg_yest is not None:
        if chg_today>0 and chg_yest>0:
            is_runner=True; runner_txt=f"RUNNER CONFIRMED +{chg_today:.1f}% TODAY + +{chg_yest:.1f}% YESTERDAY"
        elif chg_today<0 and chg_yest<0:
            is_runner=True; runner_txt=f"RUNNER CONFIRMED {chg_today:.1f}% TODAY + {chg_yest:.1f}% YESTERDAY"

    # Decide HAS TO PUMP or HAS TO DUMP
    if chg_today >= 30:
        # PUMPED
        if above_mid:
            side="BUY"; verdict="HAS TO PUMP MORE"
            reason=f"V800 PUMPED +{chg_today:.1f}% | Live {fmt(live)} ABOVE Mid {fmt(mid)} | Real Pump | {verdict}"
        else:
            side="SELL"; verdict="HAS TO DUMP"
            reason=f"V800 PUMPED +{chg_today:.1f}% | Live {fmt(live)} BELOW Mid {fmt(mid)} | Fake Pump | {verdict}"
    elif chg_today <= -30:
        # DUMPED
        if not above_mid:
            side="SELL"; verdict="HAS TO DUMP MORE"
            reason=f"V800 DUMPED {chg_today:.1f}% | Live {fmt(live)} BELOW Mid {fmt(mid)} | Real Dump | {verdict}"
        else:
            side="BUY"; verdict="HAS TO PUMP"
            reason=f"V800 DUMPED {chg_today:.1f}% | Live {fmt(live)} ABOVE Mid {fmt(mid)} | Fake Dump | {verdict}"
    else:
        return None, "Not a mover +-30%"

    if is_runner:
        reason+=f" | {runner_txt} | HOLD FOR WEEK - Small dump = pullback, not reversal"
    else:
        reason+=f" | {label} | New Face - Day 1"

    # Entry = live now, no waiting for pullback / BOS
    entry=live
    if side=="BUY":
        sl=round_level(entry*0.90)  # -10% SL, runner can dip small
        tp1=round_level(entry*1.15); tp2=round_level(entry*1.30); tp3=round_level(entry*1.50)
    else:
        sl=round_level(entry*1.10)  # +10% SL
        tp1=round_level(entry*0.85); tp2=round_level(entry*0.70); tp3=round_level(entry*0.50)

    sig={"side":side,"entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":reason,"is_mover":True,"mover_label":f"{label} | {verdict} | {'RUNNER' if is_runner else 'DAY1'}"}
    return sig, reason

def check_exits():
    for sym in list(ACTIVE.keys()):
        try:
            pos=ACTIVE[sym]; live=get_live(sym)
            if not live: continue
            side=pos["side"]; entry=pos["entry"]; sl=pos["sl"]
            pnl = (live-entry)/entry*100 if side=="BUY" else (entry-live)/entry*100
            reason=None
            if side=="BUY" and live<=sl: reason="SL HIT"
            if side=="SELL" and live>=sl: reason="SL HIT"
            if side=="BUY" and live>=pos["tp1"] and not pos.get("tp1_hit"):
                pos["tp1_hit"]=True; pos["sl"]=entry; save_a(); tg(f"✅ TP1 HIT {sym} +15% - SL to BE")
            if side=="SELL" and live<=pos["tp1"] and not pos.get("tp1_hit"):
                pos["tp1_hit"]=True; pos["sl"]=entry; save_a(); tg(f"✅ TP1 HIT {sym} +15% - SL to BE")
            if reason:
                tg(format_exit_msg(sym, side, live, reason, pnl, entry, sl))
                del ACTIVE[sym]; save_a()
        except Exception as e: print(f"exit err {sym} {e}")

def run_once():
    print(f"[{get_time()}] | {TAG} | PUMP/DUMP - NO BOS")
    print("-"*100)
    check_exits()
    movers_today=get_mexc_movers()
    movers_yest=get_yesterday_movers()
    print(f"YESTERDAY: {movers_yest}")
    signals=[]
    # Only today's movers give signals - everyday new gainer/loser
    for sym,data in movers_today.items():
        if sym in ACTIVE: print(f"{sym} already in trade, skip"); continue
        live=get_live(sym)
        if not live: print(f"{sym} no live"); continue
        chg_today=data["chg"]; label=data["label"]
        chg_yest=movers_yest.get(sym)
        sig,msg=v800_signal(sym, live, chg_today, chg_yest, label)
        print(f"{sym} live={fmt(live)} | {msg}")
        if sig:
            ACTIVE[sym]={"side":sig["side"],"entry":sig["entry"],"sl":sig["sl"],"tp1":sig["tp1"],"tp2":sig["tp2"],"tp3":sig["tp3"],"reason":sig["reason"]}
            save_a(); signals.append(sym); tg(format_signal_msg(sig, sym))
    print(f"DONE {len(signals)} signals: {signals}")

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--once",action="store_true"); args=parser.parse_args()
    if os.getenv("RESET")=="true":
        ACTIVE.clear(); COOLDOWN.clear(); COOLDOWN.update({"daily_pnl":0.0,"last_day":get_today()}); save_a(); atomic_save(COOLDOWN_FILE,COOLDOWN)
    if args.once:
        run_once(); return
    while True:
        try: run_once()
        except Exception as e: print(f"loop err {e}")
        print(f"Sleeping 900s (15min) - next scan {get_time()}")
        time.sleep(900)

if __name__=="__main__": main()
