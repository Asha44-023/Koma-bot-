import json,os,sys,time,tempfile,requests,csv
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT","LAB_USDT","VELVET_USDT"]
BETA_MAP={"BTC_USDT":1.0,"GRASS_USDT":2.5,"KOMA_USDT":2.2,"SENT_USDT":2.2,"SIREN_USDT":2.4,"PEPE_USDT":1.9,"LAB_USDT":2.1,"VELVET_USDT":2.6}
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE,JOURNAL_FILE="active.json","cooldown.json","stats_v199.json","trade_journal.csv"
MAX_ACTIVE=6;TOP_N_PER_SCAN=3
session=requests.Session()
TAG="V200.7-ALIGNED-AFAR"
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
ACTIVE=load_json(ACTIVE_FILE,{});COOLDOWN=load_json(COOLDOWN_FILE,{});STATS=load_json(STATS_FILE,{"closed":[],"open":{},"wins":0,"losses":0})
COOLDOWN.setdefault("daily_pnl",0.0);COOLDOWN.setdefault("last_day",get_today())
def save_a():atomic_save(ACTIVE_FILE,ACTIVE)
def save_c():atomic_save(COOLDOWN_FILE,COOLDOWN)
def save_s():atomic_save(STATS_FILE,STATS)
def fmt(p):
 try:
  p=float(p)
  if p<0.01:return f"{p:.8f}"
  if p<1:return f"{p:.6f}"
  return f"{p:.4f}"
 except:return "0"
def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15)
 except:pass
def journal_log(row):
 header=["date","time","coin","type","direction","score","checks","entry","sl","tp1","tp2","tp3","rr","btc_trend","reason","result","pnl","missing"]
 exists=os.path.exists(JOURNAL_FILE)
 try:
  with open(JOURNAL_FILE,"a",newline="") as f:
   w=csv.DictWriter(f,fieldnames=header)
   if not exists:w.writeheader()
   w.writerow(row)
 except Exception as e:print(f"JOURNAL EX {e}")
def kl(symbol,interval):
 sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400};sec=sec_map.get(interval,300);end=int(time.time());start=end-sec*500
 url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
 for _ in range(3):
  try:
   r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
   j=r.json();d=j.get("data",j)
   if isinstance(d,dict) and "data" in d:d=d["data"]
   if not d or "open" not in d:continue
   res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",d.get("volume",[0]*len(d["close"])))]}
   for k in res:res[k]=res[k][:-1]
   if len(res["c"])<50:continue
   return res
  except:time.sleep(1)
 return None
def get_live(s):
 for t in [s,s.replace("_",""),s.replace("_USDT","USDT")]:
  try:
   r=session.get(f"https://contract.mexc.com/api/v1/contract/ticker?symbol={t}",timeout=5).json()
   data=r.get("data",r);lp=data.get("lastPrice") or data.get("last_price") or data.get("price")
   if lp and float(lp)>0:return float(lp)
  except:pass
 return None
def calc_atr(d1,period=14):
    try:
        h=d1["h"];l=d1["l"];c=d1["c"];tr=[]
        for i in range(1,len(c)):tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
        if len(tr)<period: return sum(tr)/len(tr) if tr else c[-1]*0.03
        return sum(tr[-period:])/period
    except: return 0.0
def get_afar_levels(d1, lookback=90):
    try:
        if not d1 or len(d1["h"]) < lookback: lookback = len(d1["h"])-5
        h=d1["h"][-lookback:]; l=d1["l"][-lookback:]; c=d1["c"][-lookback:]
        highs=[]; lows=[]
        for i in range(3, len(h)-3):
            if h[i] > max(h[i-3:i]) and h[i] > max(h[i+1:i+4]):
                days_ago = len(h)-1 - i
                highs.append({"price": h[i], "days_ago": days_ago, "idx": i})
            if l[i] < min(l[i-3:i]) and l[i] < min(l[i+1:i+4]):
                days_ago = len(l)-1 - i
                lows.append({"price": l[i], "days_ago": days_ago, "idx": i})
        highs = sorted(highs, key=lambda x: x["days_ago"])[:4]
        lows = sorted(lows, key=lambda x: x["days_ago"])[:4]
        highs_recent = sorted(highs, key=lambda x: x["days_ago"], reverse=True)
        lows_recent = sorted(lows, key=lambda x: x["days_ago"], reverse=True)
        if len(highs) <2:
            mh = max(h); ml = min(l)
            return {"major_high": mh, "major_high_2": max(h[:-10]) if len(h)>10 else mh, "major_low": ml, "major_low_2": min(l[:-10]) if len(l)>10 else ml, "highs": highs, "lows": lows, "mid": (mh+ml)/2, "days_high": 0, "days_low": 0, "shape": "RANGE", "atr": calc_atr(d1), "hl_seq": ""}
        major_high = highs[0]["price"] if highs else max(h)
        major_high_2 = highs[1]["price"] if len(highs)>1 else major_high
        major_low = lows[0]["price"] if lows else min(l)
        major_low_2 = lows[1]["price"] if len(lows)>1 else major_low
        seq = ""
        try:
            if len(lows_recent)>=2:
                if lows_recent[1]["price"] < lows_recent[0]["price"]: seq += f"{lows_recent[0]['days_ago']}d HL → {lows_recent[1]['days_ago']}d HL "
                else: seq += f"LL → "
            if len(highs_recent)>=2:
                if highs_recent[1]["price"] < highs_recent[0]["price"]: seq += f"LH → "
                else: seq += f"HH → "
        except: seq="HL/HH"
        if len(highs_recent)>=2 and len(lows_recent)>=2:
            highs_desc = highs_recent[0]["price"] > highs_recent[1]["price"]
            lows_asc = lows_recent[0]["price"] < lows_recent[1]["price"]
            if highs_desc and lows_asc: shape = f"TRIANGLE COILING {len(h)}D"
            elif not highs_desc and lows_asc: shape = f"ASCENDING {len(h)}D"
            elif highs_desc and not lows_asc: shape = f"DESCENDING {len(h)}D"
            else: shape = f"RANGE {len(h)}D"
        else: shape = f"RANGE {len(h)}D"
        return {"major_high": major_high, "major_high_2": major_high_2, "major_low": major_low, "major_low_2": major_low_2, "highs": highs, "lows": lows, "mid": (major_high+major_low)/2, "days_high": highs[0]["days_ago"] if highs else 0, "days_low": lows[0]["days_ago"] if lows else 0, "shape": shape, "atr": calc_atr(d1), "hl_seq": seq}
    except Exception as e:
        print(f"AFAR EX {e}");return None
def calc_hold_days_dynamic(entry, target, atr):
    if atr==0 or atr is None: atr = abs(entry-target)/3.5 if target else entry*0.03
    dist = abs(target-entry); days = dist/atr if atr>0 else 3.5
    return max(0.5, min(days, 30))
def get_daily_levels(d1):
 y_high=float(d1["h"][-2]);y_low=float(d1["l"][-2]);y_mid=(y_high+y_low)/2.0;y_range=y_high-y_low
 return y_high,y_low,y_mid,y_range
def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1")
  if not d1 or len(d1["c"])<30:return "RANGE",0,77000,d1,None
  c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0
  month_change=(c[-1]-c[-22])/c[-22]*100 if c[-22]!=0 else 0
  btc_now=c[-1];afar = get_afar_levels(d1,90)
  if week_change<-3:return "WEEKLY_DUMP_ENDING",week_change,btc_now,d1,afar
  if week_change>3:return "WEEKLY_PUMP",week_change,btc_now,d1,afar
  if month_change<-10:return "MONTHLY_DUMP_ENDING",month_change,btc_now,d1,afar
  return "RANGE",week_change,btc_now,d1,afar
 except Exception as e:return "RANGE",0,77000,None,None
def detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar):
 try:
  if not d1 or len(d1["c"])<3:return False,"","","",0,0,0,"0/5",0,"no data"
  y_high,y_low,y_mid,y_range=get_daily_levels(d1)
  if y_range==0:return False,"","","",0,0,0,"0/5",0,"range 0"
  h15=d15["h"];l15=d15["l"];c15=d15["c"];o15=d15["o"]
  if len(c15)<6:return False,"","","",y_high,y_low,y_mid,"0/5",0,"few candles"
  last_h=max(h15[-5:]);last_l=min(l15[-5:]);last_c=c15[-1]
  body=abs(o15[-1]-c15[-1]) or 0.000001
  upper_wick=h15[-1]-max(o15[-1],c15[-1]);lower_wick=min(o15[-1],c15[-1])-l15[-1]
  sweep_up=last_h>y_high;sweep_down=last_l<y_low
  close_back_below=last_c<y_high;close_back_above=last_c>y_low
  wick_up=upper_wick>body*0.2;wick_down=lower_wick>body*0.2
  bos_bear=False;bos_bull=False
  if d15 and len(d15["c"])>10:
   if c15[-1]<min(d15["l"][-10:-5]):bos_bear=True
   if c15[-1]>max(d15["h"][-10:-5]):bos_bull=True
  is_hh_top = False
  if afar and afar["highs"]:
      last_pivot_high = afar["highs"][0]["price"]
      if live > last_pivot_high*0.99 and live < last_pivot_high*1.03:
          if c15[-1] < last_pivot_high*0.98:
              is_hh_top=False
          else:
              is_hh_top=True
  btc_ok_for_buy=True;btc_ok_for_sell=True
  if sweep_down and not is_hh_top:
   checks=0;missing=[]
   if sweep_down:checks+=1
   if close_back_above:checks+=1
   else:missing.append("no close_back")
   if wick_down:checks+=1
   else:missing.append("no wick")
   if bos_bull:checks+=1
   else:missing.append("no BOS")
   if btc_ok_for_buy:checks+=1
   else:missing.append("BTC DOWN")
   reason=f"FAKE LOW {fmt(last_l)} < YL {fmt(y_low)} {checks}/5 PHASE {btc_phase} BTC {fmt(btc_price)} AFAR {afar['shape'] if afar else ''}"
   return checks>=3,"BUY","SWEEP_FAKE",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  if sweep_up and not is_hh_top:
   checks=0;missing=[]
   if sweep_up:checks+=1
   if close_back_below:checks+=1
   else:missing.append("no close_back")
   if wick_up:checks+=1
   else:missing.append("no wick")
   if bos_bear:checks+=1
   else:missing.append("no BOS")
   if btc_ok_for_sell:checks+=1
   else:missing.append("BTC UP")
   reason=f"FAKE HIGH {fmt(last_h)} > YH {fmt(y_high)} {checks}/5 PHASE {btc_phase} BTC {fmt(btc_price)}"
   return checks>=3,"SELL","SWEEP_FAKE",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  two_below=c15[-1]<y_low and c15[-2]<y_low
  if two_below and live<y_low*1.002 and live>y_low*0.97 and not is_hh_top:
   checks=3;missing=[]
   if btc_trend=="DOWN" or btc_trend=="RANGE" or "DUMP_ENDING" in btc_phase:checks+=1
   else:missing.append("BTC not DOWN")
   if bos_bear:checks+=1
   else:missing.append("no BOS")
   reason=f"BREAKDOWN {fmt(y_low)} -> {fmt(live)} -3% {checks}/5 BTC {fmt(btc_price)} AFAR {afar['hl_seq'] if afar else ''}"
   return checks>=3,"SELL","BREAKDOWN",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  two_above=c15[-1]>y_high and c15[-2]>y_high
  if two_above and live>y_high*0.998 and live<y_high*1.03 and not is_hh_top:
   checks=3;missing=[]
   if btc_trend=="UP" or btc_trend=="RANGE" or "DUMP_ENDING" in btc_phase:checks+=1
   else:missing.append("BTC not UP")
   if bos_bull:checks+=1
   else:missing.append("no BOS")
   reason=f"BREAKOUT {fmt(y_high)} -> {fmt(live)} +3% {checks}/5 BTC {fmt(btc_price)} AFAR {afar['hl_seq'] if afar else ''} HL AFTER HH"
   return checks>=3,"BUY","BREAKOUT",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  if is_hh_top:
      return False,"","","",y_high,y_low,y_mid,f"WAIT HH WICK {afar['highs'][0]['price'] if afar and afar['highs'] else ''}",0,"HH wick - wait HL"
  return False,"","","",y_high,y_low,y_mid,"0/5",0,"no setup"
 except Exception as e:return False,"",f"ERR {e}","",0,0,0,"0/5",0,str(e)
def get_btc_trend():
 try:
  d=kl("BTC_USDT","Hour4")
  if not d:return "RANGE"
  c=d["c"]
  if c[-1]>c[-20]*1.015:return "UP"
  if c[-1]<c[-20]*0.985:return "DOWN"
  return "RANGE"
 except:return "RANGE"
def aligned_tp_calculation(sym, live, btc_live, btc_afar, afar, direction):
    beta = BETA_MAP.get(sym, 2.0)
    try:
        btc_mid = btc_afar["mid"] if btc_afar else btc_live*1.06
        btc_h2 = btc_afar["major_high_2"] if btc_afar else btc_live*1.10
        btc_h1 = btc_afar["major_high"] if btc_afar else btc_live*1.15
        btc_range = btc_h1 - btc_afar["major_low"] if btc_afar and btc_afar["major_low"]>0 else btc_live*0.15
        btc_tp3 = btc_h1 + btc_range*0.6
        if direction=="BUY":
            btc_pct1 = (btc_mid - btc_live)/btc_live if btc_live>0 else 0.06
            btc_pct2 = (btc_h1 - btc_live)/btc_live if btc_live>0 else 0.10
            btc_pct3 = (btc_tp3 - btc_live)/btc_live if btc_live>0 else 0.15
            tp1 = live * (1 + btc_pct1 * beta)
            tp2 = live * (1 + btc_pct2 * beta)
            tp3 = live * (1 + btc_pct3 * beta)
            if afar and afar["major_high_2"]>0:
                tp1 = min(tp1, afar["major_high_2"]*1.05)
            if afar and afar["major_high"]>0:
                tp2 = min(tp2, afar["major_high"]*1.10) if sym!="GRASS_USDT" else min(tp2, 0.90)
                if sym=="GRASS_USDT" and tp2 < 0.80:
                    tp2 = 0.80
            tp3 = max(tp3, tp2*1.15)
            return tp1, tp1*1.06, tp2, tp2*1.08, tp3
        else:
            btc_pct1 = (btc_live - btc_mid)/btc_live if btc_live>0 else 0.06
            tp1 = live * (1 - btc_pct1 * beta)
            tp2 = live * (1 - btc_pct1*1.6 * beta)
            tp3 = live * (1 - btc_pct1*2.2 * beta)
            return tp1, tp1*0.98, tp2, tp2*0.95, tp3
    except:
        if direction=="BUY":
            tp1=afar["mid"];tp2=afar["major_high"];tp3=afar["major_high"]+(afar["major_high"]-afar["major_low"])*0.6
            return tp1,tp1*1.02,tp2,tp2*1.05,tp3
        else:
            tp1=afar["mid"];tp2=afar["major_low"];tp3=afar["major_low"]-(afar["major_high"]-afar["major_low"])*0.6
            return tp1,tp1*0.98,tp2,tp2*0.95,tp3
def scan():
 today=get_today()
 if COOLDOWN.get("last_day")!=today:COOLDOWN["daily_pnl"]=0.0;COOLDOWN["last_day"]=today;save_c()
 btc_trend=get_btc_trend();btc_phase,btc_week_pct,btc_price,btc_d1,btc_afar=get_weekly_phase()
 print(f"\n--- {TAG} {get_time()} BTC:{btc_trend} {btc_phase} {btc_week_pct:.1f}% {fmt(btc_price)} AFAR:{btc_afar['shape'] if btc_afar else 'N/A'} ---")
 BTC_FAKE_LOW=74000
 btc_allows_longs = btc_price > BTC_FAKE_LOW
 if not btc_allows_longs:print(f"⚠️ BTC {fmt(btc_price)} < AFAR LOW {BTC_FAKE_LOW} -> BLOCKING ALL ALT LONGS - OVERALL SELL")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
  tp1_body=data.get("tp1_body", data.get("tp1",0));tp1_wick=data.get("tp1_wick", tp1_body*1.06)
  tp2_body=data.get("tp2_body", data.get("tp2",0));tp2_wick=data.get("tp2_wick", tp2_body*1.06)
  tp3=data.get("tp3",0);afar_info=data.get("afar",{});atr=data.get("atr", entry*0.03)
  days_held = (time.time() - data["ts"])/86400
  d_tp1 = calc_hold_days_dynamic(entry,tp1_body,atr)
  d_flip = calc_hold_days_dynamic(tp1_body, data.get('rebuy',0), atr)
  if (is_buy and p<=sl) or (not is_buy and p>=sl):
   pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100;STATS["losses"]+=1;save_s()
   tg(f"❌ {sym.replace('_USDT','USDT')} SL {pnl:.1f}% DAYS {days_held:.1f}/{d_tp1:.1f} AFAR {afar_info.get('shape','')} BETA {BETA_MAP.get(sym,2.0)}x");ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_body_hit") and ((is_buy and p>=tp1_body) or (not is_buy and p<=tp1_body)):
   data["tp1_body_hit"]=True;data["sl"]=entry;save_a()
   if is_buy:
       tg(f"🔴 SELL TO HERE: {sym.replace('_USDT','USDT')} TP1 BODY HIT {fmt(p)} Day {days_held:.1f}/{d_tp1:.1f}\n🟢 BUY TO HERE was {fmt(entry)} -> NOW SELL\nACTION: SELL 70% LONG + FLIP TO SHORT 30% at {fmt(tp1_body)}\n🔴 SELL FROM {fmt(tp1_body)} DOWN TO {fmt(data.get('rebuy',0))} IN ~{d_flip:.1f} DAYS\nFLIP TO: SHORT -> RE-BUY AT {fmt(data.get('rebuy',0))}\nNext SELL: TP1 WICK {fmt(tp1_wick)}\nBTC {fmt(btc_price)} {btc_afar['shape'] if btc_afar else ''}")
   else:
       tg(f"🟢 BUY TO HERE: {sym.replace('_USDT','USDT')} TP1 BODY HIT {fmt(p)}")
  if not data.get("tp1_wick_hit") and ((is_buy and p>=tp1_wick) or (not is_buy and p<=tp1_wick)):
   data["tp1_wick_hit"]=True;data["sl"]=tp1_body;save_a()
   if is_buy:
       tg(f"🔥 {sym.replace('_USDT','USDT')} TP1 WICK SURPASS {fmt(p)} BETA {BETA_MAP.get(sym,2.0)}x\n🔴 SELL TO HERE: CLOSE 30% RUNNER + FULL FLIP TO SHORT -> TARGET RE-BUY {fmt(data.get('rebuy',0))} DOWN FROM {fmt(tp1_wick)} IN ~{d_flip:.1f} DAYS")
  if not data.get("tp2_body_hit") and ((is_buy and p>=tp2_body) or (not is_buy and p<=tp2_body)):
   data["tp2_body_hit"]=True;data["sl"]=tp1_body;save_a()
   d_tp2 = calc_hold_days_dynamic(entry,tp2_body,atr)
   tg(f"🟢 HOLD TO BREAKOUT: {sym.replace('_USDT','USDT')} TP2 BODY HIT {fmt(p)} Day {days_held:.1f}/{d_tp2:.1f} BETA {BETA_MAP.get(sym,2.0)}x")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
   data["tp3_hit"]=True;data["sl"]=tp2_body;save_a()
   d_tp3 = calc_hold_days_dynamic(entry,tp3,atr)
   tg(f"✅ {sym.replace('_USDT','USDT')} TP3 AFAR MONTHLY WIN {fmt(p)} Day {days_held:.1f}/{d_tp3:.1f} BETA {BETA_MAP.get(sym,2.0)}x")
 if len(ACTIVE)>=MAX_ACTIVE:print(f"MAX ACTIVE {len(ACTIVE)}");return
 cands=[]
 for sym in SYMBOLS:
  try:
   if sym in ACTIVE:continue
   d1=kl(sym,"Day1");time.sleep(0.2);d15=kl(sym,"Min15");time.sleep(0.2);d5=kl(sym,"Min5");time.sleep(0.2)
   if not d1 or not d15:continue
   live=get_live(sym)
   if not live:continue
   afar = get_afar_levels(d1,90)
   if not afar:continue
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar)
   if not ok:
    if checks_str!="0/5":print(f"⚪ WAIT {sym} {checks_str} {missing} | {reason}")
    continue
   if direction=="BUY" and sym!="BTC_USDT" and not btc_allows_longs:
       print(f"🚫 SKIP {sym} BUY blocked by BTC AFAR {fmt(btc_price)} < {BTC_FAKE_LOW}")
       continue
   atr = afar["atr"]
   if direction=="BUY":
    sl_raw=afar["major_low"]*0.95 if afar["major_low"]>0 else min(d15["l"][-10:])*0.97
    sl = sl_raw if sl_raw < live*0.99 else live*0.97
    if sl >= live: sl = live*0.97
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3 = aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "BUY")
    rebuy_low=afar["major_low_2"] if afar["major_low_2"]>0 else afar["major_low"]
    if rebuy_low >= tp1_body: rebuy_low = afar["major_low"]
   else:
    sl_raw=afar["major_high"]*1.05 if afar["major_high"]>0 else max(d15["h"][-10:])*1.03
    sl = sl_raw if sl_raw > live*1.01 else live*1.03
    if sl <= live: sl = live*1.03
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3 = aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "SELL")
    rebuy_low=afar["major_high_2"]
   risk=abs(live-sl)/live*100
   if risk>20:print(f"⚪ {sym} SL afar wide {risk:.1f}% skip");continue
   if risk<0.5:print(f"⚪ {sym} SL too tight {risk:.1f}% skip");continue
   reward=abs(tp1_body-live)/live*100;rr=reward/risk if risk>0 else 0
   d1_hold=calc_hold_days_dynamic(live,tp1_body,atr);d2_hold=calc_hold_days_dynamic(live,tp2_body,atr);d3_hold=calc_hold_days_dynamic(live,tp3,atr);d_flip=calc_hold_days_dynamic(tp1_body,rebuy_low,atr)
   beta = BETA_MAP.get(sym,2.0)
   print(f"{'🟢' if direction=='BUY' else '🔴'} {direction} {sym} @ {fmt(live)} BETA {beta}x AFAR {afar['shape']} H {fmt(afar['major_high'])}({afar['days_high']}d) L {fmt(afar['major_low'])}({afar['days_low']}d) SL {fmt(sl)} TP1 {fmt(tp1_body)} TP2 {fmt(tp2_body)} TP3 {fmt(tp3)} RR {rr:.1f}")
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar["major_high"],afar["major_low"],afar["major_high"],afar["major_low"],reason,checks_str,afar["major_high_2"],afar["major_low_2"],afar,atr,rebuy_low,d1_hold,d2_hold,d3_hold,d_flip,beta))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,w_high,w_low,m_high,m_low,reason,checks_str,w_body_high,w_body_low,afar,atr,rebuy_low,d1_hold,d2_hold,d3_hold,d_flip,beta in cands:
  is_buy=dir=="BUY";now_ts=time.time()
  def add_days(d): return datetime.fromtimestamp(now_ts, EAT) + timedelta(days=d)
  ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1_body,"tp1_body":tp1_body,"tp1_wick":tp1_wick,"tp2":tp2_body,"tp2_body":tp2_body,"tp2_wick":tp2_wick,"tp3":tp3,"is_buy":is_buy,"label":TAG,"type":sig_type,"score":score,"rr":rr,"checks":checks_str,"reason":reason,"ts":now_ts,"runner_days":0,"rebuy":rebuy_low,"afar":afar,"atr":atr,"d1_hold":d1_hold,"d2_hold":d2_hold,"d3_hold":d3_hold,"d_flip":d_flip,"beta":beta};save_a()
  journal_log({"date":today,"time":get_time(),"coin":sym,"type":sig_type,"direction":dir,"score":score,"checks":checks_str,"entry":live,"sl":sl,"tp1":tp1_body,"tp2":tp2_body,"tp3":tp3,"rr":f"{rr:.1f}","btc_trend":f"{btc_trend}/{btc_phase} {fmt(btc_price)} AFAR {afar['shape']} {afar['hl_seq']} BETA {beta}x","reason":reason,"result":"OPEN","pnl":"","missing":""})
  if is_buy:
      btc_lead = f"BTC AFAR {btc_afar['shape']} {btc_afar['hl_seq']} {fmt(btc_afar['major_low'])}->{fmt(btc_price)} BETA {beta}x" if btc_afar else f"BETA {beta}x"
      tg(
          f"🟢 BUY {sym.replace('_USDT','USDT')} | {TAG}\n"
          f"{reason}\n"
          f"🔭 AFAR {afar['shape']} | H {fmt(afar['major_high'])} {afar['days_high']}d ago Body {fmt(afar['major_high_2'])} | L {fmt(afar['major_low'])} {afar['days_low']}d ago Body {fmt(afar['major_low_2'])} | ATR {fmt(atr)} | SEQ {afar['hl_seq']} | BETA {beta}x BTC\n"
          f"{btc_lead}\n"
          f"\n"
          f"🟢 BUY FROM HERE:\n"
          f"BUY AT {fmt(live)} | SL {fmt(sl)} (AFAR Low {afar['days_low']}d)\n"
          f"HOLD {d1_hold:.1f} DAYS TO {fmt(tp1_body)} ~ {add_days(d1_hold).strftime('%b %d')} (BTC {fmt(btc_afar['mid']) if btc_afar else ''})\n"
          f"\n"
          f"🔴 SELL FROM HERE TO HERE:\n"
          f"SELL FROM {fmt(tp1_body)} DOWN TO {fmt(rebuy_low)}\n"
          f"→ SELL 70% AT {fmt(tp1_body)} = PROFIT\n"
          f"→ FLIP TO SHORT 30% AT {fmt(tp1_body)}\n"
          f"→ COVER SHORT + RE-BUY LONG AT {fmt(rebuy_low)} IN ~{d_flip:.1f} DAYS\n"
          f"\n"
          f"🔴 SECOND SELL FROM HERE TO HERE:\n"
          f"SELL FROM {fmt(tp1_body)} UP TO {fmt(tp2_body)} (AFAR Major High {afar['days_high']}d ago) WICK {fmt(tp2_wick)} = GRASS 0.9 CHART TOP\n"
          f"→ SELL 30% RUNNER AT {fmt(tp2_body)} ~ {add_days(d2_hold).strftime('%b %d')} Day {d2_hold:.1f}\n"
          f"→ FULL FLIP TO SHORT AT {fmt(tp2_body)} DOWN TO {fmt(rebuy_low)} ~{calc_hold_days_dynamic(tp2_body,rebuy_low,atr):.1f} DAYS\n"
          f"\n"
          f"🟢 HOLD LONG:\n"
          f"FROM {fmt(rebuy_low)} TO {fmt(tp3)} = BTC 109K BREAKOUT = GRASS 1.18 BREAKOUT PAST 0.9\n"
          f"→ HOLD TO {fmt(tp2_body)} ~ {add_days(d2_hold).strftime('%b %d')} Day {d2_hold:.1f}\n"
          f"→ HOLD TO {fmt(tp3)} BREAKOUT ~ {add_days(d3_hold).strftime('%b %d')} Day {d3_hold:.1f} STOP FLIPPING\n"
          f"→ IF {fmt(rebuy_low)} BREAKS = LH AFTER HH = FINAL PEAK REVERSAL = OVERALL SELL\n"
          f"\n"
          f"RR {rr:.1f} BTC {fmt(btc_price)} BETA {beta}x"
      )
  else:
      tg(f"🔴 SELL {sym.replace('_USDT','USDT')} | {TAG}\n{reason}\n🔭 AFAR {afar['shape']} BETA {beta}x\nRR {rr:.1f} BTC {fmt(btc_price)}")
if __name__=="__main__":
 if "--once" in sys.argv:scan()
 else:
  while True:
   try:scan()
   except Exception as e:print(f"EX {e}")
   time.sleep(900)
