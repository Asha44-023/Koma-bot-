import json,os,sys,time,tempfile,requests,csv
from datetime import datetime, timedelta
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT","LAB_USDT","VELVET_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE,JOURNAL_FILE="active.json","cooldown.json","stats_v199.json","trade_journal.csv"
MAX_ACTIVE=6;TOP_N_PER_SCAN=2
session=requests.Session()
TAG="V200.7-BREAKDOWN"
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
def get_daily_levels(d1):
 y_high=float(d1["h"][-2]);y_low=float(d1["l"][-2]);y_mid=(y_high+y_low)/2.0;y_range=y_high-y_low
 return y_high,y_low,y_mid,y_range
def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1")
  if not d1 or len(d1["c"])<30:return "RANGE",0,77000,d1
  c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0
  month_change=(c[-1]-c[-22])/c[-22]*100 if c[-22]!=0 else 0
  btc_now=c[-1]
  if week_change<-3:return "WEEKLY_DUMP_ENDING",week_change,btc_now,d1
  if week_change>3:return "WEEKLY_PUMP",week_change,btc_now,d1
  if month_change<-10:return "MONTHLY_DUMP_ENDING",month_change,btc_now,d1
  return "RANGE",week_change,btc_now,d1
 except Exception as e:return "RANGE",0,77000,None
def get_coin_cycle_levels(d1):
 try:
  if not d1 or len(d1["c"])<35:return None
  wd = datetime.now(EAT).weekday()
  days_to_last_sunday = wd + 1
  end = -days_to_last_sunday
  start = end - 7
  if abs(start) > len(d1["h"]):
      w_high=max(d1["h"][-7:]);w_low=min(d1["l"][-7:])
      w_close=d1["c"][-7:];w_open=d1["o"][-7:]
  else:
      w_high=max(d1["h"][start:end]) if end !=0 else max(d1["h"][start:])
      w_low=min(d1["l"][start:end]) if end !=0 else min(d1["l"][start:])
      w_close=d1["c"][start:end] if end !=0 else d1["c"][start:]
      w_open=d1["o"][start:end] if end !=0 else d1["o"][start:]
  w_body_high = max(w_close[-1], w_open[-1]) if w_close else w_high
  w_body_low = min(w_close[-1], w_open[-1]) if w_close else w_low
  m_high=max(d1["h"][-30:]);m_low=min(d1["l"][-30:]);w_mid=(w_high+w_low)/2;m_mid=(m_high+m_low)/2
  return w_high,w_low,w_body_high,w_body_low,m_high,m_low,w_mid,m_mid
 except:return None
def calc_hold_days(entry_ts):
    return {
        "tp1_body": datetime.fromtimestamp(entry_ts, EAT) + timedelta(days=3.5),
        "tp1_wick": datetime.fromtimestamp(entry_ts, EAT) + timedelta(days=4.5),
        "tp2_body": datetime.fromtimestamp(entry_ts, EAT) + timedelta(days=8),
        "tp2_wick": datetime.fromtimestamp(entry_ts, EAT) + timedelta(days=9.5),
        "breakout": datetime.fromtimestamp(entry_ts, EAT) + timedelta(days=11)
    }
def detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price):
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
  btc_ok_for_buy=True;btc_ok_for_sell=True
  if sweep_down:
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
   reason=f"FAKE LOW {fmt(last_l)} < YL {fmt(y_low)} {checks}/5 PHASE {btc_phase} BTC {fmt(btc_price)}"
   return checks>=3,"BUY","SWEEP_FAKE",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  if sweep_up:
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
  if two_below and live<y_low*1.002 and live>y_low*0.97:
   checks=3;missing=[]
   if btc_trend=="DOWN" or btc_trend=="RANGE" or "DUMP_ENDING" in btc_phase:checks+=1
   else:missing.append("BTC not DOWN")
   if bos_bear:checks+=1
   else:missing.append("no BOS")
   reason=f"BREAKDOWN {fmt(y_low)} -> {fmt(live)} -3% {checks}/5 BTC {fmt(btc_price)}"
   return checks>=3,"SELL","BREAKDOWN",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  two_above=c15[-1]>y_high and c15[-2]>y_high
  if two_above and live>y_high*0.998 and live<y_high*1.03:
   checks=3;missing=[]
   if btc_trend=="UP" or btc_trend=="RANGE" or "DUMP_ENDING" in btc_phase:checks+=1
   else:missing.append("BTC not UP")
   if bos_bull:checks+=1
   else:missing.append("no BOS")
   reason=f"BREAKOUT {fmt(y_high)} -> {fmt(live)} +3% {checks}/5 BTC {fmt(btc_price)}"
   return checks>=3,"BUY","BREAKOUT",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
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
def scan():
 today=get_today()
 if COOLDOWN.get("last_day")!=today:COOLDOWN["daily_pnl"]=0.0;COOLDOWN["last_day"]=today;save_c()
 btc_trend=get_btc_trend();btc_phase,btc_week_pct,btc_price,btc_d1=get_weekly_phase()
 print(f"\n--- {TAG} {get_time()} BTC:{btc_trend} {btc_phase} {btc_week_pct:.1f}% {fmt(btc_price)} ---")
 BTC_FAKE_LOW=76000
 btc_allows_longs = btc_price > BTC_FAKE_LOW
 if not btc_allows_longs:
     print(f"⚠️ BTC {fmt(btc_price)} < FAKE LOW {BTC_FAKE_LOW} -> BLOCKING ALL ALT LONGS")
 try:
  if btc_d1 and len(btc_d1["c"])>30:
      m_high_btc=max(btc_d1["h"][-30:]);m_low_btc=min(btc_d1["l"][-30:])
      dist_to_month_high = (m_high_btc - btc_price)/m_high_btc*100
      if btc_phase=="WEEKLY_PUMP" and dist_to_month_high < 3.0 and btc_price > 100000:
          if COOLDOWN.get("crash_alert_day")!=today:
              COOLDOWN["crash_alert_day"]=today;save_c()
              tg(f"⚠️⚠️ CRASH ALERT - MONTHLY TOP POSSIBLE ⚠️⚠️\nBTC {fmt(btc_price)} is {dist_to_month_high:.1f}% below MONTHLY HIGH {fmt(m_high_btc)}\nPHASE: {btc_phase} +{btc_week_pct:.1f}%\n\nThis is NOT flip anymore.\nMarket wants to crash in next 7-14 days.\nACTION:\n- STOP opening new LONGS\n- Close 80% of all runners\n- Prepare to FLIP TO SHORT FOR WEEKS\n- Target BTC back to {fmt(m_low_btc*1.1)} (monthly low)\n\nThis alert replaces FLIP logic. Hold SHORT till fake low forms again.")
      if btc_price > 88000 and btc_phase in ["WEEKLY_PUMP","RANGE"] and "DUMP_ENDING" not in btc_phase:
          if btc_d1["h"][-1] > max(btc_d1["h"][-30:-1]):
              if COOLDOWN.get("breakout_alert_day")!=today:
                  COOLDOWN["breakout_alert_day"]=today;save_c()
                  tg(f"🚀 BREAKOUT CONFIRMED - STOP FLIPPING\nBTC {fmt(btc_price)} broke monthly high {fmt(m_high_btc)}\nFlip phase OVER. Now HOLD LONG FOR MONTHS.\nNo more SHORT flips till next fake high at 115K-120K.\nHold all alt longs to 2-3 months.")
 except Exception as e:print(f"CRASH CHECK EX {e}")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
  tp1_body=data.get("tp1_body", data.get("tp1",0));tp1_wick=data.get("tp1_wick", tp1_body*1.06)
  tp2_body=data.get("tp2_body", data.get("tp2",0));tp2_wick=data.get("tp2_wick", tp2_body*1.06)
  tp3=data.get("tp3",0)
  days_held = (time.time() - data["ts"])/86400
  if (is_buy and p<=sl) or (not is_buy and p>=sl):
   pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100;STATS["losses"]+=1;save_s()
   tg(f"❌ {sym.replace('_USDT','USDT')} SL {pnl:.1f}% DAYS {days_held:.1f}");ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_body_hit") and ((is_buy and p>=tp1_body) or (not is_buy and p<=tp1_body)):
   data["tp1_body_hit"]=True;data["sl"]=entry;save_a()
   if is_buy:
       tg(f"🔴 SELL TO HERE: {sym.replace('_USDT','USDT')} TP1 BODY HIT {fmt(p)} Day {days_held:.1f}/3.5\n🟢 BUY TO HERE was {fmt(entry)} -> NOW SELL\nACTION: SELL 70% LONG + FLIP TO SHORT 30% at {fmt(tp1_body)}\n🔴 SELL FROM {fmt(tp1_body)} DOWN TO {fmt(data.get('rebuy',0))} IN 2 DAYS\nFLIP TO: SHORT -> RE-BUY AT {fmt(data.get('rebuy',0))}\nNext SELL: TP1 WICK {fmt(tp1_wick)} in ~1 day\nBTC {fmt(btc_price)}")
   else:
       tg(f"🟢 BUY TO HERE: {sym.replace('_USDT','USDT')} TP1 BODY HIT {fmt(p)} Day {days_held:.1f}/3.5\n🔴 SELL TO HERE was {fmt(entry)}\nACTION: BUY 70% SHORT + FLIP TO LONG 30% at {fmt(tp1_body)}\n🟢 BUY FROM {fmt(tp1_body)} UP TO {fmt(data.get('rebuy',0))}\nFLIP TO: LONG\nNext: TP1 WICK {fmt(tp1_wick)}\nBTC {fmt(btc_price)}")
  if not data.get("tp1_wick_hit") and ((is_buy and p>=tp1_wick) or (not is_buy and p<=tp1_wick)):
   data["tp1_wick_hit"]=True;data["sl"]=tp1_body;save_a()
   if is_buy:
       tg(f"🔥 {sym.replace('_USDT','USDT')} TP1 WICK SURPASS {fmt(p)} +6% over body\n🔴 SELL TO HERE: CLOSE 30% RUNNER + FULL FLIP TO SHORT -> TARGET RE-BUY {fmt(data.get('rebuy',0))} DOWN FROM {fmt(tp1_wick)}\nFLIP TO: SHORT FOR 2 DAYS\nBTC phase {btc_phase} {fmt(btc_price)}")
   else:
       tg(f"🔥 {sym.replace('_USDT','USDT')} TP1 WICK SURPASS {fmt(p)}\n🟢 BUY TO HERE: CLOSE 30% RUNNER + FULL FLIP TO LONG -> TARGET {fmt(tp2_body)} UP FROM {fmt(tp1_wick)}\nFLIP TO: LONG\nBTC phase {btc_phase}")
  if not data.get("tp2_body_hit") and ((is_buy and p>=tp2_body) or (not is_buy and p<=tp2_body)):
   data["tp2_body_hit"]=True;data["sl"]=tp1_body;save_a()
   tg(f"🟢 HOLD TO BREAKOUT: {sym.replace('_USDT','USDT')} TP2 BODY HIT {fmt(p)} Day {days_held:.1f}/8\nACTION: SELL 50% + SL TO TP1\n🟢 HOLD FROM {fmt(tp2_body)} TO {fmt(tp3)} - FLIP PAUSES AFTER BREAKOUT")
  if not data.get("tp2_wick_hit") and ((is_buy and p>=tp2_wick) or (not is_buy and p<=tp2_wick)):
   data["tp2_wick_hit"]=True;save_a()
   tg(f"🔥 {sym.replace('_USDT','USDT')} TP2 WICK SURPASS {fmt(p)} - PREV WEEK WICK BROKEN\n🟢 HOLD FROM {fmt(tp2_body)} TO {fmt(tp3)} - CLOSE 80% + FLIP SHORT IF BTC REJECTS at {fmt(btc_price)} - ELSE HOLD TO TP3")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
   data["tp3_hit"]=True;data["sl"]=tp2_body;save_a()
   tg(f"✅ {sym.replace('_USDT','USDT')} TP3 MONTHLY WIN {fmt(p)} Day {days_held:.1f}/11 - STOP FLIPPING, HOLD RUNNER FOR MONTHS to 115K/BTC\n🔴 NO MORE SELL FLIPS till crash")
   if data.get("runner_days",0)>30:
    STATS["wins"]+=1;save_s();ACTIVE.pop(sym,None);save_a()
   continue
  if data.get("tp2_body_hit"): data["runner_days"]=data.get("runner_days",0)+0.25;save_a()
 if len(ACTIVE)>=MAX_ACTIVE:print(f"MAX ACTIVE {len(ACTIVE)}");return
 cands=[]
 for sym in SYMBOLS:
  try:
   if sym in ACTIVE:continue
   d1=kl(sym,"Day1");time.sleep(0.2);d15=kl(sym,"Min15");time.sleep(0.2);d5=kl(sym,"Min5");time.sleep(0.2)
   if not d1 or not d15:continue
   live=get_live(sym)
   if not live:continue
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price)
   if not ok:
    if checks_str!="0/5":print(f"⚪ WAIT {sym} {checks_str} {missing} | {reason}")
    continue
   if direction=="BUY" and not btc_allows_longs:
       print(f"🚫 SKIP {sym} BUY blocked by BTC {fmt(btc_price)} < 76K")
       continue
   cycle=get_coin_cycle_levels(d1)
   if not cycle:continue
   w_high,w_low,w_body_high,w_body_low,m_high,m_low,w_mid,m_mid=cycle
   if direction=="BUY":
    sl=m_low*0.95 if m_low>0 else min(d15["l"][-10:])*0.97
    tp1_body=w_body_high if w_body_high>0 else w_mid
    tp1_wick=w_high*1.02
    tp2_body=m_mid
    tp2_wick=w_high*1.06 if w_high>0 else m_high*0.95
    tp3=m_high*0.90
    emoji="🟢";color_code="\033[92m"
   else:
    sl=m_high*1.05 if m_high>0 else max(d15["h"][-10:])*1.03
    tp1_body=w_body_low if w_body_low>0 else w_mid
    tp1_wick=w_low*0.98
    tp2_body=m_mid
    tp2_wick=w_low*0.94
    tp3=m_low*1.10 if m_low>0 else w_low*0.90
    emoji="🔴";color_code="\033[91m"
   risk=abs(live-sl)/live*100
   if risk>15:print(f"{emoji} {sym} SL monthly wide {risk:.1f}% skip");continue
   reward=abs(tp1_body-live)/live*100;rr=reward/risk if risk>0 else 0
   print(f"{color_code}{emoji} {direction} {sym} @ {fmt(live)} W-H {fmt(w_high)} W-BODY {fmt(w_body_high)} L {fmt(w_low)} B-LOW {fmt(w_body_low)} M-H {fmt(m_high)} | SL {fmt(sl)} TP1-BODY {fmt(tp1_body)} WICK {fmt(tp1_wick)} TP2-BODY {fmt(tp2_body)} WICK {fmt(tp2_wick)} RR {rr:.1f}\033[0m")
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,w_high,w_low,m_high,m_low,reason,checks_str,w_body_high,w_body_low))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,w_high,w_low,m_high,m_low,reason,checks_str,w_body_high,w_body_low in cands:
  is_buy=dir=="BUY";emoji="🟢" if is_buy else "🔴"
  holds=calc_hold_days(time.time())
  ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1_body,"tp1_body":tp1_body,"tp1_wick":tp1_wick,"tp2":tp2_body,"tp2_body":tp2_body,"tp2_wick":tp2_wick,"tp3":tp3,"is_buy":is_buy,"label":TAG,"type":sig_type,"score":score,"rr":rr,"checks":checks_str,"reason":reason,"ts":time.time(),"runner_days":0,"rebuy":w_low,"holds":{k:v.strftime("%Y-%m-%d") for k,v in holds.items()}};save_a()
  journal_log({"date":today,"time":get_time(),"coin":sym,"type":sig_type,"direction":dir,"score":score,"checks":checks_str,"entry":live,"sl":sl,"tp1":tp1_body,"tp2":tp2_body,"tp3":tp3,"rr":f"{rr:.1f}","btc_trend":f"{btc_trend}/{btc_phase} {fmt(btc_price)}","reason":reason,"result":"OPEN","pnl":"","missing":""})
  if is_buy:
      tg(
          f"🟢 BUY {sym.replace('_USDT','USDT')} | {TAG}\n"
          f"{reason}\n"
          f"LAST WEEK H {fmt(w_high)} Body {fmt(w_body_high)} L {fmt(w_low)} Body {fmt(w_body_low)} FIXED MON-SUN\n"
          f"\n"
          f"🟢 BUY FROM HERE:\n"
          f"BUY AT {fmt(live)} | SL {fmt(sl)}\n"
          f"HOLD {3.5} DAYS TO {fmt(tp1_body)} ~ {holds['tp1_body'].strftime('%b %d')}\n"
          f"\n"
          f"🔴 SELL FROM HERE TO HERE:\n"
          f"SELL FROM {fmt(tp1_body)} DOWN TO {fmt(w_low)}\n"
          f"→ SELL 70% AT {fmt(tp1_body)} = PROFIT\n"
          f"→ FLIP TO SHORT 30% AT {fmt(tp1_body)}\n"
          f"→ COVER SHORT + RE-BUY LONG AT {fmt(w_low)} IN ~2 DAYS (Nov 05-06)\n"
          f"\n"
          f"🔴 SECOND SELL FROM HERE TO HERE:\n"
          f"SELL FROM {fmt(tp1_body)} UP TO {fmt(tp1_wick)}\n"
          f"→ SELL 30% RUNNER AT {fmt(tp1_wick)} ~ {holds['tp1_wick'].strftime('%b %d')} Day 4.5\n"
          f"→ FULL FLIP TO SHORT AT {fmt(tp1_wick)} DOWN TO {fmt(w_low)}\n"
          f"\n"
          f"🟢 HOLD LONG:\n"
          f"FROM {fmt(w_low)} TO {fmt(tp3)}\n"
          f"→ HOLD TO {fmt(tp2_body)} ~ {holds['tp2_body'].strftime('%b %d')} Day 8\n"
          f"→ HOLD TO {fmt(tp3)} BREAKOUT ~ {holds['breakout'].strftime('%b %d')} Day 11 STOP FLIPPING\n"
          f"\n"
          f"RR {rr:.1f} BTC {fmt(btc_price)}"
      )
  else:
      tg(
          f"🔴 SELL {sym.replace('_USDT','USDT')} | {TAG}\n"
          f"{reason}\n"
          f"LAST WEEK H {fmt(w_high)} Body {fmt(w_body_high)} L {fmt(w_low)} Body {fmt(w_body_low)}\n"
          f"\n"
          f"🔴 SELL FROM HERE:\n"
          f"SELL AT {fmt(live)} | SL {fmt(sl)}\n"
          f"\n"
          f"🟢 BUY FROM HERE TO HERE:\n"
          f"BUY FROM {fmt(tp1_body)} UP TO {fmt(w_high)}\n"
          f"→ BUY 70% AT {fmt(tp1_body)} = PROFIT + FLIP TO LONG\n"
          f"→ COVER + RE-SELL AT {fmt(w_high)} IN ~2 DAYS\n"
          f"\n"
          f"RR {rr:.1f}"
      )
if __name__=="__main__":
 if "--once" in sys.argv:scan()
 else:
  while True:
   try:scan()
   except Exception as e:print(f"EX {e}")
   time.sleep(900)
