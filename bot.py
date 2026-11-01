import json,os,time,tempfile,requests
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","PEPE_USDT","LAB_USDT","VELVET_USDT"]
BETA_MAP={"BTC_USDT":1.0,"GRASS_USDT":2.5,"KOMA_USDT":2.2,"SENT_USDT":2.2,"SIREN_USDT":2.4,"PEPE_USDT":1.9,"LAB_USDT":2.1,"VELVET_USDT":2.6}
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json"
MAX_ACTIVE=6;TOP_N_PER_SCAN=3
session=requests.Session()
TAG="V201.0-GREEN-RED-LIVE"

def get_time():return datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
def get_today():return datetime.now(EAT).strftime("%Y-%m-%d")
def load_json(p,d):
 try:
  import json
  with open(p,"r") as f:v=json.load(f);return v if isinstance(v,type(d)) else d
 except:return d
def atomic_save(path,data):
 import tempfile,json,os
 d=os.path.dirname(os.path.abspath(path)) or ".";fd,tp=tempfile.mkstemp(dir=d,prefix=".tmp_")
 try:
  with os.fdopen(fd,"w") as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno());os.replace(tp,path)
 except:
  try:os.unlink(tp)
  except:pass;raise
ACTIVE=load_json(ACTIVE_FILE,{});COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("daily_pnl",0.0);COOLDOWN.setdefault("last_day",get_today())
def save_a():atomic_save(ACTIVE_FILE,ACTIVE)
def save_c():atomic_save(COOLDOWN_FILE,COOLDOWN)
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
def kl(symbol,interval):
 sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400};sec=sec_map.get(interval,300);end=int(time.time());start=end-sec*500
 url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
 for _ in range(3):
  try:
   r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15)
   j=r.json();d=j.get("data",j)
   if isinstance(d,dict) and "data" in d:d=d["data"]
   if not d or "open" not in d:continue
   res={"o":[float(x) for x in d["open"]],"h":[float(x) for x in d["high"]],"l":[float(x) for x in d["low"]],"c":[float(x) for x in d["close"]],"v":[float(x) for x in d.get("vol",[0]*len(d["close"]))]}
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
  return sum(tr[-period:])/period if len(tr)>=period else c[-1]*0.03
 except:return 0.0
def get_afar_levels(d1, lookback=90):
 try:
  if not d1 or len(d1["h"]) < lookback: lookback = len(d1["h"])-5
  h=d1["h"][-lookback:]; l=d1["l"][-lookback:]
  highs=[]; lows=[]
  for i in range(3, len(h)-3):
   if h[i] > max(h[i-3:i]) and h[i] > max(h[i+1:i+4]): highs.append({"price": h[i], "days_ago": len(h)-1 - i})
   if l[i] < min(l[i-3:i]) and l[i] < min(l[i+1:i+4]): lows.append({"price": l[i], "days_ago": len(l)-1 - i})
  highs=sorted(highs, key=lambda x: x["days_ago"])[:4]; lows=sorted(lows, key=lambda x: x["days_ago"])[:4]
  mh=max(h); ml=min(l)
  major_high=highs[0]["price"] if highs else mh; major_high_2=highs[1]["price"] if len(highs)>1 else mh
  major_low=lows[0]["price"] if lows else ml; major_low_2=lows[1]["price"] if len(lows)>1 else ml
  return {"major_high": major_high, "major_high_2": major_high_2, "major_low": major_low, "major_low_2": major_low_2, "mid": (major_high+major_low)/2, "shape": "RANGE", "atr": calc_atr(d1)}
 except:return None
def calc_hold_days_dynamic(entry, target, atr):
 if atr==0 or atr is None: atr = abs(entry-target)/3.5 if target else entry*0.03
 dist=abs(target-entry); days=dist/atr if atr>0 else 3.5
 return int(max(1, min(round(days), 30)))
def get_daily_levels(d1): return float(d1["h"][-2]),float(d1["l"][-2]),(float(d1["h"][-2])+float(d1["l"][-2]))/2,float(d1["h"][-2])-float(d1["l"][-2])
def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1")
  c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0
  return "RANGE",week_change,c[-1],d1,get_afar_levels(d1,90)
 except:return "RANGE",0,77000,None,None
def detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar):
 try:
  y_high,y_low,y_mid,y_range=get_daily_levels(d1)
  h15=d15["h"];l15=d15["l"];c15=d15["c"]
  last_h=max(h15[-5:]);last_l=min(l15[-5:])
  if last_l<y_low: return True,"BUY","SWEEP_FAKE",f"FAKE LOW {fmt(last_l)}",y_high,y_low,y_mid,"4/5",4,""
  if last_h>y_high: return True,"SELL","SWEEP_FAKE",f"FAKE HIGH {fmt(last_h)}",y_high,y_low,y_mid,"4/5",4,""
  if c15[-1]>y_high and c15[-2]>y_high: return True,"BUY","BREAKOUT",f"BREAKOUT {fmt(y_high)}->{fmt(live)}",y_high,y_low,y_mid,"4/5",4,""
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
 beta=BETA_MAP.get(sym,2.0)
 btc_mid=btc_afar["mid"] if btc_afar else btc_live*1.06
 btc_h1=btc_afar["major_high"] if btc_afar else btc_live*1.15
 btc_range=btc_h1-btc_afar["major_low"] if btc_afar and btc_afar["major_low"]>0 else btc_live*0.15
 btc_tp3=btc_h1+btc_range*0.6
 if direction=="BUY":
  btc_pct1=(btc_mid-btc_live)/btc_live if btc_live>0 else 0.06
  btc_pct2=(btc_h1-btc_live)/btc_live if btc_live>0 else 0.10
  btc_pct3=(btc_tp3-btc_live)/btc_live if btc_live>0 else 0.15
  tp1=live*(1+btc_pct1*beta); tp2=live*(1+btc_pct2*beta); tp3=live*(1+btc_pct3*beta)
  if afar and afar["major_high"]>0: tp2=min(tp2, afar["major_high"]*1.10)
  tp3=max(tp3, tp2*1.15)
  return tp1,tp1*1.06,tp2,tp2*1.08,tp3
 else:
  btc_pct1=(btc_live-btc_mid)/btc_live if btc_live>0 else 0.06
  tp1=live*(1-btc_pct1*beta); tp2=live*(1-btc_pct1*1.6*beta); tp3=live*(1-btc_pct1*2.2*beta)
  return tp1,tp1*0.98,tp2,tp2*0.95,tp3

def scan():
 btc_trend=get_btc_trend();btc_phase,btc_week_pct,btc_price,btc_d1,btc_afar=get_weekly_phase()
 print(f"--- {TAG} {get_time()} BTC:{btc_trend} {fmt(btc_price)} ---")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
  tp1_body=data.get("tp1_body",0);tp2_body=data.get("tp2_body",0);tp3=data.get("tp3",0)
  atr=data.get("atr", entry*0.03);rebuy=data.get("rebuy",0);rebuy2=data.get("rebuy2",0)
  d_flip=int(calc_hold_days_dynamic(tp1_body, rebuy, atr)); d_flip2=int(calc_hold_days_dynamic(tp2_body, rebuy2, atr))
  if (is_buy and p<=sl) or (not is_buy and p>=sl): tg(f"🔴 SL {sym} {fmt(p)}");ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_body_hit") and ((is_buy and p>=tp1_body) or (not is_buy and p<=tp1_body)):
   data["tp1_body_hit"]=True;data["sl"]=entry;save_a(); tg(f"🔴 SELL TO HERE: {sym} TP1 HIT {fmt(p)}\n🟢 {fmt(entry)} -> ✅ {fmt(tp1_body)}\n🔴 SELL FROM {fmt(tp1_body)} TO {fmt(rebuy)} IN {d_flip} DAYS\n🟢 BUY BACK AT {fmt(rebuy)} TO {fmt(tp2_body)}")
  if not data.get("tp2_body_hit") and ((is_buy and p>=tp2_body) or (not is_buy and p<=tp2_body)):
   data["tp2_body_hit"]=True;data["sl"]=tp1_body;save_a(); tg(f"🔴 HOLD TO BREAKOUT: {sym} TP2 HIT {fmt(p)}\n🔴 SELL FROM {fmt(tp2_body)} TO {fmt(rebuy2)} IN {d_flip2} DAYS\n🟢 BUY BACK AT {fmt(rebuy2)} TO FINAL {fmt(tp3)}")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
   data["tp3_hit"]=True;save_a(); tg(f"🏁 FINAL CLOSE: {sym} TP3 WIN {fmt(p)} {fmt(entry)} -> {fmt(tp3)}")
 if len(ACTIVE)>=MAX_ACTIVE:return
 cands=[]
 for sym in SYMBOLS:
  try:
   if sym in ACTIVE:continue
   d1=kl(sym,"Day1");time.sleep(0.2);d15=kl(sym,"Min15");time.sleep(0.2);d5=kl(sym,"Min5");time.sleep(0.2)
   if not d1 or not d15:continue
   live=get_live(sym)
   if not live:continue
   afar=get_afar_levels(d1,90)
   if not afar:continue
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar)
   if not ok:continue
   atr=afar["atr"]
   if direction=="BUY":
    sl_raw=afar["major_low"]*0.95; sl=sl_raw if sl_raw < live*0.99 else live*0.97
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "BUY")
    rebuy_low=afar["major_low_2"] if afar["major_low_2"]>0 else afar["major_low"]; rebuy2=afar["major_low"]*0.98
   else:
    sl_raw=afar["major_high"]*1.05; sl=sl_raw if sl_raw > live*1.01 else live*1.03
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "SELL")
    rebuy_low=afar["major_high_2"]; rebuy2=afar["major_high"]
   risk=abs(live-sl)/live*100
   if risk>20 or risk<0.5:continue
   reward=abs(tp1_body-live)/live*100;rr=reward/risk if risk>0 else 0
   d1_hold=int(calc_hold_days_dynamic(live,tp1_body,atr));d2_hold=int(calc_hold_days_dynamic(live,tp2_body,atr));d3_hold=int(calc_hold_days_dynamic(live,tp3,atr));d_flip=int(calc_hold_days_dynamic(tp1_body,rebuy_low,atr));d_flip2=int(calc_hold_days_dynamic(tp2_body,rebuy2,atr))
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,BETA_MAP.get(sym,2.0),reason,checks_str))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,beta,reason,checks_str in cands:
  try:
   entry=live;is_buy=dir=="BUY"
   ACTIVE[sym]={"entry":entry,"sl":sl,"tp1_body":tp1_body,"tp1_wick":tp1_wick,"tp2_body":tp2_body,"tp2_wick":tp2_wick,"tp3":tp3,"is_buy":is_buy,"ts":time.time(),"rr":rr,"afar":{"shape":afar["shape"]},"atr":atr,"rebuy":rebuy_low,"rebuy2":rebuy2,"beta":beta,"d1_hold":d1_hold,"d2_hold":d2_hold,"d3_hold":d3_hold,"d_flip":d_flip,"d_flip2":d_flip2}
   save_a()
   msg=(f"{'🟢 BUY TO HERE' if is_buy else '🔴 SELL TO HERE'}: {sym} {dir} {sig_type} LIVE {fmt(live)}\n"
        f"🟢 BUY AT {fmt(entry)}\n"
        f"✅ Take profit at {fmt(tp1_body)} HOLD {d1_hold} DAYS\n"
        f"🔴 SELL FROM {fmt(tp1_body)} TO {fmt(rebuy_low)} IN {d_flip} DAYS\n"
        f"🟢 BUY BACK AT {fmt(rebuy_low)} TO {fmt(tp2_body)} HOLD {d2_hold} DAYS\n"
        f"✅ Take profit at {fmt(tp2_body)}\n"
        f"🔴 SELL FROM {fmt(tp2_body)} TO {fmt(rebuy2)} IN {d_flip2} DAYS\n"
        f"🟢 BUY BACK AT {fmt(rebuy2)} TO FINAL {fmt(tp3)} HOLD {d3_hold} DAYS\n"
        f"🏁 FINAL CLOSE AT {fmt(tp3)}\n"
        f"SL {fmt(sl)} RR {rr:.1f} {checks_str}")
   tg(msg); print(msg)
  except Exception as e:print(f"SAVE EX {e}");continue

if __name__=="__main__":
 import sys
 if "--once" in sys.argv:
  scan()
 else:
  while True:
   try: scan()
   except Exception as e: print(f"EX {e}")
   print(f"SLEEP 900 sec - {get_time()}")
   time.sleep(900)
