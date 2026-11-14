import json,os,time,tempfile,requests,argparse
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
BASE_SYMBOLS=["BTC_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";HISTORY_FILE="movers_history.json"
session=requests.Session()
TAG="V400-STRUCTURE-JRMANAS"
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
    mover_tag = f" 🔥 MOVER {sig.get('mover_label','')}" if sig.get('is_mover') else ""
    sl_pct = (sig['sl']-sig['entry'])/sig['entry']*100 if sig["side"]=="BUY" else (sig['entry']-sig['sl'])/sig['entry']*100
    if sig["side"]=="BUY":
        return (f"🟢🟢🟢 <b>BUY {sym}</b>{mover_tag} 🟢🟢🟢\nEntry: <b>{fmt(sig['entry'])}</b>\n🛑 SL: <b>{fmt(sig['sl'])}</b> ({sl_pct:+.2f}%)\n🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['tp1']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 50%\n🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['tp2']-sig['entry'])/sig['entry']*100):+.2f}%) - Close 30%\n🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['tp3']-sig['entry'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n{sig['reason']}\n[{get_time()}] | {TAG}")
    else:
        return (f"🔴🔴🔴 <b>SELL {sym}</b>{mover_tag} 🔴🔴🔴\nEntry: <b>{fmt(sig['entry'])}</b>\n🛑 SL: <b>{fmt(sig['sl'])}</b> ({-sl_pct:+.2f}%)\n🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['entry']-sig['tp1'])/sig['entry']*100):+.2f}%) - Close 50%\n🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['entry']-sig['tp2'])/sig['entry']*100):+.2f}%) - Close 30%\n🏃 TP3 RUNNER: <b>{fmt(sig['tp3'])}</b> ({((sig['entry']-sig['tp3'])/sig['entry']*100):+.2f}%) - Hold 20% + SL to BE\n{sig['reason']}\n[{get_time()}] | {TAG}")
def format_exit_msg(sym, side, live, reason, pnl, entry, sl):
    emoji="🛑" if "SL" in reason else "⚠️"
    return (f"{emoji} <b>EXIT {sym} {side}</b>\nExit: <b>{fmt(live)}</b> | Entry: {fmt(entry)} | SL: {fmt(sl)}\nReason: {reason}\nPnL: <b>{pnl:+.2f}%</b>")
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
                if -2.5 < chg < 2.5 and chg != 0:
                    chg = chg*100
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
        print(f"MOVERS TODAY DYNAMIC: {movers}")
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
        for sym,label in y.items(): out[sym]=f"YESTERDAY {label} -> REVERSAL"
        for sym,label in d2.items():
            if sym not in out and "LOSER" in label: out[sym]=f"2DAYS AGO {label} -> BOUNCE"
        print(f"MOVERS YESTERDAY: {out}")
        return out
    except Exception as e: print(f"yesterday err {e}"); return {}
def get_sr_levels(sym):
    supports=[]; resistances=[]
    try:
        d1h=kl(sym,"Hour1",min_candles=20); d4h=kl(sym,"Hour4",min_candles=15)
        for d in [d1h,d4h]:
            if not d: continue
            h=d["h"]; l=d["l"]; c=d["c"]
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
                        if abs(p-price)/price < 0.005: out[j]=(price,touches+1); found=True; break
                    if not found: out.append((p,1))
                return [(p,t) for p,t in out if t>=2]
            supports+=cluster(piv_low); resistances+=cluster(piv_high)
        supports=sorted(list(set(supports)), reverse=True)[:5]
        resistances=sorted(list(set(resistances)))[:5]
    except Exception as e: print(f"SR err {sym} {e}")
    return supports, resistances
def get_liq_pools(sym, live):
    pools=[]
    try:
        d1h=kl(sym,"Hour1",min_candles=20); d1=kl(sym,"Day1",min_candles=5)
        if d1h:
            h=d1h["h"]; l=d1h["l"]
            for i in range(3,len(h)-3):
                if h[i]==max(h[i-3:i+4]): pools.append(h[i])
                if l[i]==min(l[i-3:i+4]): pools.append(l[i])
            if len(h)>=24: pools.append(max(h[-24:])); pools.append(min(l[-24:]))
        if d1 and len(d1["h"])>=3:
            pools.append(d1["h"][-2]); pools.append(d1["l"][-2]); pools.append(d1["h"][-1]); pools.append(d1["l"][-1])
            if len(d1["h"])>=8: pools.append(max(d1["h"][-7:])); pools.append(min(d1["l"][-7:]))
    except: pass
    uniq=[]
    for p in sorted(set(pools)):
        if not uniq or abs(p-uniq[-1])/uniq[-1] > 0.005: uniq.append(p)
    above=[p for p in uniq if p > live*1.001]; below=[p for p in uniq if p < live*0.999]; below=sorted(below, reverse=True)
    return above, below

# ================= V400.1 - STRUCTURE FIRST - PATCHED =================
def get_swings(d):
    h=d["h"]; l=d["l"]; out=[]
    for i in range(3,len(h)-3):
        if h[i]==max(h[i-3:i+4]): out.append((i,"H",h[i]))
        if l[i]==min(l[i-3:i+4]): out.append((i,"L",l[i]))
    return out

def get_daily_bias(d1):
    try:
        if not d1 or len(d1["c"])<10: return "RANGE","no daily data"
        sw=get_swings(d1)
        highs=[p for _,t,p in sw if t=="H"][-3:]
        lows=[p for _,t,p in sw if t=="L"][-3:]
        if len(highs)<2 or len(lows)<2: return "RANGE","not enough daily swings"
        if highs[-1]>highs[-2] and lows[-1]>lows[-2]: return "BULLISH",f"Daily HH/HL H {fmt(highs[-2])}->{fmt(highs[-1])} L {fmt(lows[-2])}->{fmt(lows[-1])}"
        if highs[-1]<highs[-2] and lows[-1]<lows[-2]: return "BEARISH",f"Daily LH/LL H {fmt(highs[-2])}->{fmt(highs[-1])} L {fmt(lows[-2])}->{fmt(lows[-1])}"
        return "RANGE",f"Daily sideways H {fmt(highs[-1])} L {fmt(lows[-1])}"
    except Exception as e: return "RANGE",f"daily err {e}"

def get_4h_structure(d4h):
    try:
        if not d4h or len(d4h["c"])<30: return None
        h=d4h["h"]; l=d4h["l"]; c=d4h["c"]; o=d4h["o"]; v=d4h["v"]
        sw=get_swings(d4h)
        if len(sw)<4: return None
        for side in ["BUY","SELL"]:
            if side=="BUY":
                lows=[(i,p) for i,t,p in sw if t=="L"][-3:]
                highs=[(i,p) for i,t,p in sw if t=="H"][-3:]
                if len(lows)<2 or len(highs)<2: continue
                prior_low=lows[-2][1]; last_low=lows[-1][1]
                sweep_idx=None; sweep_price=None
                # PATCHED: 60 candles, not 25
                for i in range(max(0,len(c)-60), len(c)):
                    if l[i] < prior_low and c[i] > prior_low:
                        sweep_idx=i; sweep_price=l[i]; break
                if sweep_idx is None: continue
                bos_price=highs[-1][1]; bos_idx=None
                for i in range(sweep_idx, len(c)):
                    if c[i] > bos_price:
                        bos_idx=i; break
                if bos_idx is None: continue
                ob_low=None; ob_high=None
                for i in range(bos_idx, max(sweep_idx, bos_idx-10), -1):
                    if c[i] < o[i]:
                        ob_low=min(l[i-1:i+2]); ob_high=max(h[i-1:i+2]); break
                if ob_low is None:
                    ob_low=min(l[bos_idx-3:bos_idx]); ob_high=max(h[bos_idx-3:bos_idx])
                pattern=""
                if abs(last_low-prior_low)/prior_low < 0.005: pattern=" + Double Bottom"
                return {"side":"BUY","sweep":sweep_price,"bos":bos_price,"zone_low":ob_low,"zone_high":ob_high,"pattern":pattern,"debug":f"4H Sweep {fmt(sweep_price)} BOS > {fmt(bos_price)} OB {fmt(ob_low)}-{fmt(ob_high)}{pattern}"}
            else:
                highs=[(i,p) for i,t,p in sw if t=="H"][-3:]
                lows=[(i,p) for i,t,p in sw if t=="L"][-3:]
                if len(highs)<2 or len(lows)<2: continue
                prior_high=highs[-2][1]; last_high=highs[-1][1]
                sweep_idx=None; sweep_price=None
                # PATCHED: 60 candles, not 25
                for i in range(max(0,len(c)-60), len(c)):
                    if h[i] > prior_high and c[i] < prior_high:
                        sweep_idx=i; sweep_price=h[i]; break
                if sweep_idx is None: continue
                bos_price=lows[-1][1]; bos_idx=None
                for i in range(sweep_idx, len(c)):
                    if c[i] < bos_price:
                        bos_idx=i; break
                if bos_idx is None: continue
                ob_low=None; ob_high=None
                for i in range(bos_idx, max(sweep_idx, bos_idx-10), -1):
                    if c[i] > o[i]:
                        ob_low=min(l[i-1:i+2]); ob_high=max(h[i-1:i+2]); break
                if ob_low is None:
                    ob_low=min(l[bos_idx-3:bos_idx]); ob_high=max(h[bos_idx-3:bos_idx])
                pattern=""
                if abs(last_high-prior_high)/prior_high < 0.005: pattern=" + Double Top"
                return {"side":"SELL","sweep":sweep_price,"bos":bos_price,"zone_low":ob_low,"zone_high":ob_high,"pattern":pattern,"debug":f"4H Sweep {fmt(sweep_price)} BOS < {fmt(bos_price)} OB {fmt(ob_low)}-{fmt(ob_high)}{pattern}"}
        return None
    except Exception as e:
        print(f"4h struct err {e}"); return None

def get_5m_trigger_v400(d5, side, zone_low, zone_high, atr, is_mover):
    try:
        if not d5 or len(d5["c"])<20: return False,"no 5M data",0,False
        h=d5["h"]; l=d5["l"]; c=d5["c"]; o=d5["o"]; v=d5["v"]
        live=c[-1]
        in_zone = zone_low*0.995 <= live <= zone_high*1.005
        if not in_zone: return False,f"not in Entry zone live {fmt(live)} zone {fmt(zone_low)}-{fmt(zone_high)}",0,False
        body=abs(c[-1]-o[-1]); rng=h[-1]-l[-1] if h[-1]>l[-1] else 1
        body_pct=body/rng if rng>0 else 0
        avg_vol=sum(v[-6:-1])/5 if len(v)>=6 else 1
        vol_ok = v[-1] > avg_vol*1.5 if avg_vol>0 else False
        if body_pct < 0.6: return False,f"SS in zone but body {body_pct*100:.0f}% <60% - fakeout",0,False
        if not vol_ok: return False,f"SS in zone but vol {v[-1]:.0f} <1.5x avg {avg_vol:.0f}",0,False
        if side=="BUY":
            ss_low=min(l[-6:])
            sweep = ss_low < zone_low and c[-1] > zone_low
            hl = min(l[-5:]) > min(l[-10:-5])
            if not (sweep or hl): return False,f"in zone, waiting SS/HL sweepLow {fmt(ss_low)} zoneLow {fmt(zone_low)}",0,False
            sl = ss_low - atr*0.2
            return True,f"SS HOLD in OB {fmt(zone_low)}-{fmt(zone_high)} body {body_pct*100:.0f}% vol 1.5x+ sweepLow {fmt(ss_low)}",sl,True
        else:
            ss_high=max(h[-6:])
            sweep = ss_high > zone_high and c[-1] < zone_high
            lh = max(h[-5:]) < max(h[-10:-5])
            if not (sweep or lh): return False,f"in zone, waiting SS/LH sweepHigh {fmt(ss_high)} zoneHigh {fmt(zone_high)}",0,False
            sl = ss_high + atr*0.2
            return True,f"SS HOLD in OB {fmt(zone_low)}-{fmt(zone_high)} body {body_pct*100:.0f}% vol 1.5x+ sweepHigh {fmt(ss_high)}",sl,True
    except Exception as e: return False,f"5M v400 err {e}",0,False

def v400_signal(sym, live, is_mover=False, mover_label="", btc_daily="RANGE"):
    d1=kl(sym,"Day1",min_candles=15)
    d4h=kl(sym,"Hour4",min_candles=30)
    d1h=kl(sym,"Hour1",min_candles=20)
    d5=kl(sym,"Min5",min_candles=20)
    if not d1 or not d4h or not d5: return None,"missing TF data D1/4H/5M"
    daily_bias, daily_reason = get_daily_bias(d1)
    allow_counter = is_mover and ("YESTERDAY" in mover_label or "2DAYS" in mover_label)
    # PATCHED: Daily RANGE = let 4H decide, don't skip
    if daily_bias=="RANGE":
        pass
    struct=get_4h_structure(d4h)
    if not struct: return None,f"Daily {daily_bias} | No 4H Sweep+BOS yet | {daily_reason}"
    side=struct["side"]
    if not allow_counter:
        if daily_bias=="BULLISH" and side!="BUY": return None,f"Daily BULLISH vs 4H {side} - conflict SKIP | {struct['debug']}"
        if daily_bias=="BEARISH" and side!="SELL": return None,f"Daily BEARISH vs 4H {side} - conflict SKIP | {struct['debug']}"
    if sym!="BTC_USDT" and not is_mover:
        if btc_daily=="BULLISH" and side!="BUY": return None,f"BTC Daily BULLISH blocks {side}"
        if btc_daily=="BEARISH" and side!="SELL": return None,f"BTC Daily BEARISH blocks {side}"
    d30=kl(sym,"Min30",min_candles=20)
    atr=calc_atr(d30) if d30 else live*0.02
    if atr==0: atr=live*0.02
    ok, msg, sl, swept = get_5m_trigger_v400(d5, side, struct["zone_low"], struct["zone_high"], atr, is_mover)
    if not ok: return None,f"Daily {daily_bias} | 4H {struct['debug']} | waiting 5M SS: {msg}"
    supports, resistances = get_sr_levels(sym)
    nearest_support = max([p for p,_ in supports if p <= live*1.01], default=None)
    nearest_resist = min([p for p,_ in resistances if p >= live*0.99], default=None)
    above, below = get_liq_pools(sym, live)
    atr_pct=(atr/live*100) if live>0 else 0
    if is_mover: tp2_mult, tp3_mult, label = 2.0, 3.0, "MOVER-FAST"
    elif atr_pct < 1.0: tp2_mult, tp3_mult, label = 2.0, 3.0, "FOLLOWER"
    elif atr_pct < 3.0: tp2_mult, tp3_mult, label = 3.0, 5.0, "NORMAL"
    else: tp2_mult, tp3_mult, label = 4.0, 8.0, "RUNNER"
    def tp_buy():
        min_gap = max(live*0.008, atr*1.0)
        if is_mover:
            tp1 = round_level(live*1.06)
            if nearest_resist and tp1 > nearest_resist*0.98: tp1 = round_level(nearest_resist*0.98)
            tp2 = round_level(tp1 + atr*tp2_mult); tp3 = round_level(tp2 + atr*tp3_mult); return tp1,tp2,tp3
        tp1 = round_level(above[0]) if len(above)>=1 else round_level(live+atr*2)
        if tp1 < live+atr*0.5: tp1=round_level(live+atr*2)
        if nearest_resist and tp1 > nearest_resist*0.99: tp1 = round_level(nearest_resist*0.99)
        tp2=None
        for p in above:
            if p > tp1 + min_gap: tp2=round_level(p); break
        if tp2 is None: tp2=round_level(tp1+atr*tp2_mult)
        if tp2 <= tp1: tp2 = round_level(tp1 + min_gap)
        runner_target = max(tp2 + atr*tp3_mult, live*1.04); tp3=None
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
            tp2 = round_level(tp1 - atr*tp2_mult); tp3 = round_level(tp2 - atr*tp3_mult); return tp1,tp2,tp3
        tp1 = round_level(below[0]) if len(below)>=1 else round_level(live-atr*2)
        if tp1 > live-atr*0.5: tp1=round_level(live-atr*2)
        if nearest_support and tp1 < nearest_support*1.01: tp1 = round_level(nearest_support*1.01)
        tp2=None
        for p in below:
            if p < tp1 - min_gap: tp2=round_level(p); break
        if tp2 is None: tp2=round_level(tp1-atr*tp2_mult)
        if tp2 >= tp1: tp2 = round_level(tp1 - min_gap)
        runner_target = min(tp2 - atr*tp3_mult, live*0.96); tp3=None
        for p in below:
            if p < tp2 - min_gap and p <= runner_target*1.1: tp3=round_level(p); break
        if tp3 is None: tp3=round_level(runner_target)
        if tp3 >= tp2: tp3 = round_level(tp2 - min_gap)
        return tp1,tp2,tp3
    if side=="BUY":
        tp1,tp2,tp3=tp_buy()
        risk=abs(live-sl) if sl>0 else atr
        if risk>0 and (tp1-live)/risk < 1.0: return None,f"BUY RR <1 to TP1 SKIP | {struct['debug']}"
        return {"side":"BUY","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"V400 Daily {daily_bias} | 4H {struct['debug']} | 5M {msg} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"V400 BUY {msg} | {label} {mover_label}"
    else:
        tp1,tp2,tp3=tp_sell()
        risk=abs(live-sl) if sl>0 else atr
        if risk>0 and (live-tp1)/risk < 1.0: return None,f"SELL RR <1 to TP1 SKIP | {struct['debug']}"
        return {"side":"SELL","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_mover":is_mover,"mover_label":mover_label,"reason":f"V400 Daily {daily_bias} | 4H {struct['debug']} | 5M {msg} | TP=Next Liq/SR {label} ATR%{atr_pct:.2f} {mover_label}"}, f"V400 SELL {msg} | {label} {mover_label}"

def get_4h_direction(d4h, is_mover=False):
    s=get_4h_structure(d4h)
    if not s: return "RANGE","no 4H Sweep+BOS"
    return ("BULLISH" if s["side"]=="BUY" else "BEARISH"), s["debug"]

def btc_confirms(alt_side, btc_dir, mover_label="", is_mover=False):
    if is_mover: return True
    if "YESTERDAY" in mover_label and "LOSER" in mover_label and alt_side=="BUY": return True
    if "YESTERDAY" in mover_label and "GAINER" in mover_label and alt_side=="SELL": return True
    if alt_side=="BUY" and btc_dir=="BEARISH": return False
    if alt_side=="SELL" and btc_dir=="BULLISH": return False
    return True

def check_active_positions_v206():
    for sym in list(ACTIVE.keys()):
        try:
            info=ACTIVE[sym]
            if not isinstance(info, dict): continue
            entry=float(info.get("entry",0)); side=info.get("side","BUY"); sl=float(info.get("sl",0)); tp1=float(info.get("tp1",0)); tp2=float(info.get("tp2",0)); tp3=float(info.get("tp3",0)); live=get_live(sym)
            if not live: continue
            d1=kl(sym,"Day1",min_candles=10); daily_bias,_ = get_daily_bias(d1) if d1 else ("RANGE","")
            flip=False
            if side=="BUY" and daily_bias=="BEARISH": flip=True
            if side=="SELL" and daily_bias=="BULLISH": flip=True
            if side=="BUY" and live>=tp1 and not info.get("tp1_hit"):
                info["tp1_hit"]=True; info["sl"]=entry; save_a(); print(f"{GREEN}TP1 HIT {sym} {side} @ {fmt(live)} - SL moved to entry{RESET}"); tg(f"✅ <b>TP1 HIT {sym} {side}</b> @ {fmt(live)}\nSL moved to entry {fmt(entry)}")
            if side=="SELL" and live<=tp1 and not info.get("tp1_hit"):
                info["tp1_hit"]=True; info["sl"]=entry; save_a(); print(f"{GREEN}TP1 HIT {sym} {side} @ {fmt(live)} - SL moved to entry{RESET}"); tg(f"✅ <b>TP1 HIT {sym} {side}</b> @ {fmt(live)}\nSL moved to entry {fmt(entry)}")
            if side=="BUY" and live>=tp2 and not info.get("tp2_hit"):
                info["tp2_hit"]=True; save_a(); tg(f"✅ <b>TP2 HIT {sym} {side}</b> @ {fmt(live)}")
            if side=="SELL" and live<=tp2 and not info.get("tp2_hit"):
                info["tp2_hit"]=True; save_a(); tg(f"✅ <b>TP2 HIT {sym} {side}</b> @ {fmt(live)}")
            sl=float(info.get("sl",sl))
            sl_hit = (live <= sl) if side=="BUY" else (live >= sl)
            if flip or sl_hit:
                reason = "DAILY FLIP EXIT" if flip else "SL HIT EXIT"; pnl=(live-entry)/entry*100 if side=="BUY" else (entry-live)/entry*100
                print(f"{RED}EXIT {sym} {reason} PnL {pnl:.2f}%{RESET}"); tg(format_exit_msg(sym, side, live, reason, pnl, entry, sl)); del ACTIVE[sym]; save_a()
        except Exception as e: print(f"exit check err {sym} {e}")

def run_once():
    print(f"{CYAN}[{get_time()}] | {TAG} | Daily Bias / 4H Sweep+BOS / 5M SS + OB + DYNAMIC 30% MOVERS{RESET}"); print("-"*100)
    btc_d1=kl("BTC_USDT","Day1"); btc_daily, btc_reason = get_daily_bias(btc_d1) if btc_d1 else ("RANGE","no btc daily")
    print(f"{CYAN}BTC Daily = {btc_daily} | {btc_reason}{RESET}")
    check_active_positions_v206()
    yesterday_movers = get_yesterday_movers(); today_movers = get_mexc_movers()
    movers = {}; movers.update(today_movers)
    for sym,label in yesterday_movers.items():
        if sym in movers: movers[sym]=movers[sym]+f" + {label}"
        else: movers[sym]=label
    print(f"MOVERS COMBINED: {movers}")
    SYMBOLS = list(movers.keys())
    if "BTC_USDT" not in SYMBOLS:
        SYMBOLS = ["BTC_USDT"] + SYMBOLS
    print(f"{CYAN}Scanning DYNAMIC {len(SYMBOLS)} coins: {SYMBOLS}{RESET}")
    signals=[]
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE:
                print(f"{YELLOW}SKIP {sym} - already ACTIVE {ACTIVE[sym].get('side')} @ {fmt(ACTIVE[sym].get('entry',0))}{RESET}"); continue
            live=get_live(sym)
            if not live: continue
            is_mover = sym in movers; mover_label = movers.get(sym,"")
            sig, debug = v400_signal(sym, live, is_mover=is_mover, mover_label=mover_label, btc_daily=btc_daily)
            if sig:
                color = GREEN if sig["side"]=="BUY" else RED; emoji = "🟢 BUY" if sig["side"]=="BUY" else "🔴 SELL"
                print(f"{color}{BOLD}{emoji} {sym} @ {fmt(sig['entry'])} | SL {fmt(sig['sl'])} | TP1 {fmt(sig['tp1'])} | TP2 {fmt(sig['tp2'])} | TP3 {fmt(sig['tp3'])} | BTC Daily {btc_daily} OK | {debug}{RESET}")
                tg(format_signal_msg(sig, sym)); signals.append(sym); ACTIVE[sym]={"side":sig["side"],"entry":sig["entry"],"sl":sig["sl"],"tp1":sig["tp1"],"tp2":sig["tp2"],"tp3":sig["tp3"],"time":get_time()}; save_a()
            else: print(f"{YELLOW}{sym} live={fmt(live)} | {debug}{RESET}")
        except Exception as e: print(f"{sym} err {e}")
    print(f"DONE {len(signals)} signals: {signals}")
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--once",action="store_true"); a=ap.parse_args(); run_once()
