import json,os,time,tempfile,requests,argparse
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
BASE_SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","JASMY_USDT","LAB_USDT","VELVET_USDT","PEPE_USDT","DOGE_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";HISTORY_FILE="movers_history.json"
session=requests.Session()
TAG="V209-YESTERDAY-REVERSAL"
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
 except:pass

def format_signal_msg(sig, sym):
    mover_tag = f" 🔥 MOVER {sig.get('mover_label','')}" if sig.get('is_mover') else ""
    if sig["side"]=="BUY":
        return (f"🟢🟢🟢 <b>BUY {sym}</b>{mover_tag} 🟢🟢🟢\n"
                f"Entry: <b>{fmt(sig['entry'])}</b>\n"
                f"🛑 SL: <b>{fmt(sig['sl'])}</b> ({((sig['sl']-sig['entry'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['tp1']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 50%\n"
                f"🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['tp2']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 30%\n"
                f"🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['tp3']-sig['entry'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n"
                f"{sig['reason']}\n[{get_time()}] | {TAG}")
    else:
        return (f"🔴🔴🔴 <b>SELL {sym}</b>{mover_tag} 🔴🔴🔴\n"
                f"Entry: <b>{fmt(sig['entry'])}</b>\n"
                f"🛑 SL: <b>{fmt(sig['sl'])}</b>\n"
                f"🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['entry']-sig['tp1'])/sig['entry']*100):+.2f}%) - Close 50%\n"
                f"🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['entry']-sig['tp2'])/sig['entry']*100):+.2f}%) - Close 30%\n"
                f"🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['entry']-sig['tp3'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n"
                f"{sig['reason']}\n[{get_time()}] | {TAG}")

def format_exit_msg(sym, side, live, reason, pnl, entry, sl):
    emoji="🛑" if "SL" in reason else "⚠️"
    return (f"{emoji} <b>EXIT {sym} {side}</b>\n"
            f"Exit: <b>{fmt(live)}</b> | Entry: {fmt(entry)} | SL: {fmt(sl)}\n"
            f"Reason: {reason}\nPnL: <b>{pnl:+.2f}%</b>")

def kl(symbol,interval,min_candles=30):
 sec_map={"Min1":60,"Min5":300,"Min15":900,"Min30":1800,"Hour1":3600,"Min60":3600,"Hour4":14400,"Day1":86400,"Week1":604800,"Month1":2592000}
 sec=sec_map.get(interval,300); api_interval=interval
 if interval=="Month1": api_interval="Day1"; sec=86400
 if interval=="Week1": api_interval="Day1"; sec=86400
 if interval=="Hour1": api_interval="Min60"
 if interval=="Min1": api_interval="Min5"
 end=int(time.time()); start=end-sec*500
 url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={api_interval}&start={start}&end={end}"
 for _ in range(3):
  try:
   r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15);j=r.json();d=j.get("data",j)
   if isinstance(d,dict) and "data" in d:d=d["data"]
   if not d or "open" not in d:continue
   res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",[0]*len(d["close"]))]}
   for k in res:res[k]=res[k][:-1]
   if len(res["c"])<min_candles:continue
   return res
  except:time.sleep(1)
 return None

def get_live(s):
 for t in [s,s.replace("_",""),s.replace("_USDT","USDT")]:
  try:
   r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json();data=r.get("data",r);lp=data.get("lastPrice") or data.get("last_price") or data.get("price")
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
                if sym in BASE_SYMBOLS: continue
                chg=float(it.get("riseFallRate",0) or 0)
                if abs(chg) <= 2: chg = chg*100
                vol_usd=float(it.get("amount24",0) or 0)
                if vol_usd==0:
                    lp=float(it.get("lastPrice",0) or 0)
                    vol_usd=float(it.get("volume24",0) or 0)*lp
                parsed.append((sym,chg,vol_usd))
            except: continue
        parsed=[x for x in parsed if x[2] > 200000]
        gainers=[x for x in parsed if 30 <= x[1] <= 150]
        losers=[x for x in parsed if -50 <= x[1] <= -30]
        gainers=sorted(gainers, key=lambda x: x[1], reverse=True)[:3]
        losers=sorted(losers, key=lambda x: x[1])[:3]
        for sym,chg,_ in gainers: movers[sym]=f"+{chg:.1f}% GAINER"
        for sym,chg,_ in losers: movers[sym]=f"{chg:.1f}% LOSER"
        print(f"MOVERS TODAY: {movers}")
        try:
            hist=load_json(HISTORY_FILE,{})
            hist[get_today()]=movers
            for k in list(hist.keys()):
                if k < get_2days_ago(): del hist[k]
            atomic_save(HISTORY_FILE,hist)
            print(f"MOVERS SAVED for tomorrow: {movers}")
        except Exception as e: print(f"history save err {e}")
    except Exception as e: print(f"movers err {e}")
    return movers

def get_yesterday_movers():
    try:
        hist=load_json(HISTORY_FILE,{})
        y=hist.get(get_yesterday(),{})
        d2=hist.get(get_2days_ago(),{})
        out={}
        for sym,label in y.items():
            out[sym]=f"YESTERDAY {label} -> REVERSAL"
        for sym,label in d2.items():
            if sym not in out and "LOSER" in label:
                out[sym]=f"2DAYS AGO {label} -> BOUNCE"
        print(f"MOVERS YESTERDAY: {out}")
        return out
    except Exception as e:
        print(f"yesterday err {e}"); return {}

def get_sr_levels(sym):
    supports=[]; resistances=[]
    try:
        d1h=kl(sym,"Hour1",min_candles=20); d4h=kl(sym,"Hour4",min_candles=15)
        for d in [d1h,d4h]:
            if not d: continue
            h=d["h"]; l=d["l"]; c=d["c"]
            atr=calc_atr(d) or c[-1]*0.02
            piv_high=[]; piv_low=[]
            for i in range(3,len(h)-3):
                if h[i]==max(h[i-3:i+4]): piv_high.append(h[i])
                if l[i]==min(l[i-3:i+4]): piv_low.append(l[i])
            def cluster(pivots):
                out=[]
                pivots=sorted(pivots)
                for p in pivots:
                    found=False
                    for j,(price,touches) in enumerate(out):
                        if abs(p-price)/price < 0.005:
                            out[j]=(price,touches+1); found=True; break
                    if not found: out.append((p,1))
                return [(p,t) for p,t in out if t>=2]
            supports+=cluster(piv_low)
            resistances+=cluster(piv_high)
        supports=sorted(list(set(supports)), reverse=True)[:5]
        resistances=sorted(list(set(resistances)))[:5]
    except Exception as e: print(f"SR err {sym} {e}")
    return supports, resistances

def get_4h_direction(d4h, is_mover=False):
    try:
        if not d4h or len(d4h["c"]) < 15:
            # FIX FLOAT: new coin with short history - treat as RANGE, let S/R decide
            if is_mover: return "RANGE", f"Short history {len(d4h['c']) if d4h else 0} candles - MOVER RANGE"
            return "NEUTRAL", "no data"
        h=d4h["h"]; l=d4h["l"]; c=d4h["c"]
        highs=[]; lows=[]
        for i in range(3,len(h)-3):
            if h[i]==max(h[i-3:i+4]): highs.append(h[i])
            if l[i]==min(l[i-3:i+4]): lows.append(l[i])
        highs=highs[-3:]; lows=lows[-3:]
        if len(highs)<3 or len(lows)<3:
            # FIX JCT: crashed in straight line, no pivots = exhausted = RANGE
            if is_mover: return "RANGE", f"Exhausted crash/pump no pivots H {fmt(max(h))} L {fmt(min(l))} - MOVER RANGE"
            return "NEUTRAL","not enough pivots need 3"
        h1,h2,h3=highs[-3],highs[-2],highs[-1]
        l1,l2,l3=lows[-3],lows[-2],lows[-1]
        if abs(h3-h1)/h1 < 0.02 and abs(l3-l1)/l1 < 0.02:
            return "RANGE", f"Range H {fmt(h3)} L {fmt(l3)}"
        if h3>h2>h1 and l3>l2>l1:
            return "BULLISH", f"2TO2 HH {fmt(h1)}->{fmt(h2)}->{fmt(h3)} HL {fmt(l1)}->{fmt(l2)}->{fmt(l3)}"
        if h3<h2<h1 and l3<l2<l1:
            return "BEARISH", f"2TO2 LH {fmt(h1)}->{fmt(h2)}->{fmt(h3)} LL {fmt(l1)}->{fmt(l2)}->{fmt(l3)}"
        return "RANGE", f"Sideways H {fmt(h3)} L {fmt(l3)} - no 2TO2"
    except Exception as e: return "NEUTRAL", f"err {e}"

def get_30m_zones(d30):
    try:
        if not d30 or len(d30["c"])<20: return None, None
        h=d30["h"]; l=d30["l"]; c=d30["c"]
        demand=None; supply=None
        for i in range(len(c)-2, 2, -1):
            move_up = (c[i]-c[i-2])/c[i-2]*100 if c[i-2]>0 else 0
            move_dn = (c[i-2]-c[i])/c[i-2]*100 if c[i-2]>0 else 0
            if move_up >= 2.5 and demand is None:
                demand={"low": min(l[i-2:i+1]), "high": max(h[i-2:i+1]), "idx": i, "move": move_up}
            if move_dn >= 2.5 and supply is None:
                supply={"low": min(l[i-2:i+1]), "high": max(h[i-2:i+1]), "idx": i, "move": move_dn}
            if demand and supply: break
        return demand, supply
    except: return None, None

def get_liq_pools(sym, live):
    pools=[]
    try:
        d1h=kl(sym,"Hour1",min_candles=20); d1=kl(sym,"Day1",min_candles=5)
        if d1h:
            h=d1h["h"]; l=d1h["l"]
            for i in range(3,len(h)-3):
                if h[i]==max(h[i-3:i+4]): pools.append(h[i])
                if l[i]==min(l[i-3:i+4]): pools.append(l[i])
            if len(h)>=24:
                pools.append(max(h[-24:])); pools.append(min(l[-24:]))
        if d1 and len(d1["h"])>=3:
            pools.append(d1["h"][-2]); pools.append(d1["l"][-2])
            pools.append(d1["h"][-1]); pools.append(d1["l"][-1])
            if len(d1["h"])>=8:
                pools.append(max(d1["h"][-7:])); pools.append(min(d1["l"][-7:]))
    except: pass
    uniq=[]
    for p in sorted(set(pools)):
        if not uniq or abs(p-uniq[-1])/uniq[-1] > 0.005: uniq.append(p)
    above=[p for p in uniq if p > live*1.001]
    below=[p for p in uniq if p < live*0.999]
    below=sorted(below, reverse=True)
    return above, below

def get_5m_trigger(d5, side, atr, is_mover):
    try:
        if not d5 or len(d5["c"])<20: return False, "no 5M data", 0, 0, False
        h=d5["h"]; l=d5["l"]; c=d5["c"]
        sl_buffer = 1.0 if is_mover else 0.5
        if side=="BUY":
            low1=min(l[-10:-5]); low2=min(l[-5:])
            if not (low2 > low1): return False, f"no HL {fmt(low1)}->{fmt(low2)}", 0, 0, False
            breakout = max(h[-6:-1])
            sweep=False; sweep_low=min(l[-6:])
            if sweep_low < low2 and c[-1] > low2: sweep=True
            if c[-1] > breakout:
                sl = sweep_low - atr*sl_buffer*0.2 if sweep else low2 - atr*sl_buffer*0.2
                tag="SWEEP" if sweep else "BREAK"
                return True, f"{tag} HL {fmt(low1)}->{fmt(low2)} break {fmt(breakout)} sweepLow {fmt(sweep_low)}", sl, breakout, sweep
            return False, f"HL ok, waiting break > {fmt(breakout)} live {fmt(c[-1])}", 0, 0, False
        if side=="SELL":
            high1=max(h[-10:-5]); high2=max(h[-5:])
            if not (high2 < high1): return False, f"no LH {fmt(high1)}->{fmt(high2)}", 0, 0, False
            breakdown = min(l[-6:-1])
            sweep=False; sweep_high=max(h[-6:])
            if sweep_high > high2 and c[-1] < high2: sweep=True
            if c[-1] < breakdown:
                sl = sweep_high + atr*sl_buffer*0.2 if sweep else high2 + atr*sl_buffer*0.2
                tag="SWEEP" if sweep else "BREAK"
                return True, f"{tag} LH {fmt(high1)}->{fmt(high2)} break {fmt(breakdown)} sweepHigh {fmt(sweep_high)}", sl, breakdown, sweep
            return False, f"LH ok, waiting break < {fmt(breakdown)} live {fmt(c[-1])}", 0, 0, False
        return False, "no side", 0, 0, False
    except Exception as e: return False, f"5M err {e}", 0, 0, False

def v206_signal(sym, live, is_mover=False, mover_label=""):
    d4h=kl(sym,"Hour4",min_candles=15 if is_mover else 30); d30=kl(sym,"Min30",min_candles=20 if is_mover else 30); d5=kl(sym,"Min5",min_candles=20)
    if not d4h or not d30 or not d5: return None, "missing TF data"
    direction, dir_reason = get_4h_direction(d4h, is_mover=is_mover)
    demand, supply = get_30m_zones(d30)
    atr = calc_atr(d30)
    if atr==0: atr=live*0.02
    in_demand=False; in_supply=False
    if demand and demand["low"]*0.995 <= live <= demand["high"]*1.005: in_demand=True
    if supply and supply["low"]*0.995 <= live <= supply["high"]*1.005: in_supply=True
    supports, resistances = get_sr_levels(sym)
    nearest_support = max([p for p,_ in supports if p <= live*1.01], default=None)
    nearest_resist = min([p for p,_ in resistances if p >= live*0.99], default=None)
    sr_tol = atr*0.5 if is_mover else atr*1.0
    at_support = nearest_support and abs(live-nearest_support) <= sr_tol
    at_resist = nearest_resist and abs(live-nearest_resist) <= sr_tol
    above, below = get_liq_pools(sym, live)
    atr_pct = (atr/live*100) if live>0 else 0
    if is_mover:
        tp2_mult, tp3_mult, label = 2.0, 3.0, "MOVER-FAST"
    elif atr_pct < 1.0:
        tp2_mult, tp3_mult, label = 2.0, 3.0, "FOLLOWER"
    elif atr_pct < 3.0:
        tp2_mult, tp3_mult, label = 3.0, 5.0, "NORMAL"
    else:
        tp2_mult, tp3_mult, label = 4.0, 8.0, "RUNNER"
    def tp_buy():
        min_gap = max(live*0.008, atr*1.0)
        if is_mover:
            tp1 = round_level(live*1.06)
            if nearest_resist and tp1 > nearest_resist*0.98: tp1 = round_level(nearest_resist*0.98)
            tp2 = round_level(tp1 + atr*tp2_mult)
            tp3 = round_level(tp2 + atr*tp3_mult)
            return tp1,tp2,tp3
        tp1 = round_level(above[0]) if len(above)>=1 else round_level(live+atr*2)
        if tp1 < live+atr*0.5: tp1=round_level(live+atr*2)
        if nearest_resist and tp1 > nearest_resist*0.99: tp1 = round_level(nearest_resist*0.99)
        tp2 = None
        for p in above:
            if p > tp1 + min_gap: tp2=round_level(p); break
        if tp2 is None: tp2=round_level(tp1+atr*tp2_mult)
        if tp2 <= tp1: tp2 = round_level(tp1 + min_gap)
        runner_target = max(tp2 + atr*tp3_mult, live*1.04)
        tp3 = None
        for p in above:
            if p > tp2 + min_gap and p >= runner_target*0.9: tp3=round_level(p); break
        if tp3 is None: tp3=round_level(runner_target)
        if tp3 <= tp2: tp3 = round_level(tp2 + min_gap)
        return tp1,tp2,tp3
    def tp_sell():
        min_gap = max(live*0.008, atr*1.0)
        if is_mover:
            tp1 = round_level(live*0.94)
            if nearest_support and tp1 < nearest_support*1.02: tp1 = round_level(nearest_support*1.02)
            tp2 = round_level(tp1 - atr*tp2_mult)
            tp3 = round_level(tp2 - atr*tp3_mult)
            return tp1,tp2,tp3
        tp1 = round_level(below[0]) if len(below)>=1 else round_level(live-atr*2)
        if tp1 > live-atr*0.5: tp1=round_level(live-atr*2)
        if nearest_support and tp1 < nearest_support*1.01: tp1 = round_level(nearest_support*1.01)
        tp2 = None
        for p in below:
            if p < tp1 - min_gap: tp2=round_level(p); break
        if tp2 is None: tp2=round_level(tp1-atr*tp2_mult)
        if tp2 >= tp1: tp2 = round_level(tp1 - min_gap)
        runner_target = min(tp2 - atr*tp3_mult, live*0.96)
        tp3 = None
        for p in below:
            if p < tp2 - min_gap and p <= runner_target*1.1: tp3=round_level(p); break
        if tp3 is None: tp3=round_level(runner_target)
        if tp3 >= tp2: tp3 = round_level(tp2 - min_gap)
        return tp1,tp2,tp3
    if direction=="RANGE":
        if in_demand or at_support:
            ok, msg, sl, trig, sweep = get_5m_trigger(d5,"BUY",atr,is_mover)
            if ok:
                tp1,tp2,tp3=tp_buy()
                return {"side":"BUY","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"RANGE + Demand/Support {fmt(nearest_support) if nearest_support else ''} + {msg} | 4H {dir_reason} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"RANGE BUY {msg} | {label} {mover_label}"
            return None, f"RANGE in Demand/Support, waiting 5M: {msg} | SR Sup {fmt(nearest_support) if nearest_support else 'none'}"
        if in_supply or at_resist:
            ok, msg, sl, trig, sweep = get_5m_trigger(d5,"SELL",atr,is_mover)
            if ok:
                tp1,tp2,tp3=tp_sell()
                return {"side":"SELL","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"RANGE + Supply/Resist {fmt(nearest_resist) if nearest_resist else ''} + {msg} | 4H {dir_reason} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"RANGE SELL {msg} | {label} {mover_label}"
            return None, f"RANGE {dir_reason} | not in zone live {fmt(live)} SR R {fmt(nearest_resist) if nearest_resist else 'none'} S {fmt(nearest_support) if nearest_support else 'none'}"
    if direction=="BULLISH":
        if not (in_demand or at_support): return None, f"BULLISH {dir_reason} | not in Demand/Support live {fmt(live)} Sup {fmt(nearest_support) if nearest_support else 'none'}"
        ok, msg, sl, trig, sweep = get_5m_trigger(d5,"BUY",atr,is_mover)
        if not ok: return None, f"BULLISH in Demand/Support, waiting 5M: {msg}"
        tp1,tp2,tp3=tp_buy()
        return {"side":"BUY","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"BULLISH + Demand/Support + {msg} | 4H {dir_reason} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"BULLISH BUY {msg} | {label} {mover_label}"
    if direction=="BEARISH":
        if not (in_supply or at_resist): return None, f"BEARISH {dir_reason} | not in Supply/Resist live {fmt(live)} Res {fmt(nearest_resist) if nearest_resist else 'none'}"
        ok, msg, sl, trig, sweep = get_5m_trigger(d5,"SELL",atr,is_mover)
        if not ok: return None, f"BEARISH in Supply/Resist, waiting 5M: {msg}"
        tp1,tp2,tp3=tp_sell()
        return {"side":"SELL","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"BEARISH + Supply/Resist + {msg} | 4H {dir_reason} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"BEARISH SELL {msg} | {label} {mover_label}"
    return None, f"NEUTRAL {dir_reason} | no trade"

def btc_confirms(alt_side, btc_dir, mover_label=""):
    # FIX: Yesterday loser bounce should NOT be blocked by BTC bearish - that's the reversal play
    if "YESTERDAY" in mover_label and "LOSER" in mover_label and alt_side=="BUY":
        return True
    if "YESTERDAY" in mover_label and "GAINER" in mover_label and alt_side=="SELL":
        return True
    if alt_side=="BUY" and btc_dir=="BEARISH": return False
    if alt_side=="SELL" and btc_dir=="BULLISH": return False
    return True

def check_active_positions_v206():
    for sym in list(ACTIVE.keys()):
        try:
            info=ACTIVE[sym]
            if not isinstance(info, dict): continue
            entry=float(info.get("entry",0)); side=info.get("side","BUY"); sl=float(info.get("sl",0))
            tp1=float(info.get("tp1",0))
            live=get_live(sym)
            if not live: continue
            d4h=kl(sym,"Hour4",min_candles=15)
            direction,_ = get_4h_direction(d4h, is_mover=True)
            flip=False
            if side=="BUY" and direction=="BEARISH": flip=True
            if side=="SELL" and direction=="BULLISH": flip=True
            sl_hit = (live <= sl) if side=="BUY" else (live >= sl)
            if side=="BUY" and live>=tp1 and not info.get("tp1_hit"):
                info["tp1_hit"]=True; info["sl"]=entry; save_a()
                print(f"{GREEN}TP1 HIT {sym} {side} @ {fmt(live)} - SL moved to entry{RESET}")
                tg(f"✅ <b>TP1 HIT {sym} {side}</b> @ {fmt(live)}\nSL moved to entry {fmt(entry)}")
            if side=="SELL" and live<=tp1 and not info.get("tp1_hit"):
                info["tp1_hit"]=True; info["sl"]=entry; save_a()
                print(f"{GREEN}TP1 HIT {sym} {side} @ {fmt(live)} - SL moved to entry{RESET}")
                tg(f"✅ <b>TP1 HIT {sym} {side}</b> @ {fmt(live)}\nSL moved to entry {fmt(entry)}")
            if flip or sl_hit:
                reason = "4H FLIP EXIT" if flip else "SL HIT EXIT"
                pnl=(live-entry)/entry*100 if side=="BUY" else (entry-live)/entry*100
                print(f"{RED}EXIT {sym} {reason} PnL {pnl:.2f}%{RESET}")
                tg(format_exit_msg(sym, side, live, reason, pnl, entry, sl))
                del ACTIVE[sym]; save_a()
        except Exception as e: print(f"exit check err {sym} {e}")

def run_once():
    print(f"{CYAN}[{get_time()}] | {TAG} | 4H 2TO2 / 30M / 5M SWEEP + S/R + YESTERDAY REVERSAL{RESET}")
    print("-"*100)
    btc_d4h=kl("BTC_USDT","Hour4")
    btc_dir, btc_reason = get_4h_direction(btc_d4h)
    print(f"{CYAN}BTC 4H = {btc_dir} | {btc_reason}{RESET}")
    check_active_positions_v206()
    yesterday_movers = get_yesterday_movers()
    today_movers = get_mexc_movers()
    movers = {}
    movers.update(today_movers)
    for sym,label in yesterday_movers.items():
        if sym in movers:
            movers[sym]=movers[sym]+f" + {label}"
        else:
            movers[sym]=label
    print(f"MOVERS COMBINED: {movers}")
    SYMBOLS = BASE_SYMBOLS + [s for s in movers.keys() if s not in BASE_SYMBOLS]
    print(f"{CYAN}Scanning {len(SYMBOLS)} coins: {SYMBOLS}{RESET}")
    signals=[]
    for sym in SYMBOLS:
        try:
            live=get_live(sym)
            if not live: continue
            is_mover = sym in movers
            mover_label = movers.get(sym,"")
            sig, debug = v206_signal(sym, live, is_mover=is_mover, mover_label=mover_label)
            d4h=kl(sym,"Hour4",min_candles=15 if is_mover else 30)
            direction, dir_reason = get_4h_direction(d4h, is_mover=is_mover)
            if sig:
                if sym != "BTC_USDT":
                    if not btc_confirms(sig["side"], btc_dir, mover_label):
                        print(f"{YELLOW}SKIP {sym} {sig['side']} - BTC {btc_dir} not confirming | {debug}{RESET}")
                        continue
                color = GREEN if sig["side"]=="BUY" else RED
                emoji = "🟢 BUY" if sig["side"]=="BUY" else "🔴 SELL"
                print(f"{color}{BOLD}{emoji} {sym} @ {fmt(sig['entry'])} | SL {fmt(sig['sl'])} | TP1 {fmt(sig['tp1'])} | TP2 {fmt(sig['tp2'])} | TP3 {fmt(sig['tp3'])} | BTC {btc_dir} OK | {debug}{RESET}")
                tg(format_signal_msg(sig, sym))
                signals.append(sym)
                ACTIVE[sym]={"side":sig["side"],"entry":sig["entry"],"sl":sig["sl"],"tp1":sig["tp1"],"tp2":sig["tp2"],"tp3":sig["tp3"],"time":get_time()}
                save_a()
            else:
                print(f"{YELLOW}{sym} live={fmt(live)} 4H={direction} | {debug}{RESET}")
        except Exception as e: print(f"{sym} err {e}")
    print(f"DONE {len(signals)} signals: {signals}")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--once",action="store_true"); a=ap.parse_args()
    run_once()
