import json,os,sys,time,tempfile,requests,csv
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT"]
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE,COOLDOWN_FILE,STATS_FILE,JOURNAL_FILE="active.json","cooldown.json","stats_v199.json","trade_journal.csv"
MAX_ACTIVE=6;TOP_N_PER_SCAN=2
session=requests.Session()
TAG="V199.7-CLEAN-GREEN-RED-4of5-WEEKLY-MONTHLY"
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
  if not d1 or len(d1["c"])<30:return "RANGE",0
  c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0
  month_change=(c[-1]-c[-22])/c[-22]*100 if c[-22]!=0 else 0
  if week_change<-5:return "WEEKLY_DUMP_ENDING",week_change
  if week_change>5:return "WEEKLY_PUMP",week_change
  if month_change<-15:return "MONTHLY_DUMP_ENDING",month_change
  return "RANGE",week_change
 except:return "RANGE",0
def get_coin_cycle_levels(d1):
 try:
  if not d1 or len(d1["c"])<30:return None
  w_high=max(d1["h"][-7:]);w_low=min(d1["l"][-7:]);m_high=max(d1["h"][-30:]);m_low=min(d1["l"][-30:]);w_mid=(w_high+w_low)/2;m_mid=(m_high+m_low)/2
  return w_high,w_low,m_high,m_low,w_mid,m_mid
 except:return None
def detect_5check(d1,d15,d5,live,btc_trend):
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
  wick_up=upper_wick>body*0.5;wick_down=lower_wick>body*0.5
  bos_bear=False;bos_bull=False
  if d15 and len(d15["c"])>10:
   if c15[-1]<min(d15["l"][-10:-5]):bos_bear=True
   if c15[-1]>max(d15["h"][-10:-5]):bos_bull=True
  if sweep_down:
   checks=0;reasons=[];missing=[]
   if sweep_down:checks+=1;reasons.append("sweep")
   if close_back_above:checks+=1;reasons.append("close_back")
   else:missing.append("no close_back")
   if wick_down:checks+=1;reasons.append("wick")
   else:missing.append("no wick")
   if bos_bull:checks+=1;reasons.append("BOS")
   else:missing.append("no BOS")
   if btc_trend!="DOWN":checks+=1;reasons.append(f"BTC:{btc_trend}")
   else:missing.append(f"BTC DOWN")
   reason=f"FAKE LOW {fmt(last_l)} < YL {fmt(y_low)} {checks}/5"
   return checks>=4,"BUY","SWEEP_FAKE",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  if sweep_up:
   checks=0;reasons=[];missing=[]
   if sweep_up:checks+=1;reasons.append("sweep")
   if close_back_below:checks+=1;reasons.append("close_back")
   else:missing.append("no close_back")
   if wick_up:checks+=1;reasons.append("wick")
   else:missing.append("no wick")
   if bos_bear:checks+=1;reasons.append("BOS")
   else:missing.append("no BOS")
   if btc_trend!="UP":checks+=1;reasons.append(f"BTC:{btc_trend}")
   else:missing.append(f"BTC UP")
   reason=f"FAKE HIGH {fmt(last_h)} > YH {fmt(y_high)} {checks}/5"
   return checks>=4,"SELL","SWEEP_FAKE",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  two_below=c15[-1]<y_low and c15[-2]<y_low
  if two_below and live<y_low*1.002 and live>y_low*0.97:
   checks=3;reasons=["2 closes below","breakdown -3%"];missing=[]
   if btc_trend=="DOWN" or btc_trend=="RANGE":checks+=1;reasons.append(f"BTC {btc_trend}")
   else:missing.append("BTC not DOWN")
   if bos_bear:checks+=1;reasons.append("BOS")
   else:missing.append("no BOS")
   reason=f"BREAKDOWN {fmt(y_low)} -> {fmt(live)} -3% {checks}/5"
   return checks>=4,"SELL","BREAKDOWN",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
  two_above=c15[-1]>y_high and c15[-2]>y_high
  if two_above and live>y_high*0.998 and live<y_high*1.03:
   checks=3;reasons=["2 closes above","breakout +3%"];missing=[]
   if btc_trend=="UP" or btc_trend=="RANGE":checks+=1;reasons.append(f"BTC {btc_trend}")
   else:missing.append("BTC not UP")
   if bos_bull:checks+=1;reasons.append("BOS")
   else:missing.append("no BOS")
   reason=f"BREAKOUT {fmt(y_high)} -> {fmt(live)} +3% {checks}/5"
   return checks>=4,"BUY","BREAKOUT",reason,y_high,y_low,y_mid,f"{checks}/5",checks,",".join(missing)
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
 btc_trend=get_btc_trend();btc_phase,btc_week_pct=get_weekly_phase()
 print(f"\n--- {TAG} {get_time()} BTC:{btc_trend} {btc_phase} {btc_week_pct:.1f}% ---")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]);tp1,tp2,tp3=float(data["tp1"]),float(data["tp2"]),float(data["tp3"])
  if (is_buy and p<=sl) or (not is_buy and p>=sl):
   pnl=(p-entry)/entry*100 if is_buy else (entry-p)/entry*100;STATS["losses"]+=1;save_s()
   tg(f"❌ {sym.replace('_USDT','USDT')} {pnl:.1f}% SL");ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_hit") and ((is_buy and p>=tp1) or (not is_buy and p<=tp1)):data["tp1_hit"]=True;data["sl"]=entry;save_a();tg(f"🟢 {sym.replace('_USDT','USDT')} TP1 WEEKLY HIT")
  if not data.get("tp2_hit") and ((is_buy and p>=tp2) or (not is_buy and p<=tp2)):data["tp2_hit"]=True;data["sl"]=tp1;save_a();tg(f"🟢 {sym.replace('_USDT','USDT')} TP2 WEEKLY HIGH/LOW HIT")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):data["tp3_hit"]=True;STATS["wins"]+=1;save_s();tg(f"✅ {sym.replace('_USDT','USDT')} TP3 MONTHLY WIN");ACTIVE.pop(sym,None);save_a();continue
 if len(ACTIVE)>=MAX_ACTIVE:print(f"MAX ACTIVE {len(ACTIVE)}");return
 cands=[]
 for sym in SYMBOLS:
  try:
   if sym in ACTIVE:continue
   d1=kl(sym,"Day1");time.sleep(0.2);d15=kl(sym,"Min15");time.sleep(0.2);d5=kl(sym,"Min5");time.sleep(0.2)
   if not d1 or not d15:continue
   live=get_live(sym)
   if not live:continue
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend)
   if not ok:
    if checks_str!="0/5":print(f"⚪ WAIT {sym} {checks_str} {missing} | {reason}")
    continue
   cycle=get_coin_cycle_levels(d1)
   if not cycle:continue
   w_high,w_low,m_high,m_low,w_mid,m_mid=cycle
   if direction=="BUY":
    sl=min(d15["l"][-3:])*0.998 if sig_type=="SWEEP_FAKE" else y_h*0.996
    tp1=w_mid;tp2=w_high*0.98;tp3=m_high*0.90
    emoji="🟢";color_code="\033[92m"
   else:
    sl=max(d15["h"][-3:])*1.002 if sig_type=="SWEEP_FAKE" else y_l*1.004
    tp1=w_mid;tp2=w_low*1.02;tp3=m_low*1.10 if m_low>0 else w_low*0.90
    emoji="🔴";color_code="\033[91m"
   risk=abs(live-sl)/live*100;reward=abs(tp1-live)/live*100;rr=reward/risk if risk>0 else 0
   if rr<0.8:print(f"{emoji} {sym} RR {rr:.1f} too low skip");continue
   print(f"{color_code}{emoji} {direction} {sym} @ {fmt(live)} {checks_str} W-H {fmt(w_high)} W-L {fmt(w_low)} M-H {fmt(m_high)} M-L {fmt(m_low)} | SL {fmt(sl)} TP1 {fmt(tp1)} TP2 {fmt(tp2)} TP3 {fmt(tp3)}\033[0m")
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1,tp2,tp3,rr,w_high,w_low,m_high,m_low,reason,checks_str))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1,tp2,tp3,rr,w_high,w_low,m_high,m_low,reason,checks_str in cands:
  is_buy=dir=="BUY";emoji="🟢" if is_buy else "🔴"
  ACTIVE[sym]={"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"is_buy":is_buy,"label":TAG,"type":sig_type,"score":score,"rr":rr,"checks":checks_str,"reason":reason,"ts":time.time()};save_a()
  journal_log({"date":today,"time":get_time(),"coin":sym,"type":sig_type,"direction":dir,"score":score,"checks":checks_str,"entry":live,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"rr":f"{rr:.1f}","btc_trend":f"{btc_trend}/{btc_phase}","reason":reason,"result":"OPEN","pnl":"","missing":""})
  tg(f"{emoji} {dir} {sym.replace('_USDT','USDT')} | {TAG}\n{reason}\nEntry {fmt(live)} SL {fmt(sl)}\nTP1 {fmt(tp1)} W-MID\nTP2 {fmt(tp2)} W-H/L\nTP3 {fmt(tp3)} M-H/L\nRR {rr:.1f}")
if __name__=="__main__":
 if "--once" in sys.argv:scan()
 else:
  while True:
   try:scan()
   except Exception as e:print(f"EX {e}")
   time.sleep(1800)
