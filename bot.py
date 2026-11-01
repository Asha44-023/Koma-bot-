import json,os,time,tempfile,requests
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","JASMY_USDT","LAB_USDT","VELVET_USDT"]
BETA_MAP={"BTC_USDT":1.0,"GRASS_USDT":2.5,"KOMA_USDT":2.2,"SENT_USDT":2.2,"SIREN_USDT":2.4,"PEPE_USDT":1.9,"LAB_USDT":2.1,"VELVET_USDT":2.6}
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json"
MAX_ACTIVE=10;TOP_N_PER_SCAN=8
session=requests.Session()
TAG="V200.8-WHALE-SENSITIVE-PERPS"

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
ACTIVE=load_json(ACTIVE_FILE,{});COOLDOWN=load_json(COOLDOWN_FILE,{})
COOLDOWN.setdefault("daily_pnl",0.0);COOLDOWN.setdefault("last_day",get_today())
def save_a():atomic_save(ACTIVE_FILE,ACTIVE)
def save_c():atomic_save(COOLDOWN_FILE,COOLDOWN)

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
  if p>=1000: return round(p/50)*50
  if p>=100: return round(p/5)*5
  if p>=10: return round(p*2)/2
  if p>=1: return round(p*20)/20
  if p>=0.1: return round(p*20)/20
  if p>=0.01: return round(p*200)/200
  return round(p*1000)/1000
 except:return p

def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15)
 except:pass

def detect_wick_grab(d):
    try:
        if not d or len(d["c"])<2: return None
        o,h,l,c = d["o"][-1], d["h"][-1], d["l"][-1], d["c"][-1]
        body = abs(c - o)
        if body==0: body = c*0.0003
        lower = min(o,c) - l
        upper = h - max(o,c)
        lower_pct = lower / c if c else 0
        upper_pct = upper / c if c else 0
        threshold = 0.0012 if c>1000 else 0.0035
        if lower > body*1.6 and lower_pct > threshold:
            return {"type":"GRAB_DOWN","wick":lower,"pct":lower_pct*100,"body":body,"note":f"Lower wick {lower_pct*100:.3f}% x{lower/body:.1f}"}
        if upper > body*1.6 and upper_pct > threshold:
            return {"type":"GRAB_UP","wick":upper,"pct":upper_pct*100,"body":body,"note":f"Upper wick {upper_pct*100:.3f}% x{upper/body:.1f}"}
        return None
    except: return None

def get_mexc_perps_wall(symbol):
    try:
        url = f"https://contract.mexc.com/api/v1/contract/depth/{symbol}"
        r = session.get(url, timeout=6, headers={"User-Agent":"Mozilla/5.0"}).json()
        data = r.get("data", r)
        bids = data.get("bids", [])[:20]
        asks = data.get("asks", [])[:20]
        if not bids or not asks:
            return {"bias":"UNKNOWN","note":"no perps book"}
        bid_vol = sum(float(b[1]) for b in bids)
        ask_vol = sum(float(a[1]) for a in asks)
        biggest_bid_qty = max(float(b[1]) for b in bids)
        biggest_ask_qty = max(float(a[1]) for a in asks)
        biggest_bid_price = float(bids[0][0])
        biggest_ask_price = float(asks[0][0])
        total = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total * 100 if total else 0
        if biggest_bid_qty > bid_vol*0.30:
            return {"bias":"WHALE_BUY_WALL","imbalance":imbalance,"bid_vol":bid_vol,"ask_vol":ask_vol,"note":f"PERPS BUY WALL {fmt(biggest_bid_qty)} contracts @ {fmt(biggest_bid_price)} | Imbal {imbalance:+.1f}%","price":biggest_bid_price}
        if biggest_ask_qty > ask_vol*0.30:
            return {"bias":"WHALE_SELL_WALL","imbalance":imbalance,"bid_vol":bid_vol,"ask_vol":ask_vol,"note":f"PERPS SELL WALL {fmt(biggest_ask_qty)} contracts @ {fmt(biggest_ask_price)} | Imbal {imbalance:+.1f}%","price":biggest_ask_price}
        if imbalance > 25:
            return {"bias":"BID_HEAVY","imbalance":imbalance,"bid_vol":bid_vol,"ask_vol":ask_vol,"note":f"PERPS BIDS heavy {imbalance:+.1f}% ({bid_vol:.0f} vs {ask_vol:.0f})"}
        if imbalance < -25:
            return {"bias":"ASK_HEAVY","imbalance":imbalance,"bid_vol":bid_vol,"ask_vol":ask_vol,"note":f"PERPS ASKS heavy {imbalance:+.1f}% ({bid_vol:.0f} vs {ask_vol:.0f})"}
        return {"bias":"NEUTRAL","imbalance":imbalance,"bid_vol":bid_vol,"ask_vol":ask_vol,"note":f"Balanced {imbalance:+.1f}%"}
    except Exception as e:
        return {"bias":"ERR","note":str(e)[:80],"imbalance":0}

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

def calc_hold_days_dynamic(entry, target, atr):
 if atr==0 or atr is None: atr = abs(entry-target)/3.5 if target else entry*0.03
 dist=abs(target-entry); days=dist/atr if atr>0 else 3.5
 days = max(1, round(days))
 return min(days, 30)

def get_afar_levels(d1, lookback=90):
 try:
  if not d1 or len(d1["h"]) < lookback: lookback = len(d1["h"])-5
  h=d1["h"][-lookback:]; l=d1["l"][-lookback:]
  highs=[]; lows=[]
  for i in range(3, len(h)-3):
   if h[i] > max(h[i-3:i]) and h[i] > max(h[i+1:i+4]): highs.append({"price": h[i], "days_ago": len(h)-1 - i})
   if l[i] < min(l[i-3:i]) and l[i] < min(l[i+1:i+4]): lows.append({"price": l[i], "days_ago": len(l)-1 - i})
  highs=sorted(highs, key=lambda x: x["days_ago"])[:4]; lows=sorted(lows, key=lambda x: x["days_ago"])[:4]
  h_recent=d1["h"][-20:]; l_recent=d1["l"][-20:]
  recent_high = max(h_recent); recent_low = min(l_recent)
  recent_low_days = 20 - l_recent.index(recent_low) -1
  recent_high_days = 20 - h_recent.index(recent_high) -1
  mh=max(h); ml=min(l)
  major_high=highs[0]["price"] if highs else mh; major_high_2=highs[1]["price"] if len(highs)>1 else mh
  major_low=lows[0]["price"] if lows else ml; major_low_2=lows[1]["price"] if len(lows)>1 else ml
  shape="RANGE 90D"
  if len(lows)>1 and lows[1]['price']<lows[0]['price']: shape="ASCENDING 90D"
  if len(highs)>1 and highs[1]['price']<highs[0]['price'] and shape=="ASCENDING 90D": shape="TRIANGLE COILING 90D"
  elif len(highs)>1 and highs[1]['price']<highs[0]['price']: shape="HH COILING 90D"
  seq=""
  if len(lows)>1: seq+=f"{'HL ->' if lows[1]['price']<lows[0]['price'] else 'LL ->'} "
  if len(highs)>1: seq+=f"{'HH ->' if highs[1]['price']<highs[0]['price'] else 'LH ->'}"
  def days_to_str(d):
   if d<8: return f"{d}d"
   if d<35: return f"{d//7}W {d%7}d"
   return f"{d//30}M {d%30}d"
  month_line=f"{days_to_str(highs[0]['days_ago'])} ago High {fmt(round_level(highs[0]['price']))} -> {days_to_str(lows[0]['days_ago'])} ago Low {fmt(round_level(lows[0]['price']))}" if highs and lows else "NO STRUCTURE"
  if len(highs)>1 and len(lows)>1:
   month_line+=f" -> {days_to_str(highs[1]['days_ago'])} ago {'HIGHER' if highs[1]['price']<highs[0]['price'] else 'LOWER'} {fmt(round_level(highs[1]['price']))} -> {days_to_str(lows[1]['days_ago'])} ago {'LOWER' if lows[1]['price']>lows[0]['price'] else 'HIGHER'} {fmt(round_level(lows[1]['price']))}"
  return {"major_high": major_high, "major_high_2": major_high_2, "major_low": major_low, "major_low_2": major_low_2, "recent_high": recent_high, "recent_low": recent_low, "recent_low_days": recent_low_days, "recent_high_days": recent_high_days, "highs": highs, "lows": lows, "mid": (major_high+major_low)/2, "shape": shape, "hl_seq": seq, "month_line": month_line, "atr": calc_atr(d1)}
 except:return None

def get_daily_levels(d1): return float(d1["h"][-2]),float(d1["l"][-2]),(float(d1["h"][-2])+float(d1["l"][-2]))/2,float(d1["h"][-2])-float(d1["l"][-2])

def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1")
  c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0
  return "RANGE",week_change,c[-1],d1,get_afar_levels(d1,90)
 except:return "RANGE",0,77000,None,None

def detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar, perps_wall, wick_info):
 try:
  y_high,y_low,y_mid,y_range=get_daily_levels(d1)
  h15=d15["h"];l15=d15["l"];c15=d15["c"]
  last_h=max(h15[-5:]);last_l=min(l15[-5:])
  y_high_r=round_level(y_high); y_low_r=round_level(y_low)
  wall_bias = perps_wall.get("bias","")
  imbalance = perps_wall.get("imbalance",0)
  wick_type = wick_info["type"] if wick_info else None
  if wick_type=="GRAB_DOWN" and last_l<y_low:
      return True,"BUY","PERPS_WHALe_FAKE",f"PERPS GRAB {wick_info['note']} + FAKE LOW {fmt(round_level(last_l))} < YL {fmt(y_low_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"5/5 PERPS WHALE",5,""
  if wick_type=="GRAB_UP" and last_h>y_high:
      return True,"SELL","PERPS_WHALe_FAKE",f"PERPS GRAB {wick_info['note']} + FAKE HIGH {fmt(round_level(last_h))} > YH {fmt(y_high_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"5/5 PERPS WHALE",5,""
  if wick_type=="GRAB_DOWN":
      if wall_bias in ["WHALE_BUY_WALL","BID_HEAVY"]:
          return True,"BUY","PERPS_GRAB",f"GRAB_DOWN {wick_info['note']} + {perps_wall['note']} => BUY REVERSAL",y_high,y_low,y_mid,"4/5 PERPS",4,""
      return True,"BUY","GRAB",f"GRAB_DOWN {wick_info['note']} | {perps_wall['note']} => Wait BUY",y_high,y_low,y_mid,"3/5",3,""
  if wick_type=="GRAB_UP":
      if wall_bias in ["WHALE_SELL_WALL","ASK_HEAVY"]:
          return True,"SELL","PERPS_GRAB",f"GRAB_UP {wick_info['note']} + {perps_wall['note']} => SELL REVERSAL",y_high,y_low,y_mid,"4/5 PERPS",4,""
      return True,"SELL","GRAB",f"GRAB_UP {wick_info['note']} | {perps_wall['note']} => Wait SELL",y_high,y_low,y_mid,"3/5",3,""
  if wall_bias=="BID_HEAVY" and last_l<y_low*1.005:
      return True,"BUY","PERPS_IMBAL",f"BID HEAVY {imbalance:+.1f}% + near YL {fmt(y_low_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"3/5 IMBAL",3,""
  if wall_bias=="ASK_HEAVY" and last_h>y_high*0.995:
      return True,"SELL","PERPS_IMBAL",f"ASK HEAVY {imbalance:+.1f}% + near YH {fmt(y_high_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"3/5 IMBAL",3,""
  if last_l<y_low: return True,"BUY","SWEEP_FAKE",f"FAKE LOW {fmt(round_level(last_l))} < YL {fmt(y_low_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"3/5",3,""
  if last_h>y_high: return True,"SELL","SWEEP_FAKE",f"FAKE HIGH {fmt(round_level(last_h))} > YH {fmt(y_high_r)} | {perps_wall['note']}",y_high,y_low,y_mid,"3/5",3,""
  if c15[-1]>y_high and c15[-2]>y_high: return True,"BUY","BREAKOUT",f"BREAKOUT {fmt(y_high_r)}->{fmt(round_level(live))} | {perps_wall['note']}",y_high,y_low,y_mid,"3/5",3,""
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
  btc_pct1=max(btc_pct1,0.04); btc_pct2=max(btc_pct2,0.07)
  tp1=live*(1+btc_pct1*beta); tp2=live*(1+btc_pct2*beta); tp3=live*(1+btc_pct3*beta)
  if afar and afar["major_high"]>0: tp2=min(tp2, afar["major_high"]*1.10)
  tp3=max(tp3, tp2*1.15)
 else:
  btc_pct1=abs((btc_live-btc_mid)/btc_live) if btc_live>0 else 0.06
  btc_pct1=max(btc_pct1,0.04)
  tp1=live*(1-btc_pct1*beta)
  tp2=live*(1-btc_pct1*1.6*beta)
  tp3=live*(1-btc_pct1*2.2*beta)
  tp1=min(tp1, live*0.96); tp2=min(tp2, tp1*0.94); tp3=min(tp3, tp2*0.90)
 return round_level(tp1),round_level(tp1*1.06),round_level(tp2),round_level(tp2*1.08),round_level(tp3)

def scan():
 btc_trend=get_btc_trend();btc_phase,btc_week_pct,btc_price,btc_d1,btc_afar=get_weekly_phase()
 print(f"--- {TAG} {get_time()} BTC:{btc_trend} {fmt(btc_price)} ---")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"])
  tp1_body=data.get("tp1_body",0);tp2_body=data.get("tp2_body",0);tp3=data.get("tp3",0)
  atr=data.get("atr", entry*0.03);rebuy=data.get("rebuy",0);rebuy2=data.get("rebuy2",0)
  afar_info=data.get("afar",{})
  d_flip=calc_hold_days_dynamic(tp1_body, rebuy, atr); d_flip2=calc_hold_days_dynamic(tp2_body, rebuy2, atr)
  days_held=(time.time()-data.get("ts",time.time()))/86400
  if (is_buy and p<=sl) or (not is_buy and p>=sl): 
   tg(f"🔴 SL {sym} {fmt(p)} SL {fmt(sl)} Held {days_held:.0f} DAYS");ACTIVE.pop(sym,None);save_a();continue
  if rebuy>0:
   if (is_buy and p < rebuy*0.97) or (not is_buy and p > rebuy*1.03):
    month_line=afar_info.get("month_line","") if isinstance(afar_info,dict) else ""
    tg(f"🚨 OVERALL SELL {sym} 🚨\nPrice {fmt(p)} BROKE rebuy {fmt(rebuy)}\n📅 MONTH: {month_line}\nLH AFTER HH = FINAL PEAK REVERSAL\nCLOSE 100% - NO REBUY\nHeld {days_held:.0f} DAYS | BTC {fmt(btc_price)}")
    ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_body_hit") and ((is_buy and p>=tp1_body) or (not is_buy and p<=tp1_body)):
   data["tp1_body_hit"]=True;data["sl"]=entry;save_a()
   tg(f"🔴 SELL TO HERE: {sym} TP1 BODY HIT {fmt(p)}\n🟢 BUY {fmt(entry)} -> TP1 {fmt(tp1_body)}\n🔴 SELL FROM {fmt(tp1_body)} DOWN TO {fmt(rebuy)} IN {d_flip:.0f} DAYS\n🟢 FLIP TO SHORT -> RE-BUY AT {fmt(rebuy)} | Day {days_held:.0f}")
  if not data.get("tp2_body_hit") and ((is_buy and p>=tp2_body) or (not is_buy and p<=tp2_body)):
   data["tp2_body_hit"]=True;data["sl"]=tp1_body;save_a()
   tg(f"🟢 HOLD TO BREAKOUT: {sym} TP2 BODY HIT {fmt(p)}\n🔴 SELL FROM {fmt(tp2_body)} DOWN TO {fmt(rebuy2)} IN {d_flip2:.0f} DAYS\n🟢 FINAL HOLD {fmt(rebuy2)} TO {fmt(tp3)} | Day {days_held:.0f}")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
   data["tp3_hit"]=True;save_a(); tg(f"🏁 FINAL CLOSE: {sym} TP3 WIN {fmt(p)} {fmt(entry)} -> {fmt(tp3)} Held {days_held:.0f} DAYS")

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
   wick = detect_wick_grab(d15)
   wall = get_mexc_perps_wall(sym)
   time.sleep(0.2)
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar, wall, wick)
   if not ok: 
       if wick or wall["bias"]!="NEUTRAL":
           print(f"PERPS WATCH {sym} WICK:{wick} WALL:{wall}")
       continue
   atr=afar["atr"]
   if direction=="BUY":
    sl_raw=afar["recent_low"]*0.97
    if wick and wick["type"]=="GRAB_DOWN":
        sl_raw = min(sl_raw, d15["l"][-1]*0.995)
    sl=round_level(sl_raw if sl_raw < live*0.99 else live*0.97)
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "BUY")
    rebuy_low=round_level(afar["recent_low"]); rebuy2=round_level(afar["major_low"]*0.98)
   else:
    sl_raw=afar["recent_high"]*1.03
    if wick and wick["type"]=="GRAB_UP":
        sl_raw = max(sl_raw, d15["h"][-1]*1.005)
    sl=round_level(sl_raw if sl_raw > live*1.01 else live*1.03)
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym, live, btc_price, btc_afar, afar, "SELL")
    rebuy_low=round_level(afar["recent_high"]); rebuy2=round_level(afar["major_high"])
   risk=abs(live-sl)/live*100
   if risk>10 or risk<0.5:continue
   reward=abs(tp1_body-live)/live*100;rr=reward/risk if risk>0 else 0
   d1_hold=calc_hold_days_dynamic(live, tp1_body, atr)
   d2_hold=calc_hold_days_dynamic(live, tp2_body, atr)
   d3_hold=calc_hold_days_dynamic(live, tp3, atr)
   d_flip=calc_hold_days_dynamic(tp1_body, rebuy_low, atr)
   d_flip2=calc_hold_days_dynamic(tp2_body, rebuy2, atr)
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,BETA_MAP.get(sym,2.0),reason,checks_str, wall, wick))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,beta,reason,checks_str, wall, wick in cands:
  try:
   entry=live;is_buy=dir=="BUY"
   ACTIVE[sym]={"entry":entry,"sl":sl,"tp1_body":tp1_body,"tp1_wick":tp1_wick,"tp2_body":tp2_body,"tp2_wick":tp2_wick,"tp3":tp3,"is_buy":is_buy,"ts":time.time(),"rr":rr,"afar":{"shape":afar["shape"],"month_line":afar["month_line"],"hl_seq":afar["hl_seq"]},"atr":atr,"rebuy":rebuy_low,"rebuy2":rebuy2,"beta":beta,"d1_hold":d1_hold,"d2_hold":d2_hold,"d3_hold":d3_hold,"d_flip":d_flip,"d_flip2":d_flip2,"whale":wall,"wick":wick}
   save_a()
   whale_emoji = "🐋" if "WHALE" in sig_type or "PERPS" in sig_type else "🐟"
   msg=(f"{whale_emoji} {dir} {sym} | {TAG} | {sig_type}\n"
        f"{reason} {checks_str} PHASE {btc_phase} BTC {fmt(round_level(btc_price))}\n"
        f"📅 MONTH: {afar['month_line']}\n"
        f"🔭 AFAR {afar['shape']} | SEQ {afar['hl_seq']} | ATR {fmt(round_level(atr))} | BETA {beta}x\n"
        f"🐋 PERPS WALL: {wall['note']}\n"
        f"🕯️ WICK: {wick['note'] if wick else 'No grab'}\n"
        f"🟢 BUY FROM HERE:\nBUY AT {fmt(round_level(entry))} | SL {fmt(round_level(sl))}\n"
        f"HOLD {d1_hold:.0f} DAYS TO {fmt(tp1_body)} | WICK {fmt(tp1_wick)}\n"
        f"🔴 SELL FROM {fmt(tp1_body)} DOWN TO {fmt(rebuy_low)} IN {d_flip:.0f} DAYS\n"
        f"RR {rr:.1f} | Entry {fmt(round_level(entry))} SL {fmt(round_level(sl))} Size 10-15% capital\n")
   tg(msg); print(msg)
  except Exception as e:print(f"SAVE EX {e}");continue

if __name__=="__main__":
 import sys
 if "--once" in sys.argv: scan()
 else:
  while True:
   try: scan()
   except Exception as e: print(f"EX {e}")
   print(f"SLEEP 900 sec - {get_time()}")
   time.sleep(900)
