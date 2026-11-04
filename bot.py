import json,os,time,tempfile,requests,argparse
from datetime import datetime
import pytz
EAT=pytz.timezone("Africa/Nairobi")
SYMBOLS=["BTC_USDT","KOMA_USDT","GRASS_USDT","SENT_USDT","SIREN_USDT","JASMY_USDT","LAB_USDT","VELVET_USDT","PEPE_USDT","DOGE_USDT"]
BETA_MAP={"BTC_USDT":1.0,"GRASS_USDT":2.5,"KOMA_USDT":2.2,"SENT_USDT":2.2,"SIREN_USDT":2.4,"PEPE_USDT":1.9,"LAB_USDT":2.1,"VELVET_USDT":2.6,"JASMY_USDT":1.9,"DOGE_USDT":1.8}
TELEGRAM_TOKEN=os.getenv("TG_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT=os.getenv("TG_CHAT") or os.getenv("TELEGRAM_CHAT_ID")
ACTIVE_FILE="active.json";COOLDOWN_FILE="cooldown.json";OI_FILE="oi_history.json";WHALE_LOG="whale_log.json"
session=requests.Session()
TAG="V203.2-BETA-RSI-FIXED-RANGE"
COOLDOWN_HOURS=12; TOP_N_PER_SCAN=10

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
  if p==0: return 0
  if p>=1000:return round(p/50)*50
  if p>=100:return round(p/5)*5
  if p>=10:return round(p*2)/2
  if p>=1:return round(p*20)/20
  if p>=0.1:return round(p*200)/200
  if p>=0.01:return round(p*200)/200
  if p>=0.001:return round(p*10000)/10000
  return round(p*100000000)/100000000
 except:return p
def tg(m):
 if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:print(m);return
 try:session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage",json={"chat_id":str(TELEGRAM_CHAT).strip(),"text":m},timeout=15)
 except:pass

HIERARCHY = {
    "MONTHLY": {"key_tf": "Month1", "struct_tf": "Day1", "key_lb": 12, "struct_lb": 90, "label": "MONTHLY KEY > DAILY STRUCT"},
    "WEEKLY":  {"key_tf": "Week1", "struct_tf": "Hour4", "key_lb": 12, "struct_lb": 60, "label": "WEEKLY KEY > H4 STRUCT"},
    "DAILY":   {"key_tf": "Day1", "struct_tf": "Hour1", "key_lb": 20, "struct_lb": 72, "label": "DAILY KEY > H1 STRUCT"},
    "H4":      {"key_tf": "Hour4", "struct_tf": "Min15", "key_lb": 60, "struct_lb": 96, "label": "H4 KEY > M15 STRUCT"},
    "H1":      {"key_tf": "Hour1", "struct_tf": "Min5", "key_lb": 72, "struct_lb": 96, "label": "H1 KEY > M5 STRUCT"},
    "M15":     {"key_tf": "Min15", "struct_tf": "Min1", "key_lb": 96, "struct_lb": 120, "label": "M15 KEY > M1 STRUCT"},
}

def get_rsi_thresholds(sym):
    beta = BETA_MAP.get(sym, 2.0)
    if beta >= 2.4: return 15, 85
    elif beta >= 2.0: return 18, 82
    else: return 20, 80

def kl(symbol,interval):
 sec_map={"Min1":60,"Min5":300,"Min15":900,"Min30":1800,"Hour1":3600,"Min60":3600,"Hour4":14400,"Day1":86400,"Week1":604800,"Month1":2592000}
 sec=sec_map.get(interval,300)
 api_interval = interval
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
  shape="RANGE"
  if len(lows)>1 and lows[1]['price']<lows[0]['price']:shape="ASCENDING"
  if len(highs)>1 and highs[1]['price']<highs[0]['price'] and shape=="ASCENDING":shape="TRIANGLE COILING"
  seq=""
  if len(lows)>1:seq+=f"{'HL' if lows[1]['price']<lows[0]['price'] else 'LL'} "
  if len(highs)>1:seq+=f"{'HH' if highs[1]['price']<highs[0]['price'] else 'LH'}"
  def days_to_str(d):
   if d<8:return f"{d}d"
   if d<35:return f"{d//7}W {d%7}d"
   return f"{d//30}M {d%30}d"
  month_line=f"{days_to_str(highs[0]['days_ago'])} ago H {fmt(round_level(highs[0]['price']))} -> {days_to_str(lows[0]['days_ago'])} ago L {fmt(round_level(lows[0]['price']))}" if highs and lows else "NO STRUCTURE"
  return {"major_high":major_high,"major_high_2":major_high_2,"major_low":major_low,"major_low_2":major_low_2,"recent_high":recent_high,"recent_low":recent_low,"highs":highs,"lows":lows,"mid":(major_high+major_low)/2,"shape":shape,"hl_seq":seq,"month_line":month_line,"atr":calc_atr(d1)}
 except:return None

def get_hierarchy_levels(sym):
    levels={}
    for name,cfg in HIERARCHY.items():
        try:
            d_key=kl(sym,cfg["key_tf"]); d_struct=kl(sym,cfg["struct_tf"])
            if not d_key: continue
            key_afar=get_afar_levels(d_key,cfg["key_lb"])
            struct_afar=get_afar_levels(d_struct,cfg["struct_lb"]) if d_struct else None
            if not key_afar: continue
            struct_bias="NEUTRAL"
            if struct_afar and len(struct_afar["lows"])>1 and len(struct_afar["highs"])>0:
                l1=struct_afar["lows"][1]["price"]; l2=struct_afar["lows"][0]["price"]
                h1=struct_afar["highs"][1]["price"] if len(struct_afar["highs"])>1 else struct_afar["highs"][0]["price"]
                h2=struct_afar["highs"][0]["price"]
                if l2>l1 and h2>h1*0.97: struct_bias=f"{cfg['struct_tf']} HL HH BULL"
                elif l2<l1 and h2<h1: struct_bias=f"{cfg['struct_tf']} LL LH BEAR"
                elif l2>l1: struct_bias=f"{cfg['struct_tf']} HL"
                else: struct_bias=f"{cfg['struct_tf']} LL"
            levels[name]={"cfg":cfg,"key":key_afar,"struct":struct_afar,"bias":struct_bias}
        except: continue
    return levels

# --- NEW: ICT ALIGNMENT ---
def alignment_score(h_levels):
    # DAILY + H4 + H1 = bias for trade, per ICT post: Daily bias, H4 narrative, H1 POI
    bull=0; bear=0
    for k in ["DAILY","H4","H1"]:
        b=h_levels.get(k,{}).get("bias","")
        if "BULL" in b: bull+=1
        if "BEAR" in b: bear+=1
    return bull, bear

def get_liquidity_grab_levels_hierarchy(h_levels, live, side, atr):
    try:
        if not atr or atr==0: atr=live*0.04
        min_gap = live*0.04
        monthly = h_levels.get("MONTHLY",{}).get("key"); weekly = h_levels.get("WEEKLY",{}).get("key")
        daily = h_levels.get("DAILY",{}).get("key"); h4 = h_levels.get("H4",{}).get("key"); h1 = h_levels.get("H1",{}).get("key"); m15 = h_levels.get("M15",{}).get("key")
        monthly_high = monthly["major_high"] if monthly else live*1.5; monthly_low = monthly["major_low"] if monthly else live*0.5
        weekly_high = weekly["major_high"] if weekly else daily["major_high"]*1.1 if daily else live*1.2; weekly_low = weekly["major_low"] if weekly else daily["major_low"]*0.9 if daily else live*0.8
        daily_high = daily["major_high"] if daily else live*1.2; daily_low = daily["major_low"] if daily else live*0.8
        if side=="BUY":
            up_tp1 = round_level(h1["major_high"]*0.8 if h1 else live + atr*1.5); up_tp2 = round_level(h4["major_high"]*0.85 if h4 else live + atr*3)
            final_tp1 = round_level(daily_high*0.75); final_tp2 = round_level(daily_high); super_tp = round_level(weekly_high); moon_tp = round_level(monthly_high)
            if up_tp1 - live < min_gap: up_tp1 = round_level(live + min_gap)
            if up_tp2 - up_tp1 < min_gap: up_tp2 = round_level(up_tp1 + min_gap)
            if final_tp1 <= up_tp2: final_tp1 = round_level(up_tp2 + min_gap)
            if final_tp2 <= final_tp1: final_tp2 = round_level(final_tp1 + min_gap)
            if super_tp <= final_tp2: super_tp = round_level(final_tp2 + min_gap)
            if moon_tp <= super_tp: moon_tp = round_level(super_tp + min_gap*2)
            chain=[]
            chain.append(f"BUY {fmt(live)} (M15 KEY {fmt(m15['major_low']) if m15 else 'N/A'} > M1)")
            chain.append(f"-> TP1 {fmt(up_tp1)} H1 KEY > M5 (+{((up_tp1-live)/live*100):.1f}%)")
            chain.append(f"-> TP2 {fmt(up_tp2)} H4 KEY > M15 (+{((up_tp2-live)/live*100):.1f}%)")
            chain.append(f"-> TP3 {fmt(final_tp1)} DAILY KEY > H1 (+{((final_tp1-live)/live*100):.1f}%)")
            chain.append(f"-> TP4 {fmt(final_tp2)} DAILY HIGH (+{((final_tp2-live)/live*100):.1f}%)")
            chain.append(f"-> TP5 {fmt(super_tp)} WEEKLY KEY > H4 (+{((super_tp-live)/live*100):.1f}%)")
            chain.append(f"-> MOON {fmt(moon_tp)} MONTHLY KEY > DAILY (+{((moon_tp-live)/live*100):.1f}%)")
            return {"chain":chain,"up_tp1":up_tp1,"up_tp2":up_tp2,"final_tp1":final_tp1,"final_tp2":final_tp2,"super_tp":super_tp,"moon_tp":moon_tp,"atr":atr}
        else:
            down_tp1 = round_level(h1["major_low"] if h1 else live - atr*1.5)
            down_tp2 = round_level(h4["major_low"] if h4 else live - atr*3)
            final_tp1 = round_level(daily_low)
            final_tp2 = round_level(daily_low*0.95)
            super_tp = round_level(weekly_low)
            moon_tp = round_level(monthly_low)
            if down_tp1 >= live: down_tp1 = round_level(live - min_gap)
            if down_tp2 >= down_tp1: down_tp2 = round_level(down_tp1 - min_gap)
            if final_tp1 >= down_tp2: final_tp1 = round_level(down_tp2 - min_gap)
            if final_tp2 >= final_tp1: final_tp2 = round_level(final_tp1 - min_gap)
            if super_tp >= final_tp2: super_tp = round_level(final_tp2 - min_gap)
            if moon_tp >= super_tp: moon_tp = round_level(super_tp - min_gap*2)
            chain=[]; chain.append(f"SELL {fmt(live)} -> DOWN TP {fmt(down_tp1)} H1 KEY BUY"); chain.append(f"-> TP2 {fmt(down_tp2)} H4 KEY BUY"); chain.append(f"-> FINAL {fmt(final_tp2)} DAILY KEY BUY"); chain.append(f"-> SUPER {fmt(super_tp)} WEEKLY KEY BUY"); chain.append(f"-> MOON {fmt(moon_tp)} MONTHLY KEY BUY")
            return {"chain":chain,"up_tp1":live,"down_tp1":down_tp1,"down_tp2":down_tp2,"final_tp1":final_tp1,"final_tp2":final_tp2,"super_tp":super_tp,"moon_tp":moon_tp,"atr":atr}
    except Exception as e:
        return {"chain":[f"ERR {e}"],"up_tp1":live*1.05,"down_tp1":live*0.95,"final_tp1":live*1.1,"final_tp2":live*1.2,"super_tp":live*1.3,"moon_tp":live*1.5,"atr":live*0.04}

def get_oi_funding(symbol):
    try:
        hist=load_json(OI_FILE,{});oi_now=None;funding=0.0
        for url in [f"https://contract.mexc.com/api/v1/contract/open_interest/{symbol}",f"https://contract.mexc.com/api/v1/contract/ticker?symbol={symbol}"]:
            try:
                r=session.get(url,timeout=6).json();data=r.get("data",r)
                if isinstance(data,dict):
                    if "openInterest" in data:oi_now=float(data["openInterest"]);break
                    if "holdVol" in data:oi_now=float(data["holdVol"]);break
            except:continue
        try:
            fr=session.get(f"https://contract.mexc.com/api/v1/contract/funding_rate/{symbol}",timeout=6).json();fd=fr.get("data",fr)
            if isinstance(fd,dict):funding=float(fd.get("fundingRate",fd.get("funding_rate",0)))
        except:funding=0.0
        beta=BETA_MAP.get(symbol,2.0);oi_thr=20-(beta*3);oi_thr=max(oi_thr,8)
        if oi_now is None:return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK","oi_change":0,"funding":funding}
        prev=hist.get(symbol,{}).get("oi",oi_now);oi_change=(oi_now-prev)/prev*100 if prev>0 else 0
        hist[symbol]={"oi":oi_now,"ts":time.time(),"funding":funding};atomic_save(OI_FILE,hist)
        if oi_change>oi_thr*1.8:return {"status":"OI_SPIKE","ok":False,"msg":f"OI_SPIKE {oi_change:.1f}%","oi_change":oi_change,"funding":funding}
        return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK OI{oi_change:+.1f}%","oi_change":oi_change,"funding":funding}
    except:return {"status":"PEG_OK","ok":True,"msg":f"PEG_OK err","oi_change":0,"funding":0}

def get_mexc_perps_wall(symbol):
    try:
        url=f"https://contract.mexc.com/api/v1/contract/depth/{symbol}";r=session.get(url,timeout=6,headers={"User-Agent":"Mozilla/5.0"}).json();data=r.get("data",r);bids=data.get("bids",[])[:30];asks=data.get("asks",[])[:30]
        if not bids or not asks: return {"bias":"UNKNOWN","note":"no book","imbalance":0,"whale_log":"NO BOOK"}
        bid_vol=sum(float(b[1]) for b in bids);ask_vol=sum(float(a[1]) for a in asks);total=bid_vol+ask_vol;imb=(bid_vol-ask_vol)/total*100 if total else 0
        whale_log=f"{symbol} BIDS {bid_vol:.0f} vs ASKS {ask_vol:.0f} {imb:+.1f}%"
        if max(float(b[1]) for b in bids)>bid_vol*0.30: return {"bias":"WHALE_BUY_WALL","imbalance":imb,"note":"BUY WALL","whale_log":whale_log}
        if max(float(a[1]) for a in asks)>ask_vol*0.30: return {"bias":"WHALE_SELL_WALL","imbalance":imb,"note":"SELL WALL","whale_log":whale_log}
        return {"bias":"NEUTRAL","imbalance":imb,"note":f"Bal {imb:+.1f}%","whale_log":whale_log}
    except: return {"bias":"ERR","note":"err","imbalance":0,"whale_log":"ERR"}

def get_daily_levels(d1):
    y_high = float(d1["h"][-2]); y_low = float(d1["l"][-2]); y_mid = (y_high+y_low)/2
    range_pct = (y_high - y_low) / y_low if y_low>0 else 0.05
    if range_pct < 0.03:
        fear_zone = y_low * 1.02
        greed_zone = y_high * 0.98
    else:
        fear_zone = y_low * 1.10
        greed_zone = y_high * 0.90
    return y_high, y_low, y_mid, fear_zone, greed_zone, range_pct

def v203_signal(d30, d1, live, rsi_30m, perps_wall, h_levels, sym):
    try:
        buy_thr,sell_thr = get_rsi_thresholds(sym)
        monthly = h_levels.get("MONTHLY",{}).get("key"); daily = h_levels.get("DAILY",{}).get("key")
        if not daily: daily = get_afar_levels(d1,20)
        if not daily: return None
        y_high, y_low, y_mid, fear_zone, greed_zone, range_pct = get_daily_levels(d1)
        wall_bias = perps_wall.get("bias","")
        monthly_low = monthly["major_low"] if monthly else y_low*0.7
        monthly_high = monthly["major_high"] if monthly else y_high*1.5
        # ICT ALIGNMENT - DAILY+H4+H1 must agree 2/3
        bull, bear = alignment_score(h_levels)
        if live <= fear_zone and rsi_30m < buy_thr and wall_bias != "WHALE_SELL_WALL":
            if live > monthly_high*0.95: return None
            if bull < 2: return None  # BLOCK: not enough bullish alignment
            return {"side":"BUY","zone":f"FEAR RSI{buy_thr} BETA{sym}","entry":live,"sl":y_low*0.80,"h_levels":h_levels,"reason":f"V203.2 MONTHLY {fmt(monthly_low)} > DAILY HL | RSI {rsi_30m:.0f}<{buy_thr} range {range_pct*100:.1f}% ALIGN {bull}/3 BULL","buy_thr":buy_thr,"sell_thr":sell_thr,"fear_zone":fear_zone,"greed_zone":greed_zone,"bull":bull,"bear":bear}
        if live >= greed_zone and rsi_30m > sell_thr and wall_bias != "WHALE_BUY_WALL":
            if bear < 2: return None  # BLOCK: not enough bearish alignment - this blocks that BTC SELL
            return {"side":"SELL","zone":f"GREED RSI{sell_thr} BETA{sym}","entry":live,"sl":y_high*1.20,"h_levels":h_levels,"reason":f"V203.2 MONTHLY {fmt(monthly_high)} < DAILY LH | RSI {rsi_30m:.0f}>{sell_thr} ALIGN {bear}/3 BEAR","buy_thr":buy_thr,"sell_thr":sell_thr,"fear_zone":fear_zone,"greed_zone":greed_zone,"bull":bull,"bear":bear}
        return None
    except Exception as e: return None

def check_active_positions():
    updated=False
    for sym in list(ACTIVE.keys()):
        try:
            entry_info = ACTIVE[sym]
            if not isinstance(entry_info, dict): continue
            entry = float(entry_info.get("entry",0)); side = entry_info.get("side","BUY"); tp1 = float(entry_info.get("tp1",0)); tp2 = float(entry_info.get("tp2",0)); sl = float(entry_info.get("sl",0))
            live = get_live(sym)
            if not live: continue
            pnl = (live-entry)/entry*100 if side=="BUY" else (entry-live)/entry*100
            hit=False
            if side=="BUY":
                if live >= tp2: msg=f"🚀🚀 TP2 HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=True
                elif live >= tp1: msg=f"🎯 TP1 HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=False
                elif live <= sl: msg=f"🛑 SL HIT SELL {sym} | BUY {fmt(entry)} -> NOW {fmt(live)} ({pnl:.1f}%) | {TAG}"; hit=True
                else: continue
                if "TP1 HIT" in msg: tg(msg); print(msg); continue
            else:
                if live <= tp2: msg=f"🚀🚀 TP2 HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=True
                elif live <= tp1: msg=f"🎯 TP1 HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} (+{pnl:.1f}%) | {TAG}"; hit=False
                elif live >= sl: msg=f"🛑 SL HIT BUY {sym} | SELL {fmt(entry)} -> NOW {fmt(live)} ({pnl:.1f}%)"; hit=True
                else: continue
                if "TP1 HIT" in msg: tg(msg); print(msg); continue
            if hit:
                tg(msg); print(msg); del ACTIVE[sym]; COOLDOWN[sym] = {"last_ts": time.time(), "side": side, "entry": entry}; updated=True
        except: continue
    if updated: save_a(); save_c()

def scan_once(debug=True):
    check_active_positions()
    results=[]
    print(f"\n[{get_time()}] | {TAG} | BETA RSI: VELVET/GRASS 15/85, KOMA 18/82, BTC 20/80")
    print("-"*95)
    for sym in SYMBOLS:
        try:
            if sym in ACTIVE: print(f"{sym} ACTIVE - skip"); continue
            last_entry = COOLDOWN.get(sym)
            if last_entry and isinstance(last_entry, dict) and "last_ts" in last_entry:
                if time.time() - last_entry["last_ts"] < COOLDOWN_HOURS * 3600:
                    hrs_left = (COOLDOWN_HOURS*3600 - (time.time()-last_entry["last_ts"]))/3600
                    if debug: print(f"{sym} COOLDOWN {hrs_left:.1f}H left")
                    continue
            d1=kl(sym,"Day1"); d30=kl(sym,"Min30")
            if not d1 or not d30: print(f"{sym} NO DATA"); continue
            live=get_live(sym)
            if not live: live=d1["c"][-1]
            rsi30=calc_rsi(d30["c"])
            wall=get_mexc_perps_wall(sym)
            third=get_oi_funding(sym)
            if not third.get("ok",True): print(f"{sym} OI BLOCK {third['msg']}"); continue
            h_levels=get_hierarchy_levels(sym)
            buy_thr,sell_thr = get_rsi_thresholds(sym)
            bull,bear=alignment_score(h_levels)
            v203=v203_signal(d30,d1,live,rsi30,wall,h_levels,sym)
            if debug:
                print(f"{sym} live={fmt(live)} RSI30={rsi30:.1f} thr {buy_thr}/{sell_thr} wall={wall.get('bias')} oi={third.get('msg')} ALIGN BULL {bull}/3 BEAR {bear}/3 sig={v203['side'] if v203 else 'NONE (blocked by alignment)'}")
            if not v203: continue
            atr=calc_atr(d1)
            liq=get_liquidity_grab_levels_hierarchy(h_levels, live, v203["side"], atr)
            hier_lines=[]
            for k in ["MONTHLY","WEEKLY","DAILY","H4","H1","M15"]:
                if k in h_levels:
                    kk=h_levels[k]["key"]; bias=h_levels[k]["bias"]
                    hier_lines.append(f"{k} KEY {fmt(round_level(kk['major_low']))}-{fmt(round_level(kk['major_high']))} > {bias}")
            hier_txt="\n".join(hier_lines)
            side=v203["side"]
            entry=live; sl=v203["sl"]
            if side=="BUY":
                tp1=liq.get("up_tp1",live*1.05); tp2=liq.get("up_tp2",live*1.1); final_tp=liq.get("final_tp2",live*1.2); super_tp=liq.get("super_tp",live*1.3); moon_tp=liq.get("moon_tp",live*1.5)
                hold=calc_hold_days_dynamic(entry,tp2,atr)
                msg=f"🐳🟢 FEAR RSI{buy_thr} BETA{sym} BUY {sym} | {TAG} | RSI30 {rsi30:.0f} (thr {buy_thr}/{sell_thr}) ALIGN {bull}/3 BULL\n📊 HIERARCHY:\n{hier_txt}\n🐋 {wall.get('whale_log','')}\n💧 LIQUIDITY MAP 6 LEVELS:\n" + "\n".join(liq["chain"]) + f"\n🏁 TP2 {fmt(tp2)} {hold}D | SUPER {fmt(super_tp)} | MOON {fmt(moon_tp)} | SL {fmt(sl)}\n🧠 {third.get('msg','')}"
            else:
                tp1=liq.get("down_tp1",live*0.95); tp2=liq.get("down_tp2",live*0.9); final_tp=liq.get("final_tp2",live*0.8); super_tp=liq.get("super_tp",live*0.7); moon_tp=liq.get("moon_tp",live*0.5)
                hold=calc_hold_days_dynamic(entry,tp2,atr)
                msg=f"🐳🔴 GREED RSI{sell_thr} BETA{sym} SELL {sym} | {TAG} | RSI30 {rsi30:.0f} (thr {buy_thr}/{sell_thr}) ALIGN {bear}/3 BEAR\n📊 HIERARCHY:\n{hier_txt}\n🐋 {wall.get('whale_log','')}\n💧 LIQUIDITY MAP 6 LEVELS:\n" + "\n".join(liq["chain"]) + f"\n🏁 TP2 {fmt(tp2)} {hold}D | SUPER {fmt(super_tp)} | MOON {fmt(moon_tp)} | SL {fmt(sl)}\n🧠 {third.get('msg','')}"
            tg(msg); print(msg)
            ACTIVE[sym]={"entry":entry,"side":side,"tp1":tp1,"tp2":tp2,"sl":sl,"ts":time.time()}
            results.append(sym)
            if len(results)>=TOP_N_PER_SCAN: break
        except Exception as e:
            print(f"{sym} ERR {e}"); continue
    save_a(); save_c()
    print(f"DONE {len(results)} signals: {results}")
    return results

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--once",action="store_true"); ap.add_argument("--reset",action="store_true")
    args=ap.parse_args()
    if args.reset:
        ACTIVE.clear(); COOLDOWN.clear(); save_a(); save_c()
    scan_once(debug=True)
