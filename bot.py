import json,os,time,tempfile,requests,argparse
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","JASMY_USDT","LAB_USDT","VELVET_USDT","PEPE_USDT","DOGE_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json"
session=requests.Session()
TAG="V205-BTC-FILTER-4H-30M-5M"
GREEN="\033[92m"; RED="\033[91m"; YELLOW="\033[93m"; CYAN="\033[96m"; RESET="\033[0m"; BOLD="\033[1m"

def get_time():return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today():return datetime.now(EAT).strftime("%Y-%m-%d")
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
  return round(p*10000000)/10000000
 except:return p

def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m,"parse_mode":"HTML"},timeout=15)
 except:pass

def format_signal_msg(sig, sym):
    if sig["side"]=="BUY":
        return (f"🟢🟢🟢 <b>BUY {sym}</b> 🟢🟢🟢\n"
                f"Entry: <b>{fmt(sig['entry'])}</b>\n"
                f"🛑 SL: <b>{fmt(sig['sl'])}</b> ({((sig['sl']-sig['entry'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['tp1']-sig['entry'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['tp2']-sig['entry'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP3: <b>{fmt(sig['tp3'])}</b> ({((sig['tp3']-sig['entry'])/sig['entry']*100):+.2f}%)\n"
                f"{sig['reason']}\n[{get_time()}] | {TAG}")
    else:
        return (f"🔴🔴🔴 <b>SELL {sym}</b> 🔴🔴🔴\n"
                f"Entry: <b>{fmt(sig['entry'])}</b>\n"
                f"🛑 SL: <b>{fmt(sig['sl'])}</b>\n"
                f"🎯 TP1: <b>{fmt(sig['tp1'])}</b> ({((sig['entry']-sig['tp1'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP2: <b>{fmt(sig['tp2'])}</b> ({((sig['entry']-sig['tp2'])/sig['entry']*100):+.2f}%)\n"
                f"🎯 TP3: <b>{fmt(sig['tp3'])}</b> ({((sig['entry']-sig['tp3'])/sig['entry']*100):+.2f}%)\n"
                f"{sig['reason']}\n[{get_time()}] | {TAG}")

def format_exit_msg(sym, side, live, reason, pnl, entry, sl):
    emoji="🛑" if "SL" in reason else "⚠️"
    return (f"{emoji} <b>EXIT {sym} {side}</b>\n"
            f"Exit: <b>{fmt(live)}</b> | Entry: {fmt(entry)} | SL: {fmt(sl)}\n"
            f"Reason: {reason}\nPnL: <b>{pnl:+.2f}%</b>")

def kl(symbol,interval):
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
   if len(res["c"])<30:continue
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

def get_4h_direction(d4h):
    try:
        if not d4h or len(d4h["c"]) < 30: return "NEUTRAL", "no data"
        h=d4h["h"]; l=d4h["l"]; c=d4h["c"]
        highs=[]; lows=[]
        for i in range(3,len(h)-3):
            if h[i]==max(h[i-3:i+4]): highs.append(h[i])
            if l[i]==min(l[i-3:i+4]): lows.append(l[i])
        highs=highs[-3:]; lows=lows[-3:]
        if len(highs)<2 or len(lows)<2: return "NEUTRAL","not enough pivots"
        h1,h2=highs[-2],highs[-1]
        l1,l2=lows[-2],lows[-1]
        if abs(h2-h1)/h1 < 0.02 and abs(l2-l1)/l1 < 0.02:
            return "RANGE", f"Range H {fmt(h2)} L {fmt(l2)}"
        if h2>h1 and l2>l1:
            return "BULLISH", f"HH {fmt(h1)}->{fmt(h2)} HL {fmt(l1)}->{fmt(l2)}"
        if h2<h1 and l2<l1:
            return "BEARISH", f"LH {fmt(h1)}->{fmt(h2)} LL {fmt(l1)}->{fmt(l2)}"
        avg=sum(c[-20:])/20
        if c[-1] > avg*1.01: return "BULLISH", f"Price above avg {fmt(avg)}"
        if c[-1] < avg*0.99: return "BEARISH", f"Price below avg {fmt(avg)}"
        return "RANGE", f"Sideways H {fmt(h2)} L {fmt(l2)}"
    except Exception as e: return "NEUTRAL", f"err {e}"

def get_30m_zones(d30):
    try:
        if not d30 or len(d30["c"])<50: return None, None
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

def get_5m_trigger(d5, side):
    try:
        if not d5 or len(d5["c"])<20: return False, "no 5M data", 0, 0
        h=d5["h"]; l=d5["l"]; c=d5["c"]
        if side=="BUY":
            low1=min(l[-10:-5]); low2=min(l[-5:])
            if not (low2 > low1): return False, f"no HL {fmt(low1)}->{fmt(low2)}", 0, 0
            breakout = max(h[-6:-1])
            if c[-1] > breakout:
                sl = low2 * 0.997
                return True, f"HL {fmt(low1)}->{fmt(low2)} break {fmt(breakout)}", sl, breakout
            return False, f"HL ok, waiting break > {fmt(breakout)} live {fmt(c[-1])}", 0, 0
        if side=="SELL":
            high1=max(h[-10:-5]); high2=max(h[-5:])
            if not (high2 < high1): return False, f"no LH {fmt(high1)}->{fmt(high2)}", 0, 0
            breakdown = min(l[-6:-1])
            if c[-1] < breakdown:
                sl = high2 * 1.003
                return True, f"LH {fmt(high1)}->{fmt(high2)} break {fmt(breakdown)}", sl, breakdown
            return False, f"LH ok, waiting break < {fmt(breakdown)} live {fmt(c[-1])}", 0, 0
        return False, "no side", 0, 0
    except Exception as e: return False, f"5M err {e}", 0, 0

def v204_signal(sym, live):
    d4h=kl(sym,"Hour4"); d30=kl(sym,"Min30"); d5=kl(sym,"Min5")
    if not d4h or not d30 or not d5: return None, "missing TF data"
    direction, dir_reason = get_4h_direction(d4h)
    demand, supply = get_30m_zones(d30)
    atr = calc_atr(d30)
    if atr==0: atr=live*0.02
    in_demand=False; in_supply=False
    if demand and demand["low"]*0.995 <= live <= demand["high"]*1.005: in_demand=True
    if supply and supply["low"]*0.995 <= live <= supply["high"]*1.005: in_supply=True
    def fix_tp_buy(tp1_raw):
        if tp1_raw and tp1_raw > live + atr*0.5:
            return round_level(tp1_raw)
        return round_level(live + atr*2)
    def fix_tp_sell(tp1_raw):
        if tp1_raw and tp1_raw < live - atr*0.5:
            return round_level(tp1_raw)
        return round_level(live - atr*2)
    if direction=="RANGE":
        if in_demand:
            ok, msg, sl, trig = get_5m_trigger(d5,"BUY")
            if ok:
                tp1 = fix_tp_buy(supply["high"] if supply else 0)
                tp2 = round_level(live+atr*4); tp3 = round_level(tp2+atr*2)
                return {"side":"BUY","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":f"RANGE + Demand + {msg} | 4H {dir_reason}"}, f"RANGE BUY {msg}"
            return None, f"RANGE in Demand, waiting 5M: {msg}"
        if in_supply:
            ok, msg, sl, trig = get_5m_trigger(d5,"SELL")
            if ok:
                tp1 = fix_tp_sell(demand["low"] if demand else 0)
                tp2 = round_level(live-atr*4); tp3 = round_level(tp2-atr*2)
                return {"side":"SELL","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":f"RANGE + Supply + {msg} | 4H {dir_reason}"}, f"RANGE SELL {msg}"
            return None, f"RANGE in Supply, waiting 5M: {msg}"
        return None, f"RANGE {dir_reason} | not in zone live {fmt(live)}"
    if direction=="BULLISH":
        if not in_demand: return None, f"BULLISH {dir_reason} | not in Demand live {fmt(live)}"
        ok, msg, sl, trig = get_5m_trigger(d5,"BUY")
        if not ok: return None, f"BULLISH in Demand, waiting 5M: {msg}"
        tp1 = fix_tp_buy(supply["high"] if supply else 0)
        tp2 = round_level(live+atr*4); tp3 = round_level(tp2+atr*2)
        return {"side":"BUY","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":f"BULLISH + Demand + {msg} | 4H {dir_reason}"}, f"BULLISH BUY {msg}"
    if direction=="BEARISH":
        if not in_supply: return None, f"BEARISH {dir_reason} | not in Supply live {fmt(live)}"
        ok, msg, sl, trig = get_5m_trigger(d5,"SELL")
        if not ok: return None, f"BEARISH in Supply, waiting 5M: {msg}"
        tp1 = fix_tp_sell(demand["low"] if demand else 0)
        tp2 = round_level(live-atr*4); tp3 = round_level(tp2-atr*2)
        return {"side":"SELL","entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"reason":f"BEARISH + Supply + {msg} | 4H {dir_reason}"}, f"BEARISH SELL {msg}"
    return None, f"NEUTRAL {dir_reason} | no trade"

# ================= BTC FILTER - STANDARD =================
def btc_confirms(alt_side, btc_dir):
    # BTC trades alone, no filter
    # Alt BUY needs BTC BULLISH or RANGE - never BEARISH
    # Alt SELL needs BTC BEARISH or RANGE - never BULLISH
    if alt_side=="BUY" and btc_dir=="BEARISH": return False
    if alt_side=="SELL" and btc_dir=="BULLISH": return False
    return True

def check_active_positions_v204():
    for sym in list(ACTIVE.keys()):
        try:
            info=ACTIVE[sym]
            if not isinstance(info, dict): continue
            entry=float(info.get("entry",0)); side=info.get("side","BUY"); sl=float(info.get("sl",0))
            tp1=float(info.get("tp1",0))
            live=get_live(sym)
            if not live: continue
            d4h=kl(sym,"Hour4")
            direction,_ = get_4h_direction(d4h)
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
    print(f"{CYAN}[{get_time()}] | {TAG} | 4H / 30M / 5M + BTC FILTER{RESET}")
    print("-"*100)
    # Get BTC direction ONCE for filter
    btc_d4h=kl("BTC_USDT","Hour4")
    btc_dir, btc_reason = get_4h_direction(btc_d4h)
    print(f"{CYAN}BTC 4H = {btc_dir} | {btc_reason}{RESET}")
    check_active_positions_v204()
    signals=[]
    for sym in SYMBOLS:
        try:
            live=get_live(sym)
            if not live: continue
            sig, debug = v204_signal(sym, live)
            d4h=kl(sym,"Hour4")
            direction, dir_reason = get_4h_direction(d4h)
            if sig:
                # === BTC FILTER APPLIED HERE ===
                if sym != "BTC_USDT":
                    if not btc_confirms(sig["side"], btc_dir):
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
