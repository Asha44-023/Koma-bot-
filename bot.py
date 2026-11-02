import json,os,time,tempfile,requests
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","JASMY_USDT","LAB_USDT","VELVET_USDT","PEPE_USDT","DOGE_USDT"]
BETA_MAP={"BTC_USDT":1.0,"GRASS_USDT":2.5,"KOMA_USDT":2.2,"SENT_USDT":2.2,"SIREN_USDT":2.4,"PEPE_USDT":1.9,"LAB_USDT":2.1,"VELVET_USDT":2.6,"JASMY_USDT":1.9,"DOGE_USDT":1.8}
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";OI_FILE="oi_history.json";WHALE_LOG="whale_log.json"
MAX_ACTIVE=15;TOP_N_PER_SCAN=10
session=requests.Session()
TAG="V200.15-FIXED-COLOR-WHALE"

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
  if p>=1000:return round(p/50)*50
  if p>=100:return round(p/5)*5
  if p>=10:return round(p*2)/2
  if p>=1:return round(p*20)/20
  if p>=0.1:return round(p*20)/20
  if p>=0.01:return round(p*200)/200
  return round(p*1000)/1000
 except:return p
def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15)
 except:pass

def map_coin_pattern(afar):
    try:
        if not afar: return {"pattern":"NONE","signal":"NONE","reason":"no afar"}
        highs=afar.get("highs",[]); lows=afar.get("lows",[])
        if len(highs)>=3:
            h1=highs[1]["price"] if len(highs)>1 else 0; h2=highs[0]["price"] if len(highs)>0 else 0; h3=highs[2]["price"] if len(highs)>2 else 0
            if h1<h2 and h3<h2 and abs(h1-h3)/h2<0.08: return {"pattern":"H&S_TOP","signal":"TOP","reason":f"H&S TOP S {fmt(h1)} H {fmt(h2)} S {fmt(h3)}"}
        if len(lows)>=3:
            l1=lows[1]["price"] if len(lows)>1 else 0; l2=lows[0]["price"] if len(lows)>0 else 0; l3=lows[2]["price"] if len(lows)>2 else 0
            if l1>l2 and l3>l2 and abs(l1-l3)/l1<0.08: return {"pattern":"INV_H&S_BOTTOM","signal":"BOTTOM","reason":f"INV H&S {fmt(l1)}->{fmt(l2)}->{fmt(l3)}"}
        if len(highs)>=2 and len(lows)>=2:
            h1=highs[1]["price"] if len(highs)>1 else 0; h2=highs[0]["price"] if len(highs)>0 else 0; l1=lows[1]["price"] if len(lows)>1 else 0; l2=lows[0]["price"] if len(lows)>0 else 0
            if abs(h1-h2)/h2<0.03: return {"pattern":"DOUBLE_TOP","signal":"TOP","reason":f"Double Top {fmt(h1)}~{fmt(h2)}"}
            if abs(l1-l2)/l2<0.03: return {"pattern":"DOUBLE_BOTTOM","signal":"BOTTOM","reason":f"Double Bottom {fmt(l1)}~{fmt(l2)}"}
            if l2>l1*0.97 and h2>h1*0.97 and h2<h1: return {"pattern":"COIL","signal":"COIL","reason":f"Coil HL {fmt(l1)}->{fmt(l2)} + LH rising {fmt(h1)}->{fmt(h2)}"}
            if l2>l1*0.97: return {"pattern":"HL","signal":"BOTTOM","reason":f"HL {fmt(l1)}->{fmt(l2)}"}
            if l2<l1*0.97: return {"pattern":"LL","signal":"BEAR","reason":f"LL {fmt(l1)}->{fmt(l2)}"}
            if h2<h1*0.97: return {"pattern":"LH","signal":"TOP","reason":f"LH {fmt(h1)}->{fmt(h2)}"}
        return {"pattern":"RANGE","signal":"RANGE","reason":"Ranging filling liquidity"}
    except Exception as e: return {"pattern":"ERR","signal":"ERR","reason":str(e)[:60]}

def map_btc_coordinates(btc_afar, btc_d1):
    try:
        if not btc_afar: return {"signal":"NO_MAP","reason":"no afar","pattern":"NONE","coord_text":"NO_COORD"}
        highs=btc_afar.get("highs",[]); lows=btc_afar.get("lows",[])
        if len(lows)<1: return {"signal":"NO_MAP","reason":"no lows","pattern":"NONE","coord_text":"NO_COORD"}
        coords=[]
        for h in highs: coords.append({"x":-h["days_ago"],"y":h["price"],"type":"H"})
        for l in lows: coords.append({"x":-l["days_ago"],"y":l["price"],"type":"L"})
        coords=sorted(coords,key=lambda c:c["x"])
        coord_text=""
        for c in coords[-6:]: coord_text+=f"{c['type']}({abs(c['x'])}d {fmt(c['y'])})->"
        coord_text=coord_text[:-2] if len(coord_text)>2 else "NO_COORD"
        h1=highs[1]["price"] if len(highs)>1 else 0; h2=highs[0]["price"] if len(highs)>0 else 0; h3=highs[2]["price"] if len(highs)>2 else 0
        l1=lows[1]["price"] if len(lows)>1 else 0; l2=lows[0]["price"] if len(lows)>0 else 0; l3=lows[2]["price"] if len(lows)>2 else 0
        pattern="NONE"; signal="RANGE"; reason=""
        if len(highs)>=3:
            if h1<h2 and h3<h2 and abs(h1-h3)/h2<0.08: pattern="HEAD_SHOULDERS_TOP"; signal="TOP_FORMING"; reason=f"H&S TOP S {fmt(h1)} H {fmt(h2)} S {fmt(h3)} bear flip"
        if pattern=="NONE" and len(lows)>=3:
            if l1>l2 and l3>l2 and abs(l1-l3)/l1<0.08: pattern="INV_H&S_BOTTOM"; signal="BOTTOM_FORMING"; reason=f"INV H&S BOTTOM {fmt(l1)}->{fmt(l2)}->{fmt(l3)} bull flip"
        if pattern=="NONE" and len(highs)>=2 and abs(h1-h2)/h2<0.03: pattern="DOUBLE_TOP"; signal="TOP_FORMING"; reason=f"Double Top {fmt(h1)}~{fmt(h2)}"
        if pattern=="NONE" and len(lows)>=2 and abs(l1-l2)/l2<0.03: pattern="DOUBLE_BOTTOM"; signal="BOTTOM_FORMING"; reason=f"Double Bottom {fmt(l1)}~{fmt(l2)}"
        is_hl=l2>l1*0.97; is_ll=l2<l1*0.97; is_hh=h2>h1*1.03; is_lh=h2<h1*0.97; is_higher_lh=h2>h1*0.97 and h2<h1
        if pattern=="NONE":
            if is_lh and is_ll: signal="DUMP_STARTING"; reason=f"LH {fmt(h1)}->{fmt(h2)} + LL {fmt(l1)}->{fmt(l2)} bullish year ending"
            elif is_lh and is_hl: signal="TOP_FORMING"; reason=f"LH {fmt(h1)}->{fmt(h2)} + HL {fmt(l1)}->{fmt(l2)} coiling top"
            elif is_hl and is_higher_lh: signal="BUY_IN_BEAR"; reason=f"Coil HL {fmt(l1)}->{fmt(l2)} + LH rising {fmt(h1)}->{fmt(h2)} gaps filled"
            elif is_hl: signal="BOTTOM_FORMING"; reason=f"HL {fmt(l1)}->{fmt(l2)} bottom forming"
            elif is_ll: signal="BEAR_CONTINUE"; reason=f"Still LL {fmt(l1)}->{fmt(l2)} bear continue"
            elif is_hh and is_hl: signal="PUMP_STARTING"; reason=f"HH {fmt(h1)}->{fmt(h2)} + HL {fmt(l1)}->{fmt(l2)} bull start"
            else: signal="RANGE"; reason=f"Range H {fmt(h1)}->{fmt(h2)} L {fmt(l1)}->{fmt(l2)} filling liquidity"
        return {"signal":signal,"reason":reason,"pattern":pattern,"coords":coords,"coord_text":coord_text,"entry_long":l2,"sl_long":l2*0.80,"entry_short":h2,"sl_short":h2*1.20}
    except Exception as e: return {"signal":"NO_MAP","reason":str(e)[:80],"pattern":"ERR","coord_text":"ERR"}

def get_oi_funding(symbol):
    try:
        hist=load_json(OI_FILE,{});oi_now=None;funding=0.0
        for url in [f"https://contract.mexc.com/api/v1/contract/open_interest/{symbol}",f"https://contract.mexc.com/api/v1/contract/ticker?symbol={symbol}"]:
            try:
                r=session.get(url,timeout=6).json();data=r.get("data",r)
                if isinstance(data,dict):
                    if "openInterest" in data:oi_now=float(data["openInterest"]);break
                    if "open_interest" in data:oi_now=float(data["open_interest"]);break
                    if "holdVol" in data:oi_now=float(data["holdVol"]);break
            except:continue
        try:
            fr=session.get(f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}",timeout=6).json();fd=fr.get("data",fr)
            if isinstance(fd,dict):funding=float(fd.get("fundingRate",fd.get("funding_rate",0)))
            elif isinstance(fd,list) and fd:funding=float(fd[0].get("fundingRate",0))
        except:funding=0.0
        beta=BETA_MAP.get(symbol,2.0);oi_thr=20-(beta*3);fund_thr=0.08-(beta*0.01);oi_thr=max(oi_thr,8);fund_thr=max(fund_thr,0.025)
        if oi_now is None:return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK OI no data fund {funding*100:.3f}%","oi_change":0,"funding":funding}
        prev=hist.get(symbol,{}).get("oi",oi_now);prev_ts=hist.get(symbol,{}).get("ts",0)
        if time.time()-prev_ts>7200 and symbol not in hist:oi_change=0
        else:oi_change=(oi_now-prev)/prev*100 if prev>0 else 0
        hist[symbol]={"oi":oi_now,"ts":time.time(),"funding":funding};atomic_save(OI_FILE,hist);fp=funding*100
        if abs(fp)>0.12:return {"status":"FUND_EXTREME","ok":False,"msg":f"FUND_EXTREME {fp:.3f}% thr {fund_thr:.3f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr and fp>fund_thr:return {"status":"LONG_TRAP","ok":False,"msg":f"LONG_TRAP OI+{oi_change:.1f}%>{oi_thr:.0f}% fund+{fp:.3f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr and fp<-fund_thr:return {"status":"SHORT_TRAP","ok":False,"msg":f"SHORT_TRAP OI+{oi_change:.1f}% fund{fp:.3f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr*1.8:return {"status":"OI_SPIKE","ok":False,"msg":f"OI_SPIKE OI+{oi_change:.1f}%","oi_change":oi_change,"funding":funding}
        return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK OI{oi_change:+.1f}% fund{fp:+.3f}%","oi_change":oi_change,"funding":funding}
    except Exception as e:return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK err {str(e)[:30]}","oi_change":0,"funding":0}

def detect_wick_grab(d):
    try:
        if not d or len(d["c"])<2:return None
        o,h,l,c=d["o"][-1],d["h"][-1],d["l"][-1],d["c"][-1];body=abs(c-o)
        if body<c*0.00025:body=c*0.00025;lower=min(o,c)-l;upper=h-max(o,c);lower_pct=lower/c;upper_pct=upper/c;thr=0.0015 if c>1000 else 0.0030;mult=1.8
        if lower>body*mult and lower_pct>thr:return {"type":"GRAB_DOWN","wick":lower,"pct":lower_pct*100,"body":body,"note":f"Lower wick {lower_pct*100:.3f}% x{lower/body:.1f}"}
        if upper>body*mult and upper_pct>thr:return {"type":"GRAB_UP","wick":upper,"pct":upper_pct*100,"body":body,"note":f"Upper wick {upper_pct*100:.3f}% x{upper/body:.1f}"}
        return None
    except:return None

def get_mexc_perps_wall(symbol):
    try:
        url=f"https://contract.mexc.com/api/v1/contract/depth/{symbol}";r=session.get(url,timeout=6,headers={"User-Agent":"Mozilla/5.0"}).json();data=r.get("data",r);bids=data.get("bids",[])[:30];asks=data.get("asks",[])[:30]
        if not bids or not asks: return {"bias":"UNKNOWN","note":"no book","imbalance":0,"whale_log":"NO BOOK"}
        bid_vol=sum(float(b[1]) for b in bids);ask_vol=sum(float(a[1]) for a in asks);big_bid=max(float(b[1]) for b in bids);big_ask=max(float(a[1]) for a in asks)
        big_bid_idx=max(range(len(bids)), key=lambda i: float(bids[i][1]));big_ask_idx=max(range(len(asks)), key=lambda i: float(asks[i][1]))
        total=bid_vol+ask_vol;imb=(bid_vol-ask_vol)/total*100 if total else 0
        whale_log=f"WHALE LOG {symbol} | BIDS {bid_vol:.0f} vs ASKS {ask_vol:.0f} Imbal {imb:+.1f}% | BIG BID {fmt(big_bid)} @ {fmt(bids[big_bid_idx][0])} pos {big_bid_idx} | BIG ASK {fmt(big_ask)} @ {fmt(asks[big_ask_idx][0])} pos {big_ask_idx}"
        try:
            wlog=load_json(WHALE_LOG,{});wlog[symbol]={"time":get_time(),"bid_vol":bid_vol,"ask_vol":ask_vol,"imbalance":imb,"big_bid":big_bid,"big_bid_price":bids[big_bid_idx][0],"big_ask":big_ask,"big_ask_price":asks[big_ask_idx][0],"log":whale_log};atomic_save(WHALE_LOG,wlog)
        except: pass
        if big_bid>bid_vol*0.30: return {"bias":"WHALE_BUY_WALL","imbalance":imb,"note":f"BUY WALL {fmt(big_bid)} @ {fmt(bids[big_bid_idx][0])} Imbal {imb:+.1f}%","price":float(bids[big_bid_idx][0]),"whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if big_ask>ask_vol*0.30: return {"bias":"WHALE_SELL_WALL","imbalance":imb,"note":f"SELL WALL {fmt(big_ask)} @ {fmt(asks[big_ask_idx][0])} Imbal {imb:+.1f}%","price":float(asks[big_ask_idx][0]),"whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if imb>25: return {"bias":"BID_HEAVY","imbalance":imb,"note":f"BIDS heavy {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if imb<-25: return {"bias":"ASK_HEAVY","imbalance":imb,"note":f"ASKS heavy {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        return {"bias":"NEUTRAL","imbalance":imb,"note":f"Balanced {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
    except Exception as e: return {"bias":"ERR","note":str(e)[:80],"imbalance":0,"whale_log":f"ERR {e}"}

def kl(symbol,interval):
 sec_map={"Min5":300,"Min15":900,"Min60":3600,"Hour4":14400,"Day1":86400};sec=sec_map.get(interval,300);end=int(time.time());start=end-sec*500
 url=f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&start={start}&end={end}"
 for _ in range(3):
  try:
   r=session.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15);j=r.json();d=j.get("data",j)
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
def calc_hold_days_dynamic(entry,target,atr):
 if atr==0 or atr is None:atr=abs(entry-target)/3.5 if target else entry*0.03
 dist=abs(target-entry);days=dist/atr if atr>0 else 3.5;days=max(1,round(days));return min(days,30)
def get_afar_levels(d1,lookback=90):
 try:
  if not d1 or len(d1["h"])<lookback:lookback=len(d1["h"])-5
  h=d1["h"][-lookback:];l=d1["l"][-lookback:];highs=[];lows=[]
  for i in range(3,len(h)-3):
   if h[i]>max(h[i-3:i]) and h[i]>max(h[i+1:i+4]):highs.append({"price":h[i],"days_ago":len(h)-1-i})
   if l[i]<min(l[i-3:i]) and l[i]<min(l[i+1:i+4]):lows.append({"price":l[i],"days_ago":len(l)-1-i})
  highs=sorted(highs,key=lambda x:x["days_ago"])[:4];lows=sorted(lows,key=lambda x:x["days_ago"])[:4]
  h_recent=d1["h"][-20:];l_recent=d1["l"][-20:];recent_high=max(h_recent);recent_low=min(l_recent)
  mh=max(h);ml=min(l);major_high=highs[0]["price"] if highs else mh;major_high_2=highs[1]["price"] if len(highs)>1 else mh;major_low=lows[0]["price"] if lows else ml;major_low_2=lows[1]["price"] if len(lows)>1 else ml
  shape="RANGE 90D"
  if len(lows)>1 and lows[1]['price']<lows[0]['price']:shape="ASCENDING 90D"
  if len(highs)>1 and highs[1]['price']<highs[0]['price'] and shape=="ASCENDING 90D":shape="TRIANGLE COILING 90D"
  elif len(highs)>1 and highs[1]['price']<highs[0]['price']:shape="HH COILING 90D"
  seq=""
  if len(lows)>1:seq+=f"{'HL ->' if lows[1]['price']<lows[0]['price'] else 'LL ->'} "
  if len(highs)>1:seq+=f"{'HH ->' if highs[1]['price']<highs[0]['price'] else 'LH ->'}"
  def days_to_str(d):
   if d<8:return f"{d}d"
   if d<35:return f"{d//7}W {d%7}d"
   return f"{d//30}M {d%30}d"
  month_line=f"{days_to_str(highs[0]['days_ago'])} ago High {fmt(round_level(highs[0]['price']))} -> {days_to_str(lows[0]['days_ago'])} ago Low {fmt(round_level(lows[0]['price']))}" if highs and lows else "NO STRUCTURE"
  return {"major_high":major_high,"major_high_2":major_high_2,"major_low":major_low,"major_low_2":major_low_2,"recent_high":recent_high,"recent_low":recent_low,"highs":highs,"lows":lows,"mid":(major_high+major_low)/2,"shape":shape,"hl_seq":seq,"month_line":month_line,"atr":calc_atr(d1)}
 except:return None
def get_daily_levels(d1):return float(d1["h"][-2]),float(d1["l"][-2]),(float(d1["h"][-2])+float(d1["l"][-2]))/2,float(d1["h"][-2])-float(d1["l"][-2])
def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1");c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0;return "RANGE",week_change,c[-1],d1,get_afar_levels(d1,90)
 except:return "RANGE",0,77000,None,None

# ===== FIXED DETECT 5CHECK =====
def detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar,perps_wall,wick_info,third_algo,btc_map):
 try:
  y_high,y_low,y_mid,y_range=get_daily_levels(d1);h15=d15["h"];l15=d15["l"];last_h=max(h15[-5:]);last_l=min(l15[-5:]);y_high_r=round_level(y_high);y_low_r=round_level(y_low)
  wall_bias=perps_wall.get("bias","");imbalance=perps_wall.get("imbalance",0);wick_type=wick_info["type"] if wick_info else None;third_ok=third_algo.get("ok",True);third_msg=third_algo.get("msg","");btc_signal=btc_map.get("signal","NO_MAP") if btc_map else "NO_MAP";btc_pat=btc_map.get("pattern","NONE")
  if not third_ok:return False,"","","",y_high,y_low,y_mid,f"BLOCKED 3RD {third_msg}",0,third_msg
  def wall_ok(dir,bias):
      if dir=="BUY" and bias=="WHALE_SELL_WALL": return False
      if dir=="SELL" and bias=="WHALE_BUY_WALL": return False
      return True
  is_btc_bottom = btc_signal in ["BOTTOM_FORMING","BUY_IN_BEAR","PUMP_STARTING","DOUBLE_BOTTOM"] or "BOTTOM" in btc_pat or btc_pat=="INV_H&S_BOTTOM"
  is_btc_top = btc_signal in ["TOP_FORMING","DUMP_STARTING","DOUBLE_TOP"] or "TOP" in btc_pat or btc_pat=="HEAD_SHOULDERS_TOP"
  if wick_type=="GRAB_DOWN" and last_l<y_low and wall_bias in ["WHALE_BUY_WALL","BID_HEAVY"] and imbalance>20:
      if is_btc_top: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} {btc_pat} TOP - BUY 5/5 blocked",0,f"BTC TOP blocks BUY"
      return True,"BUY","5/5 WHALE FAKE",f"GRAB {wick_info['note']} + FAKE LOW {fmt(round_level(last_l))}<{fmt(y_low_r)} + {perps_wall['note']} + {third_msg} | BTC {btc_map.get('coord_text','')} {btc_pat} {btc_signal} BULL",y_high,y_low,y_mid,"5/5 BOTTOM",5,""
  if wick_type=="GRAB_UP" and last_h>y_high and wall_bias in ["WHALE_SELL_WALL","ASK_HEAVY"] and imbalance<-20:
      if is_btc_bottom: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} {btc_pat} BOTTOM - SELL 5/5 blocked",0,f"BTC BOTTOM blocks SELL"
      return True,"SELL","5/5 WHALE FAKE",f"GRAB {wick_info['note']} + FAKE HIGH {fmt(round_level(last_h))}>{fmt(y_high_r)} + {perps_wall['note']} + {third_msg} | BTC {btc_map.get('coord_text','')} {btc_pat} {btc_signal} BEAR",y_high,y_low,y_mid,"5/5 TOP",5,""
  if wick_type=="GRAB_DOWN" and wall_bias in ["WHALE_BUY_WALL","BID_HEAVY"] and imbalance>20:
      if is_btc_top: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} {btc_pat} TOP - BUY 4/5 blocked",0,"BTC TOP"
      return True,"BUY","4/5 WHALE GRAB",f"GRAB_DOWN {wick_info['note']} + {perps_wall['note']} + {third_msg} BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"4/5 BOTTOM",4,""
  if wick_type=="GRAB_UP" and wall_bias in ["WHALE_SELL_WALL","ASK_HEAVY"] and imbalance<-20:
      if is_btc_bottom: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} {btc_pat} BOTTOM - SELL 4/5 blocked",0,"BTC BOTTOM"
      return True,"SELL","4/5 WHALE GRAB",f"GRAB_UP {wick_info['note']} + {perps_wall['note']} + {third_msg} BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"4/5 TOP",4,""
  if wick_type=="GRAB_DOWN" and last_l<y_low:
      if is_btc_top: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} TOP - BUY fake blocked",0,"BTC TOP"
      if not wall_ok("BUY",wall_bias): return False,"","","",y_high,y_low,y_mid,f"BLOCKED WALL MISMATCH BUY but {wall_bias} {perps_wall['note']}",0,"wall mismatch"
      return True,"BUY","4/5 FAKE GRAB",f"GRAB {wick_info['note']} + FAKE LOW {fmt(round_level(last_l))}<{fmt(y_low_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_map.get('coord_text','')} {btc_pat}",y_high,y_low,y_mid,"4/5 BOTTOM",4,""
  if wick_type=="GRAB_UP" and last_h>y_high:
      if is_btc_bottom: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} BOTTOM - SELL fake blocked",0,"BTC BOTTOM"
      if not wall_ok("SELL",wall_bias): return False,"","","",y_high,y_low,y_mid,f"BLOCKED WALL MISMATCH SELL but {wall_bias} {perps_wall['note']} is BUY WALL",0,"wall mismatch"
      return True,"SELL","4/5 FAKE GRAB",f"GRAB {wick_info['note']} + FAKE HIGH {fmt(round_level(last_h))}>{fmt(y_high_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_map.get('coord_text','')} {btc_pat}",y_high,y_low,y_mid,"4/5 TOP",4,""
  if wick_type in ["GRAB_DOWN","GRAB_UP"]:return False,"","","",y_high,y_low,y_mid,"0/5 BLOCKED - wick alone",0,"needs wall>20% or fake"
  if wall_bias=="BID_HEAVY" and imbalance>25 and last_l<y_low*1.005:
      if is_btc_top: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} TOP - BUY 3/5 WALL blocked",0,"BTC TOP"
      return True,"BUY","3/5 WALL",f"BID HEAVY {imbalance:+.1f}% + near YL {fmt(y_low_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"3/5",3,""
  if wall_bias=="ASK_HEAVY" and imbalance<-25 and last_h>y_high*0.995:
      if is_btc_bottom: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} BOTTOM - SELL 3/5 WALL blocked",0,"BTC BOTTOM"
      return True,"SELL","3/5 WALL",f"ASK HEAVY {imbalance:+.1f}% + near YH {fmt(y_high_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"3/5",3,""
  if last_l<y_low*0.998:
      if not wall_ok("BUY",wall_bias): return False,"","","",y_high,y_low,y_mid,f"BLOCKED WALL MISMATCH BUY but {wall_bias} {perps_wall['note']}",0,"wall mismatch"
      if is_btc_top: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} TOP - BUY 3/5 FAKE blocked",0,"BTC TOP"
      return True,"BUY","3/5 FAKE",f"FAKE LOW {fmt(round_level(last_l))}< YL {fmt(y_low_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"3/5",3,""
  if last_h>y_high*1.002:
      if not wall_ok("SELL",wall_bias): return False,"","","",y_high,y_low,y_mid,f"BLOCKED WALL MISMATCH SELL but {wall_bias} {perps_wall['note']} BUY WALL",0,"wall mismatch BUY WALL cant SELL"
      if is_btc_bottom: return False,"","","",y_high,y_low,y_mid,f"BLOCKED BTC {btc_signal} BOTTOM - SELL 3/5 FAKE blocked (bull flip)",0,"BTC BOTTOM blocks SELL"
      return True,"SELL","3/5 FAKE",f"FAKE HIGH {fmt(round_level(last_h))}> YH {fmt(y_high_r)} | {perps_wall['note']} | {third_msg} | BTC {btc_signal} {btc_pat}",y_high,y_low,y_mid,"3/5",3,""
  return False,"","","",y_high,y_low,y_mid,"0/5",0,"no confluence"
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
def aligned_tp_calculation(sym,live,btc_live,btc_afar,afar,direction):
 beta=BETA_MAP.get(sym,2.0);btc_mid=btc_afar["mid"] if btc_afar else btc_live*1.06;btc_h1=btc_afar["major_high"] if btc_afar else btc_live*1.15;btc_range=btc_h1-btc_afar["major_low"] if btc_afar and btc_afar["major_low"]>0 else btc_live*0.15;btc_tp3=btc_h1+btc_range*0.6
 if direction=="BUY":
  btc_pct1=(btc_mid-btc_live)/btc_live if btc_live>0 else 0.06;btc_pct2=(btc_h1-btc_live)/btc_live if btc_live>0 else 0.10;btc_pct3=(btc_tp3-btc_live)/btc_live if btc_live>0 else 0.15;btc_pct1=max(btc_pct1,0.04);btc_pct2=max(btc_pct2,0.07)
  tp1=live*(1+btc_pct1*beta);tp2=live*(1+btc_pct2*beta);tp3=live*(1+btc_pct3*beta)
  if afar and afar["major_high"]>0:tp2=min(tp2,afar["major_high"]*1.10)
  tp3=max(tp3,tp2*1.15)
 else:
  btc_pct1=abs((btc_live-btc_mid)/btc_live) if btc_live>0 else 0.06;btc_pct1=max(btc_pct1,0.04);tp1=live*(1-btc_pct1*beta);tp2=live*(1-btc_pct1*1.6*beta);tp3=live*(1-btc_pct1*2.2*beta);tp1=min(tp1,live*0.96);tp2=min(tp2,tp1*0.94);tp3=min(tp3,tp2*0.90)
 return round_level(tp1),round_level(tp1*1.06),round_level(tp2),round_level(tp2*1.08),round_level(tp3)
def scan():
 btc_trend=get_btc_trend();btc_phase,btc_week_pct,btc_price,btc_d1,btc_afar=get_weekly_phase();btc_map=map_btc_coordinates(btc_afar,btc_d1)
 print(f"--- {TAG} {get_time()} BTC:{btc_trend} {fmt(btc_price)} MAP:{btc_map['signal']} PATTERN:{btc_map.get('pattern','')} {btc_map.get('reason','')} COORD:{btc_map.get('coord_text','')} ---")
 for sym,data in list(ACTIVE.items()):
  p=get_live(sym)
  if not p:continue
  entry,is_buy,sl=float(data["entry"]),bool(data["is_buy"]),float(data["sl"]);tp1_body=data.get("tp1_body",0);tp2_body=data.get("tp2_body",0);tp3=data.get("tp3",0);atr=data.get("atr",entry*0.03);rebuy=data.get("rebuy",0);rebuy2=data.get("rebuy2",0);afar_info=data.get("afar",{})
  d_flip=calc_hold_days_dynamic(tp1_body,rebuy,atr);d_flip2=calc_hold_days_dynamic(tp2_body,rebuy2,atr);days_held=(time.time()-data.get("ts",time.time()))/86400
  if (is_buy and p<=sl) or (not is_buy and p>=sl):
   color="🟢" if is_buy else "🔴"; dir_color="GREEN BUY" if is_buy else "RED SELL"
   print(f"AUTO DELETE {sym} price {p} hit SL {sl} removing from active.json")
   tg(f"{color} SL HIT + AUTO DELETE {sym} {fmt(p)} SL {fmt(sl)} {dir_color} Held {days_held:.0f} DAYS - deleted from active.json");ACTIVE.pop(sym,None);save_a();continue
  if rebuy>0:
   if (is_buy and p<rebuy*0.97) or (not is_buy and p>rebuy*1.03):
    month_line=afar_info.get("month_line","") if isinstance(afar_info,dict) else ""
    tg(f"🚨 OVERALL SELL {sym} 🚨\n🔴 Price {fmt(p)} BROKE rebuy {fmt(rebuy)} RED SELL\n📅 MONTH: {month_line}\nLH AFTER HH = FINAL PEAK REVERSAL\nCLOSE 100% - NO REBUY\nHeld {days_held:.0f} DAYS | BTC {fmt(btc_price)} COORD {btc_map.get('coord_text','')} PATTERN {btc_map.get('pattern','')}");ACTIVE.pop(sym,None);save_a();continue
  if not data.get("tp1_body_hit") and ((is_buy and p>=tp1_body) or (not is_buy and p<=tp1_body)):
   data["tp1_body_hit"]=True;data["sl"]=entry;save_a()
   tg(f"🔴 SMALL SELL TO HERE: {sym} TP1 BODY HIT {fmt(p)} RED SELL\n🟢 BUY {fmt(entry)} -> TP1 {fmt(tp1_body)} GREEN->RED\n🔴 SELL FROM {fmt(tp1_body)} DOWN TO {fmt(rebuy)} IN {d_flip:.0f} DAYS (Small Sell RED)\n🟢 FLIP TO SHORT -> RE-BUY AT {fmt(rebuy)} (Small Buy GREEN) | Day {days_held:.0f} | BTC {btc_map.get('signal','')} {btc_map.get('pattern','')}")
  if data.get("tp1_body_hit") and not data.get("small_buy_done") and ((is_buy and p<=rebuy*1.02) or (not is_buy and p>=rebuy*0.98)):
   data["small_buy_done"]=True;save_a();tg(f"🟢 SMALL BUY {sym} at {fmt(p)} near rebuy {fmt(rebuy)} GREEN BUY flip long | BTC COORD {btc_map.get('coord_text','')}")
  if not data.get("tp2_body_hit") and ((is_buy and p>=tp2_body) or (not is_buy and p<=tp2_body)):
   data["tp2_body_hit"]=True;data["sl"]=tp1_body;save_a()
   tg(f"🟢 HOLD TO BREAKOUT: {sym} TP2 BODY HIT {fmt(p)} GREEN\n🔴 SMALL SELL FROM {fmt(tp2_body)} DOWN TO {fmt(rebuy2)} IN {d_flip2:.0f} DAYS RED SELL\n🟢 FINAL HOLD {fmt(rebuy2)} TO {fmt(tp3)} GREEN | Day {days_held:.0f} | BTC {btc_map.get('signal','')} {btc_map.get('pattern','')}")
  if data.get("tp2_body_hit") and not data.get("small_buy2_done") and ((is_buy and p<=rebuy2*1.02) or (not is_buy and p>=rebuy2*0.98)):
   data["small_buy2_done"]=True;save_a();tg(f"🟢 SMALL BUY 2 {sym} at {fmt(p)} near rebuy2 {fmt(rebuy2)} GREEN BUY final flip | BTC COORD {btc_map.get('coord_text','')}")
  if not data.get("tp3_hit") and ((is_buy and p>=tp3) or (not is_buy and p<=tp3)):
   data["tp3_hit"]=True;save_a();tg(f"🏁 OVERALL FINAL CLOSE: {sym} TP3 WIN {fmt(p)} {fmt(entry)} -> {fmt(tp3)} Held {days_held:.0f} DAYS GREEN WIN | BTC {btc_map.get('signal','')} PATTERN {btc_map.get('pattern','')}")
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
   coin_pat=map_coin_pattern(afar)
   wick=detect_wick_grab(d15);wall=get_mexc_perps_wall(sym);third=get_oi_funding(sym);time.sleep(0.2)
   ok,direction,sig_type,reason,y_h,y_l,y_mid,checks_str,checks_score,missing=detect_5check(d1,d15,d5,live,btc_trend,btc_phase,btc_price,afar,wall,wick,third,btc_map)
   if not ok:
       if wick or wall["bias"]!="NEUTRAL" or not third["ok"]:
           print(f"PERPS WATCH {sym} COIN_PAT:{coin_pat['pattern']} WICK:{wick['note'] if wick else None} WALL:{wall['note']} WHALE_LOG:{wall['whale_log']} 3RD:{third['msg']} BTC:{btc_map['signal']} PATTERN:{btc_map.get('pattern','')} REASON:{missing}")
       continue
   atr=afar["atr"]
   if direction=="BUY":
    sl_raw=afar["recent_low"]*0.80
    if wick and wick["type"]=="GRAB_DOWN":sl_raw=min(sl_raw,d15["l"][-1]*0.995*0.80)
    sl=round_level(sl_raw if sl_raw<live*0.99 else live*0.80)
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym,live,btc_price,btc_afar,afar,"BUY")
    rebuy_low=round_level(afar["recent_low"]);rebuy2=round_level(afar["major_low"]*0.98)
   else:
    sl_raw=afar["recent_high"]*1.20
    if wick and wick["type"]=="GRAB_UP":sl_raw=max(sl_raw,d15["h"][-1]*1.005*1.20)
    sl=round_level(sl_raw if sl_raw>live*1.01 else live*1.20)
    tp1_body,tp1_wick,tp2_body,tp2_wick,tp3=aligned_tp_calculation(sym,live,btc_price,btc_afar,afar,"SELL")
    rebuy_low=round_level(afar["recent_high"]);rebuy2=round_level(afar["major_high"])
   risk=abs(live-sl)/live*100
   if risk>35 or risk<5:continue
   reward=abs(tp1_body-live)/live*100;rr=reward/risk if risk>0 else 0
   if rr<1.0:
       print(f"BLOCKED LOW RR {sym} RR {rr:.2f} risk {risk:.1f} reward {reward:.1f}")
       continue
   d1_hold=calc_hold_days_dynamic(live,tp1_body,atr);d2_hold=calc_hold_days_dynamic(live,tp2_body,atr);d3_hold=calc_hold_days_dynamic(live,tp3,atr);d_flip=calc_hold_days_dynamic(tp1_body,rebuy_low,atr);d_flip2=calc_hold_days_dynamic(tp2_body,rebuy2,atr)
   cands.append((checks_score,sym,direction,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,BETA_MAP.get(sym,2.0),reason,checks_str,wall,wick,third,coin_pat))
  except Exception as e:print(f"EX {sym} {e}");continue
 cands=sorted(cands,key=lambda x:x[0],reverse=True)[:TOP_N_PER_SCAN]
 for score,sym,dir,sig_type,live,sl,tp1_body,tp1_wick,tp2_body,tp2_wick,tp3,rr,afar,atr,rebuy_low,rebuy2,d1_hold,d2_hold,d3_hold,d_flip,d_flip2,beta,reason,checks_str,wall,wick,third,coin_pat in cands:
  try:
   entry=live;is_buy=dir=="BUY"
   ACTIVE[sym]={"entry":entry,"sl":sl,"tp1_body":tp1_body,"tp1_wick":tp1_wick,"tp2_body":tp2_body,"tp2_wick":tp2_wick,"tp3":tp3,"is_buy":is_buy,"ts":time.time(),"rr":rr,"afar":{"shape":afar["shape"],"month_line":afar["month_line"],"hl_seq":afar["hl_seq"]},"atr":atr,"rebuy":rebuy_low,"rebuy2":rebuy2,"beta":beta,"d1_hold":d1_hold,"d2_hold":d2_hold,"d3_hold":d3_hold,"d_flip":d_flip,"d_flip2":d_flip2,"whale":wall,"wick":wick,"third":third,"btc_map":btc_map,"coin_pat":coin_pat}
   save_a()
   if is_buy: dir_emoji="🟢"; color_word="GREEN BUY"; whale_emoji="🐳🟢"
   else: dir_emoji="🔴"; color_word="RED SELL"; whale_emoji="🐳🔴"
   msg=(f"{whale_emoji} {color_word} {sym} | {TAG} | {sig_type}\n"
        f"{dir_emoji} {reason} {checks_str} PHASE {btc_phase} BTC {fmt(round_level(btc_price))} {btc_map['signal']} PATTERN {btc_map.get('pattern','')} {btc_map.get('reason','')}\n"
        f"🗺 BTC COORD: {btc_map.get('coord_text','')}\n"
        f"📈 COIN COORD: {coin_pat['pattern']} {coin_pat['reason']} | {afar['month_line']}\n"
        f"🔍 AFAR {afar['shape']} {afar['hl_seq']} ATR {fmt(atr)}\n"
        f"🐋 WHALE LOG: {wall['whale_log']}\n"
        f"{dir_emoji} OVERALL {color_word} {fmt(entry)} SL {fmt(sl)} (WIDE 20%) RR {rr:.1f} Beta {beta}x\n"
        f"🔴 Small Sell TP1 {fmt(tp1_body)}->{fmt(tp1_wick)} {d1_hold}D RED SELL | 🟢 Small Buy FLIP {fmt(tp1_body)}->{fmt(rebuy_low)} {d_flip}D GREEN BUY\n"
        f"🔴 TP2 {fmt(tp2_body)}->{fmt(tp2_wick)} {d2_hold}D RED SELL | 🟢 FLIP {fmt(tp2_body)}->{fmt(rebuy2)} {d_flip2}D GREEN BUY\n"
        f"🏁 TP3 {fmt(tp3)} {d3_hold}D GREEN WIN\n"
        f"🧠 3RD ALGO {third['msg']}")
   tg(msg)
  except Exception as e:print(f"TG EX {e}")
if __name__=="__main__":
 import sys
 if "--once" in sys.argv:scan();print(f"--- DONE ONCE {get_time()} SLEEP 0 ---")
 else:
   while True:
     try:scan()
     except Exception as e:print(f"SCAN ERR {e}");tg(f"SCAN ERR {e}")
     sleep_sec=900;print(f"--- SLEEP {sleep_sec}s {get_time()} ---");time.sleep(sleep_sec)
