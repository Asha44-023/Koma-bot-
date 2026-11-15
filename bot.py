import json,os,time,tempfile,requests,argparse
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";HISTORY_FILE="movers_history.json"
session=requests.Session()
TAG="V700-CYCLE-MACRO+15M"
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
def calc_atr(d1,period=14):
 try:
  h=d1["h"];l=d1["l"];c=d1["c"];tr=[]
  for i in range(1,len(c)):tr.append(max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])))
  return sum(tr[-period:])/period if len(tr)>=period else c[-1]*0.03
 except:return 0.0

def get_mexc_movers():
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
        losers=[x for x in parsed if -80 <= x[1] <= -30]
        gainers=sorted(gainers, key=lambda x: x[1], reverse=True)[:5]
        losers=sorted(losers, key=lambda x: x[1])[:5]
        for sym,chg,_ in gainers: movers[sym]=f"+{chg:.1f}% GAINER"
        for sym,chg,_ in losers: movers[sym]=f"{chg:.1f}% LOSER"
        print(f"MOVERS TODAY: {movers}")
        try:
            hist=load_json(HISTORY_FILE,{})
            hist[get_today()]=movers
            for k in list(hist.keys()):
                if k < get_2days_ago(): del hist[k]
            atomic_save(HISTORY_FILE,hist)
        except Exception as e: print(f"history err {e}")
    except Exception as e: print(f"movers err {e}")
    return movers
def get_yesterday_movers():
    try:
        hist=load_json(HISTORY_FILE,{})
        y=hist.get(get_yesterday(),{}); d2=hist.get(get_2days_ago(),{})
        out={}
        for sym,label in y.items(): out[sym]=f"YESTERDAY {label}"
        for sym,label in d2.items():
            if sym not in out: out[sym]=f"2DAYS {label}"
        return out
    except: return {}

# ================= V700 - CYCLE PHASE =================
def get_cycle_phase(sym, live):
    # Uses Daily (last 90 days) to decide: MARKUP / DISTRIBUTION / MARKDOWN / ACCUMULATION
    # This is the "perfect logic" - macro decides direction.
    try:
        d1=kl(sym,"Day1",min_candles=60)
        if not d1 or len(d1["c"])<60: return "UNKNOWN","not enough daily data"
        h=d1["h"]; l=d1["l"]; c=d1["c"]
        # Last 90d high/low, last 30d high/low
        high_90=max(h[-90:]); low_90=min(l[-90:])
        high_30=max(h[-30:]); low_30=min(l[-30:])
        # Where is price vs range?
        # 1. MARKDOWN: price broke below 30d low AND below 50% of 90d range, and making lower highs
        # Example KAVA: high_90=0.084, low_30=0.06, live=0.026 -> MARKDOWN
        range_mid = (high_90+low_90)/2
        # Check for lower highs on daily last 10 candles
        # Find last 3 daily swings
        # Simple: last 10 daily highs are declining?
        last_highs = h[-10:]
        lower_highs = last_highs[-1] < last_highs[-5] < last_highs[0]
        # Distribution: price chopping in top 30% of range for >21 days, not breaking out
        top_zone_low = high_90 - (high_90-low_90)*0.30
        in_top_zone = all(x > top_zone_low*0.85 for x in c[-21:])
        range_21 = max(h[-21:]) - min(l[-21:])
        is_flat_21 = range_21 / c[-1] < 0.25  # less than 25% range in 21 days = flat
        if live < low_30 and live < range_mid and lower_highs:
            return "MARKDOWN", f"Daily broke 30d low {fmt(low_30)} | Live {fmt(live)} < mid {fmt(range_mid)} | Lower Highs - SHORTS ONLY"
        if live < low_30 and live < range_mid:
            return "MARKDOWN", f"Daily broke 30d low {fmt(low_30)} | Live {fmt(live)} - SHORTS ONLY"
        if in_top_zone and is_flat_21 and lower_highs:
            return "DISTRIBUTION", f"Flat top 21d {fmt(min(l[-21:]))}-{fmt(max(h[-21:]))} + Lower Highs - NO TRADE (whale selling)"
        if in_top_zone and is_flat_21:
            return "DISTRIBUTION", f"Flat top 21d - NO TRADE"
        # Markup: price above mid, making higher highs
        last_lows = l[-10:]
        higher_lows = last_lows[-1] > last_lows[-5]
        if live > range_mid and higher_lows:
            return "MARKUP", f"Daily above mid {fmt(range_mid)} + Higher Lows - LONGS ONLY"
        if live > range_mid:
            return "MARKUP", f"Daily above mid {fmt(range_mid)} - LONGS ONLY"
        # Accumulation: price near 90d low, flat
        if live < low_90*1.20 and is_flat_21:
            return "ACCUMULATION", f"Near 90d low {fmt(low_90)} flat - NO TRADE, wait for markup"
        return "MARKUP" if live > range_mid else "MARKDOWN", f"Fallback live {fmt(live)} vs mid {fmt(range_mid)}"
    except Exception as e:
        return "UNKNOWN", f"phase err {e}"

def get_swings_15m(d):
    h=d["h"]; l=d["l"]; out=[]
    for i in range(2,len(h)-2):
        if h[i]==max(h[i-2:i+3]): out.append((i,"H",h[i]))
        if l[i]==min(l[i-2:i+3]): out.append((i,"L",l[i]))
    return out

def get_15m_entry(d15, live, allowed_side):
    # Returns structure dict if 15M confirms allowed_side with Sweep+BOS or BOS continuation + pullback to OB
    try:
        if not d15 or len(d15["c"])<40: return None
        h=d15["h"]; l=d15["l"]; c=d15["c"]; o=d15["o"]
        sw=get_swings_15m(d15)
        if len(sw)<4: return None
        # Try to find BOS in last 12 candles (3h) in allowed direction
        if allowed_side=="BUY":
            lows=[(i,p) for i,t,p in sw if t=="L"][-3:]
            highs=[(i,p) for i,t,p in sw if t=="H"][-3:]
            if len(lows)<2 or len(highs)<2: return None
            prior_low=lows[-2][1]
            sweep_idx=None; sweep_price=None
            for i in range(max(0,len(c)-80), len(c)):
                if l[i] < prior_low and c[i] > prior_low:
                    sweep_idx=i; sweep_price=l[i]; break
            # If no sweep, try continuation: BOS without sweep = still valid in MARKUP
            bos_price=highs[-1][1] if highs else None
            bos_idx=None
            start = sweep_idx if sweep_idx is not None else max(0,len(c)-30)
            for i in range(start, len(c)):
                if c[i] > bos_price:
                    bos_idx=i; break
            if bos_idx is None or bos_idx < len(c)-12: return None
            ob_low=None; ob_high=None
            for i in range(bos_idx, max(start, bos_idx-8), -1):
                if c[i] < o[i]:
                    ob_low=min(l[max(0,i-1):i+2]); ob_high=max(h[max(0,i-1):i+2]); break
            if ob_low is None:
                ob_low=min(l[bos_idx-3:bos_idx]); ob_high=max(h[bos_idx-3:bos_idx])
            atr=calc_atr(d15)
            if abs(live-(ob_low+ob_high)/2) > atr*4: return None
            return {"side":"BUY","sweep":sweep_price,"bos":bos_price,"zone_low":ob_low,"zone_high":ob_high,"debug":f"15M Sweep {fmt(sweep_price) if sweep_price else 'none'} BOS > {fmt(bos_price)} OB {fmt(ob_low)}-{fmt(ob_high)}"}
        else: # SELL
            highs=[(i,p) for i,t,p in sw if t=="H"][-3:]
            lows=[(i,p) for i,t,p in sw if t=="L"][-3:]
            if len(highs)<2 or len(lows)<2: return None
            prior_high=highs[-2][1]
            sweep_idx=None; sweep_price=None
            for i in range(max(0,len(c)-80), len(c)):
                if h[i] > prior_high and c[i] < prior_high:
                    sweep_idx=i; sweep_price=h[i]; break
            bos_price=lows[-1][1] if lows else None
            bos_idx=None
            start = sweep_idx if sweep_idx is not None else max(0,len(c)-30)
            for i in range(start, len(c)):
                if c[i] < bos_price:
                    bos_idx=i; break
            if bos_idx is None or bos_idx < len(c)-12: return None
            ob_low=None; ob_high=None
            for i in range(bos_idx, max(start, bos_idx-8), -1):
                if c[i] > o[i]:
                    ob_low=min(l[max(0,i-1):i+2]); ob_high=max(h[max(0,i-1):i+2]); break
            if ob_low is None:
                ob_low=min(l[bos_idx-3:bos_idx]); ob_high=max(h[bos_idx-3:bos_idx])
            atr=calc_atr(d15)
            if abs(live-(ob_low+ob_high)/2) > atr*4: return None
            return {"side":"SELL","sweep":sweep_price,"bos":bos_price,"zone_low":ob_low,"zone_high":ob_high,"debug":f"15M Sweep {fmt(sweep_price) if sweep_price else 'none'} BOS < {fmt(bos_price)} OB {fmt(ob_low)}-{fmt(ob_high)}"}
    except Exception as e:
        print(f"15m entry err {e}"); return None

def v700_signal(sym, live, mover_label):
    phase, phase_reason = get_cycle_phase(sym, live)
    if phase in ["DISTRIBUTION","ACCUMULATION","UNKNOWN"]:
        return None, f"PHASE {phase} | {phase_reason} | NO TRADE"
    allowed = "BUY" if phase=="MARKUP" else "SELL"
    d15=kl(sym,"Min15",min_candles=50)
    d5=kl(sym,"Min5",min_candles=20)
    if not d15 or not d5: return None, f"PHASE {phase} | missing 15M/5M"
    struct=get_15m_entry(d15, live, allowed)
    if not struct: return None, f"PHASE {phase} | {phase_reason} | No 15M {allowed} BOS yet - waiting pullback"
    zone_low, zone_high = struct["zone_low"], struct["zone_high"]
    in_zone = zone_low*0.99 <= live <= zone_high*1.01
    if not in_zone:
        return None, f"PHASE {phase} | 15M {struct['debug']} | waiting pullback to OB live {fmt(live)} zone {fmt(zone_low)}-{fmt(zone_high)}"
    h=d5["h"]; l=d5["l"]; c=d5["c"]; o=d5["o"]; v=d5["v"]
    body=abs(c[-1]-o[-1]); rng=h[-1]-l[-1] if h[-1]>l[-1] else 1
    body_pct=body/rng if rng>0 else 0
    avg_vol=sum(v[-6:-1])/5 if len(v)>=6 else 1
    vol_ok = v[-1] > avg_vol*1.3 if avg_vol>0 else False
    if body_pct < 0.5: return None, f"PHASE {phase} | in OB but 5M body {body_pct*100:.0f}% <50% weak"
    if not vol_ok: return None, f"PHASE {phase} | in OB but 5M vol low"
    atr=calc_atr(d15)
    if allowed=="BUY":
        sl=min(l[-6:]) - atr*0.2; entry=live
        tp1=round_level(entry*1.08); tp2=round_level(entry*1.15); tp3=round_level(entry*1.25)
        reason=f"V700 {phase} LONG | {mover_label} | {phase_reason} | {struct['debug']} | 5M body {body_pct*100:.0f}%"
    else:
        sl=max(h[-6:]) + atr*0.2; entry=live
        tp1=round_level(entry*0.92); tp2=round_level(entry*0.85); tp3=round_level(entry*0.75)
        reason=f"V700 {phase} SHORT | {mover_label} | {phase_reason} | {struct['debug']} | 5M body {body_pct*100:.0f}%"
    return {"side":allowed,"entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":reason,"is_mover":True,"mover_label":f"{mover_label} | {phase}"}, reason

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
                pos["tp1_hit"]=True; pos["sl"]=entry; save_a(); tg(f"✅ TP1 HIT {sym} +8% - SL to BE")
            if side=="SELL" and live<=pos["tp1"] and not pos.get("tp1_hit"):
                pos["tp1_hit"]=True; pos["sl"]=entry; save_a(); tg(f"✅ TP1 HIT {sym} +8% - SL to BE")
            if reason:
                tg(format_exit_msg(sym, side, live, reason, pnl, entry, sl))
                del ACTIVE[sym]; save_a()
        except Exception as e: print(f"exit err {sym} {e}")

def run_once():
    print(f"[{get_time()}] | {TAG} | CYCLE PHASE + 15M ENTRY")
    print("-"*100)
    check_exits()
    movers_today=get_mexc_movers()
    movers_yest=get_yesterday_movers()
    combined={}
    for k,v in movers_yest.items(): combined[k]=v
    for k,v in movers_today.items():
        if k in combined: combined[k]=f"{v} + {combined[k]}"
        else: combined[k]=v
    print(f"MOVERS COMBINED: {combined}")
    signals=[]
    for sym,label in combined.items():
        if sym in ACTIVE: print(f"{sym} already in trade, skip"); continue
        live=get_live(sym)
        if not live: print(f"{sym} no live"); continue
        sig,msg=v700_signal(sym, live, label)
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
    # RENDER MODE: loop forever every 15 min - solves GitHub cron problem
    while True:
        try: run_once()
        except Exception as e: print(f"loop err {e}")
        print(f"Sleeping 900s (15min) - next scan {get_time()}")
        time.sleep(900)

if __name__=="__main__": main()
