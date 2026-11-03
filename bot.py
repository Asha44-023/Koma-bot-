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
TAG="V202-LIQUIDITY-GRAB-BUY-SELL-MAP"
ENTRY_TF="Min30";EXIT_TF="Day1"
RSI_BUY_MAX = 20
RSI_SELL_MIN = 80
COOLDOWN_HOURS = 12

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

def get_liquidity_grab_levels(afar1d, afar30m, live, side, atr):
    try:
        if not atr or atr==0: atr=live*0.04
        min_gap = live*0.04
        if side=="BUY":
            up_tp1 = round_level(live + atr*1.5)
            if up_tp1 - live < min_gap: up_tp1 = round_level(live + min_gap)
            up_tp2 = round_level(live + atr*3)
            if up_tp2 - up_tp1 < min_gap: up_tp2 = round_level(up_tp1 + min_gap)
            down_tp1 = round_level(live - atr*1.2)
            down_tp2 = round_level(afar1d.get("major_low", live*0.8))
            final_tp1 = round_level(afar1d.get("major_high", live*1.2)*0.75)
            if final_tp1 <= up_tp2: final_tp1 = round_level(up_tp2 + min_gap)
            final_tp2 = round_level(afar1d.get("major_high", live*1.2))
            if final_tp2 <= final_tp1: final_tp2 = round_level(final_tp1 + min_gap)
            chain = []
            chain.append(f"BUY {fmt(live)} -> UP TP {fmt(up_tp1)} SELL (+{((up_tp1-live)/live*100):.1f}%)")
            chain.append(f"SELL {fmt(up_tp1)} -> DOWN TP {fmt(down_tp1)} BUY ({((down_tp1-up_tp1)/up_tp1*100):.1f}%)")
            chain.append(f"BUY {fmt(down_tp1)} -> UP TP {fmt(up_tp2)} SELL (+{((up_tp2-down_tp1)/down_tp1*100):.1f}%)")
            chain.append(f"SELL {fmt(up_tp2)} -> DOWN TP {fmt(down_tp2)} BUY ({((down_tp2-up_tp2)/up_tp2*100):.1f}%)")
            chain.append(f"BUY {fmt(down_tp2)} -> UP TP {fmt(final_tp1)} TP1 SELL (+{((final_tp1-down_tp2)/down_tp2*100):.1f}%)")
            chain.append(f"BUY {fmt(down_tp2)} -> UP TP {fmt(final_tp2)} TP2 SELL (+{((final_tp2-down_tp2)/down_tp2*100):.1f}%)")
        else:
            down_tp1 = round_level(live - atr*1.5)
            if live - down_tp1 < min_gap: down_tp1 = round_level(live - min_gap)
            down_tp2 = round_level(live - atr*3)
            up_tp1 = round_level(live + atr*1.2)
            final_tp1 = round_level(afar1d.get("major_low", live*0.8)*1.25)
            final_tp2 = round_level(afar1d.get("major_low", live*0.8))
            chain = []
            chain.append(f"SELL {fmt(live)} -> DOWN TP {fmt(down_tp1)} BUY ({((live-down_tp1)/live*100):.1f}%)")
            chain.append(f"BUY {fmt(down_tp1)} -> UP TP {fmt(up_tp1)} SELL (+{((up_tp1-down_tp1)/down_tp1*100):.1f}%)")
            chain.append(f"SELL {fmt(up_tp1)} -> DOWN TP {fmt(final_tp1)} TP1 BUY (-{((up_tp1-final_tp1)/up_tp1*100):.1f}%)")
            chain.append(f"SELL {fmt(up_tp1)} -> DOWN TP {fmt(final_tp2)} TP2 BUY (-{((up_tp1-final_tp2)/up_tp1*100):.1f}%)")
        return {"chain": chain, "up_tp1": up_tp1, "up_tp2": up_tp2, "down_tp1": down_tp1, "down_tp2": down_tp2, "final_tp1": final_tp1, "final_tp2": final_tp2, "atr": atr}
    except Exception as e:
        return {"chain":[f"ERR mapping {e}"], "up_tp1":live*1.05, "down_tp1":live*0.95, "final_tp1":live*1.1, "final_tp2":live*1.2, "up_tp2":live*1.08, "down_tp2":live*0.9, "atr":live*0.04}

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
            if is_lh and is_ll: signal="DUMP_STARTING"; reason=f"LH {fmt(h1)}->{fmt(h2)} + LL {fmt(l1)}->{fmt(l2)}"
            elif is_lh and is_hl: signal="TOP_FORMING"; reason=f"LH {fmt(h1)}->{fmt(h2)} + HL {fmt(l1)}->{fmt(l2)} coiling top"
            elif is_hl and is_higher_lh: signal="BUY_IN_BEAR"; reason=f"Coil HL {fmt(l1)}->{fmt(l2)} + LH rising {fmt(h1)}->{fmt(h2)}"
            elif is_hl: signal="BOTTOM_FORMING"; reason=f"HL {fmt(l1)}->{fmt(l2)} bottom forming"
            elif is_ll: signal="BEAR_CONTINUE"; reason=f"Still LL {fmt(l1)}->{fmt(l2)} bear continue"
            elif is_hh and is_hl: signal="PUMP_STARTING"; reason=f"HH {fmt(h1)}->{fmt(h2)} + HL {fmt(l1)}->{fmt(l2)} bull start"
            else: signal="RANGE"; reason=f"Range H {fmt(h1)}->{fmt(h2)} L {fmt(l1)}->{fmt(l2)}"
        return {"signal":signal,"reason":reason,"pattern":pattern,"coords":coords,"coord_text":coord_text,"entry_long":l2,"sl_long":l2*0.80,"entry_short":h2,"sl_short":h2*1.20,"major_low":l2,"major_high":h2}
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
        if abs(fp)>0.12:return {"status":"FUND_EXTREME","ok":False,"msg":f"FUND_EXTREME {fp:.3f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr and fp>fund_thr:return {"status":"LONG_TRAP","ok":False,"msg":f"LONG_TRAP OI+{oi_change:.1f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr and fp<-fund_thr:return {"status":"SHORT_TRAP","ok":False,"msg":f"SHORT_TRAP OI+{oi_change:.1f}%","oi_change":oi_change,"funding":funding}
        if oi_change>oi_thr*1.8:return {"status":"OI_SPIKE","ok":False,"msg":f"OI_SPIKE OI+{oi_change:.1f}%","oi_change":oi_change,"funding":funding}
        return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK OI{oi_change:+.1f}% fund{fp:+.3f}%","oi_change":oi_change,"funding":funding}
    except Exception as e:return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK err","oi_change":0,"funding":0}

def get_mexc_perps_wall(symbol):
    try:
        url=f"https://contract.mexc.com/api/v1/contract/depth/{symbol}";r=session.get(url,timeout=6,headers={"User-Agent":"Mozilla/5.0"}).json();data=r.get("data",r);bids=data.get("bids",[])[:30];asks=data.get("asks",[])[:30]
        if not bids or not asks: return {"bias":"UNKNOWN","note":"no book","imbalance":0,"whale_log":"NO BOOK"}
        bid_vol=sum(float(b[1]) for b in bids);ask_vol=sum(float(a[1]) for a in asks);big_bid=max(float(b[1]) for b in bids);big_ask=max(float(a[1]) for a in asks)
        big_bid_idx=max(range(len(bids)), key=lambda i: float(bids[i][1]));big_ask_idx=max(range(len(asks)), key=lambda i: float(asks[i][1]))
        total=bid_vol+ask_vol;imb=(bid_vol-ask_vol)/total*100 if total else 0
        whale_log=f"WHALE LOG {symbol} | BIDS {bid_vol:.0f} vs ASKS {ask_vol:.0f} Imbal {imb:+.1f}% | BIG BID {fmt(big_bid)} @ {fmt(bids[big_bid_idx][0])}"
        try:
            wlog=load_json(WHALE_LOG,{});wlog[symbol]={"time":get_time(),"bid_vol":bid_vol,"ask_vol":ask_vol,"imbalance":imb,"log":whale_log};atomic_save(WHALE_LOG,wlog)
        except: pass
        if big_bid>bid_vol*0.30: return {"bias":"WHALE_BUY_WALL","imbalance":imb,"note":f"BUY WALL {fmt(big_bid)} @ {fmt(bids[big_bid_idx][0])}","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if big_ask>ask_vol*0.30: return {"bias":"WHALE_SELL_WALL","imbalance":imb,"note":f"SELL WALL {fmt(big_ask)} @ {fmt(asks[big_ask_idx][0])}","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if imb>25: return {"bias":"BID_HEAVY","imbalance":imb,"note":f"BIDS heavy {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        if imb<-25: return {"bias":"ASK_HEAVY","imbalance":imb,"note":f"ASKS heavy {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
        return {"bias":"NEUTRAL","imbalance":imb,"note":f"Balanced {imb:+.1f}%","whale_log":whale_log,"big_bid":big_bid,"big_ask":big_ask}
    except Exception as e: return {"bias":"ERR","note":str(e)[:80],"imbalance":0,"whale_log":f"ERR {e}"}

def kl(symbol,interval):
 sec_map={"Min5":300,"Min15":900,"Min30":1800,"Min60":3600,"Hour4":14400,"Day1":86400};sec=sec_map.get(interval,300);end=int(time.time());start=end-sec*500
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

def calc_rsi(c, period=14):
    try:
        if len(c)<period+1: return 50
        gains=[]; losses=[]
        for i in range(1,len(c)):
            diff=c[i]-c[i-1]
            gains.append(max(diff,0)); losses.append(max(-diff,0))
        avg_gain=sum(gains[-period:])/period; avg_loss=sum(losses[-period:])/period
        if avg_loss==0: return 80
        rs=avg_gain/avg_loss
        return 100-(100/(1+rs))
    except: return 50

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

def v201_30m_signal(d30, d1, live, rsi_30m, perps_wall):
    try:
        if not d30 or not d1: return None
        afar_1d = get_afar_levels(d1, 90)
        afar_30m = get_afar_levels(d30, 20)
        if not afar_1d: return None
        y_high, y_low, y_mid, y_range = get_daily_levels(d1)
        fear_zone = y_low * 1.10
        greed_zone = y_high * 0.90
        wall_bias = perps_wall.get("bias","")
        imb = perps_wall.get("imbalance",0)
        if live <= fear_zone and rsi_30m < RSI_BUY_MAX and wall_bias != "WHALE_SELL_WALL":
            return {"side":"BUY","zone":f"FEAR RSI{RSI_BUY_MAX}","entry":live,"real_tp1":afar_1d["major_high"]*0.75,"real_tp2":afar_1d["major_high"],"dust_tp":afar_30m["recent_high"] if afar_30m else y_high*1.05,"sl":y_low*0.80,"afar_1d":afar_1d,"afar_30m":afar_30m,"reason":f"V201 FEAR {RSI_BUY_MAX} RSI {rsi_30m:.0f}<{RSI_BUY_MAX} ZONE {fmt(live)} <= {fmt(fear_zone)} {wall_bias}"}
        if live >= greed_zone and rsi_30m > RSI_SELL_MIN and wall_bias != "WHALE_BUY_WALL":
            return {"side":"SELL","zone":f"GREED RSI{RSI_SELL_MIN}","entry":live,"real_tp1":afar_1d["major_low"]*1.25,"real_tp2":afar_1d["major_low"],"dust_tp":afar_30m["recent_low"] if afar_30m else y_low*0.95,"sl":y_high*1.20,"afar_1d":afar_1d,"afar_30m":afar_30m,"reason":f"V201 GREED {RSI_SELL_MIN} RSI {rsi_30m:.0f}>{RSI_SELL_MIN} ZONE {fmt(live)} >= {fmt(greed_zone)} {wall_bias}"}
        return None
    except Exception as e: return None

def get_weekly_phase():
 try:
  d1=kl("BTC_USDT","Day1");c=d1["c"];week_change=(c[-1]-c[-8])/c[-8]*100 if c[-8]!=0 else 0;return "RANGE",week_change,c[-1],d1,get_afar_levels(d1,90)
 except:return "RANGE",0,77000,None,None

def check_active_positions():
    updated=False
    for sym in list(ACTIVE.keys()):
        try:
            entry_info = ACTIVE[sym]
            if not isinstance(entry_info, dict): continue
            entry = float(entry_info.get("entry",0))
            side = entry_info.get("side","BUY")
            tp1 = float(entry_info.get("tp1",0))
            tp2 = float(entry_info.get("tp2",0))
            sl = float(entry_info.get("sl",0))
            live = get_live(sym)
            if not live: continue
            pnl = (live-entry)/entry*100 if side=="BUY" else (entry-live)/entry*100
            hit=False
            if side=="BUY":
                if live >= tp2: msg=f"🚀🚀 TP2 HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}\nHold days done! Take profit!"; hit=True
                elif live >= tp1: msg=f"🎯 TP1 HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}\nTake 50% profit, move SL to entry"; hit=False
                elif live <= sl: msg=f"🛑 SL HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} ({pnl:.1f}%) | {TAG}"; hit=True
                else: continue
                if "TP1 HIT" in msg:
                    tg(msg); print(msg); continue
            else:
                if live <= tp2: msg=f"🚀🚀 TP2 HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=True
                elif live <= tp1: msg=f"🎯 TP1 HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=False
                elif live >= sl: msg=f"🛑 SL HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} ({pnl:.1f}%)"; hit=True
                else: continue
                if "TP1 HIT" in msg:
                    tg(msg); print(msg); continue
            if hit:
                tg(msg); print(msg)
                del ACTIVE[sym]
                COOLDOWN[sym] = {"last_ts": time.time(), "side": side, "entry": entry}
                updated=True
        except Exception as e:
            print(f"check active err {sym} {e}")
            continue
    if updated:
        save_a(); save_c()

def scan_once():
    btc_trend,btc_week_change,btc_price,btc_d1,btc_afar=get_weekly_phase()
    btc_map=map_btc_coordinates(btc_afar,btc_d1) if btc_afar else {"signal":"NO_MAP","reason":"no btc afar","pattern":"NONE","coord_text":"NO_COORD"}
    check_active_positions()
    results=[]
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: continue
            last_entry = COOLDOWN.get(sym)
            if last_entry and isinstance(last_entry, dict) and "last_ts" in last_entry:
                if time.time() - last_entry["last_ts"] < COOLDOWN_HOURS * 3600:
                    continue
            d1=kl(sym,"Day1"); d30=kl(sym,"Min30"); d15=kl(sym,"Min15"); d5=kl(sym,"Min5")
            if not d1 or not d30: continue
            live=get_live(sym)
            if not live: live=d1["c"][-1]
            rsi30=calc_rsi(d30["c"])
            wall=get_mexc_perps_wall(sym)
            afar1=get_afar_levels(d1,90)
            if not afar1: continue
            third=get_oi_funding(sym)
            if not third.get("ok",True): continue
            v201=v201_30m_signal(d30,d1,live,rsi30,wall)
            if v201 and v201.get("side") in ["BUY","SELL"]:
                entry=v201["entry"]; side=v201["side"]; zone=v201["zone"]
                real_tp1=v201["real_tp1"]; real_tp2=v201["real_tp2"]; sl=v201["sl"]
                afar1d=v201["afar_1d"]; afar30m=v201["afar_30m"]
                hold2=calc_hold_days_dynamic(entry,real_tp2,afar1d["atr"])
                beta=BETA_MAP.get(sym,2.0)
                liq = get_liquidity_grab_levels(afar1d, afar30m, entry, side, afar1d["atr"])
                chain_text = "\n".join(liq["chain"])
                ACTIVE[sym] = {"entry": entry, "side": side, "tp1": liq["up_tp1"] if side=="BUY" else liq["down_tp1"], "tp2": liq["final_tp2"], "sl": sl, "time": get_time(), "rsi": rsi30, "zone": zone}
                save_a()
                COOLDOWN[sym] = {"last_ts": time.time(), "side": side, "entry": entry, "rsi": rsi30, "zone": zone}
                save_c()
                msg=f"🐳{'🟢' if side=='BUY' else '🔴'} {zone} {side} {sym} | {TAG} | RSI30 {rsi30:.0f}\n🗺 BTC: {btc_map.get('coord_text','')} {btc_map.get('signal','')}\n📈 {afar1d['month_line']} | ATR {fmt(afar1d['atr'])}\n🐋 {wall.get('whale_log','')}\n💧 LIQUIDITY MAP:\n{chain_text}\n🏁 TP2 {fmt(liq['final_tp2'])} {hold2}D | SL {fmt(sl)} | Cooldown {COOLDOWN_HOURS}H\n🧠 {third['msg']}"
                results.append((sym,msg,v201))
        except Exception as e:
            print(f"ERR {sym} {e}")
            continue
    return results, btc_price, btc_map

def main():
    import argparse; p=argparse.ArgumentParser(); p.add_argument("--once",action="store_true"); args=p.parse_args()
    res,btc_price,btc_map=scan_once()
    if not res:
        print(f"[{get_time()}] No new signals - active positions checked. Cooldown {COOLDOWN_HOURS}H")
        return
    for sym,msg,v201 in res[:TOP_N_PER_SCAN]:
        tg(msg)
        print(msg)
        time.sleep(1)

if __name__=="__main__":
    main()
