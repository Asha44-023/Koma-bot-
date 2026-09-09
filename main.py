import ccxt,requests,os,json,pandas as pd
from datetime import datetime,timedelta
import time
BOT=os.getenv("TELEGRAM_BOT_TOKEN")
CHAT=os.getenv("TELEGRAM_CHAT_ID")
MIN_SCORE=55
CF="last_alerts.json"
TF="trades.json"
COOLDOWN_HOURS=6
SYMBOLS=["VELVET/USDT:USDT","KOMA/USDT:USDT","GRASS/USDT:USDT","SIREN/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT"]
def gc(s):
 try:
  c=s.replace("/","").replace(":USDT","").replace(":","")
  if not c.endswith("USDT"):c+="USDT"
  return float(requests.get(f"https://api.mexc.com/api/v3/ticker/24hr?symbol={c}",timeout=5).json().get('priceChangePercent',0))
 except:return 0.0
def filt(sym,typ):
 d=gc(sym)
 if typ=="SHORT" and d>8:return False
 if typ=="LONG" and d<-8:return False
 if abs(d)>10:return (d>10 and typ=="LONG") or (d<-10 and typ=="SHORT")
 return True
def tg(m):
 try:requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":m,"parse_mode":"Markdown"},timeout=15)
 except:pass
def lc():
 try:
  with open(CF,"r") as f:return {k:datetime.fromisoformat(v) for k,v in json.load(f).items()}
 except:return {}
def sc(d):
 try:
  with open(CF,"w") as f:json.dump({k:v.isoformat() for k,v in d.items()},f)
 except:pass
def lt():
 try:
  with open(TF,"r") as f:return json.load(f)
 except:return {}
def st(d):
 try:
  with open(TF,"w") as f:json.dump(d,f,default=str)
 except:pass
def rsi(c,p=14):
 d=c.diff();g=d.where(d>0,0).rolling(p).mean();l=-d.where(d<0,0).rolling(p).mean();return 100-(100/(1+g/l))
def fs(ex,sym,tf,lim):
 try:
  o=ex.fetch_ohlcv(sym,tf,limit=lim)
  if not o or len(o)<60:return None
  df=pd.DataFrame(o,columns=['ts','open','high','low','close','vol'])
  for col in ['close','high','low','open','vol']:df[col]=df[col].astype(float)
  return df
 except:return None
def ge():
 try:ex=ccxt.mexc({'enableRateLimit':True,'options':{'defaultType':'swap'}});ex.fetch_ticker("BTC/USDT:USDT");return ex,"MEXC-FUT"
 except:
  try:ex=ccxt.kucoin({'enableRateLimit':True,'options':{'defaultType':'swap'}});ex.fetch_ticker("BTC/USDT:USDT");return ex,"KUCOIN-FUT"
  except:ex=ccxt.mexc({'enableRateLimit':True});return ex,"MEXC-FUT"
def btc_t(ex):
 try:
  df=fs(ex,"BTC/USDT:USDT","4h",50)
  if df is None:return "BTC_NEUTRAL"
  e50=df['close'].ewm(span=50).mean().iloc[-1];e200=df['close'].ewm(span=200).mean().iloc[-1]
  if df['close'].iloc[-1]>e50>e200:return "BTC_BULL"
  if df['close'].iloc[-1]<e50<e200:return "BTC_BEAR"
  return "BTC_NEUTRAL"
 except:return "BTC_NEUTRAL"
def ob_c(df):
 try:
  for i in range(-10,-3):
   if df['close'].iloc[i]<df['open'].iloc[i] and df['close'].iloc[-1]>df['high'].iloc[i] and df['low'].iloc[i]<=df['low'].iloc[-5:].min()*1.01:return "BULL_OB",20
   if df['close'].iloc[i]>df['open'].iloc[i] and df['close'].iloc[-1]<df['low'].iloc[i] and df['high'].iloc[i]>=df['high'].iloc[-5:].max()*0.99:return "BEAR_OB",20
  return "NO_OB",0
 except:return "NO_OB",0
def eq_c(df):
 try:
  lo=df['low'].iloc[-20:-1];hi=df['high'].iloc[-20:-1]
  if abs(lo.min()-sorted(lo)[1])/lo.min()<0.002 and df['low'].iloc[-1]<lo.min()*0.998 and df['close'].iloc[-1]>lo.min():return "EQ_LOWS_BULL",25
  if abs(hi.max()-sorted(hi,reverse=True)[1])/hi.max()<0.002 and df['high'].iloc[-1]>hi.max()*1.002 and df['close'].iloc[-1]<hi.max():return "EQ_HIGHS_BEAR",25
  return "NO_EQ",0
 except:return "NO_EQ",0
def tur_c(df):
 try:
  hh=df['high'].iloc[-20:-1].max();ll=df['low'].iloc[-20:-1].min()
  if df['high'].iloc[-2]>hh and df['close'].iloc[-1]<hh and df['close'].iloc[-1]<df['open'].iloc[-1]:return "TURTLE_BEAR",25
  if df['low'].iloc[-2]<ll and df['close'].iloc[-1]>ll and df['close'].iloc[-1]>df['open'].iloc[-1]:return "TURTLE_BULL",25
  return "NO_TURTLE",0
 except:return "NO_TURTLE",0
def mss_c(df):
 try:
  if df['close'].iloc[-1]>df['high'].iloc[-20:-1].max() and df['close'].iloc[-3]<df['low'].iloc[-10:-3].min():return "MSS_BULL",20
  if df['close'].iloc[-1]<df['low'].iloc[-20:-1].min() and df['close'].iloc[-3]>df['high'].iloc[-10:-3].max():return "MSS_BEAR",20
  return "NO_MSS",0
 except:return "NO_MSS",0
def pd_c(df):
 try:
  h=df['high'].iloc[-50:].max();l=df['low'].iloc[-50:].min();c=df['close'].iloc[-1]
  if c<l+(h-l)*0.25:return "DISCOUNT_BULL",10
  if c>h-(h-l)*0.25:return "PREMIUM_BEAR",10
  return "EQ_ZONE",0
 except:return "EQ_ZONE",0
def kz_c():
 try:
  h=datetime.utcnow().hour
  if 8<=h<=11:return "LONDON_KZ",5
  if 13<=h<=16:return "NY_KZ",10
  if 0<=h<=2:return "ASIAN_LOW",-5
  return "NO_KZ",0
 except:return "NO_KZ",0
def score(df,ex):
 s=50;re=[]
 try:
  rs=rsi(df['close']).iloc[-1]
  if rs<30:s+=15;re.append(f"RSI_OVERSOLD_{rs:.1f}")
  elif rs>70:s+=15;re.append(f"RSI_OVERB_B_{rs:.1f}")
  else:re.append(f"RSI_{rs:.1f}")
  ema20=df['close'].ewm(span=20).mean().iloc[-1];ema50=df['close'].ewm(span=50).mean().iloc[-1]
  if df['close'].iloc[-1]>ema20>ema50:s+=10;re.append("EMA_BULL")
  elif df['close'].iloc[-1]<ema20<ema50:s+=10;re.append("EMA_BEAR")
  vol_avg=df['vol'].iloc[-20:-1].mean()
  if df['vol'].iloc[-1]>vol_avg*1.5:s+=10;re.append("VOL_SPIKE")
  ob,sc_ob=ob_c(df);s+=sc_ob;re.append(ob)
  eq,sc_eq=eq_c(df);s+=sc_eq;re.append(eq)
  tu,sc_tu=tur_c(df);s+=sc_tu;re.append(tu)
  ms,sc_ms=mss_c(df);s+=sc_ms;re.append(ms)
  pd,sc_pd=pd_c(df);s+=sc_pd;re.append(pd)
  kz,sc_kz=kz_c();s+=sc_kz;re.append(kz)
  bt=btc_t(ex);re.append(bt)
  if bt=="BTC_BULL" and "BULL" in "".join(re):s+=10
  if bt=="BTC_BEAR" and "BEAR" in "".join(re):s+=10
 except:pass
 s=max(0,min(100,s));return s,re
def main():
 ex,exn=ge();ca=lc();tr=lt();now=datetime.utcnow();tg(f"🚀 V7 STARTED on {exn} | MIN_SCORE={MIN_SCORE} | COOLDOWN={COOLDOWN_HOURS}h")
 for sym in SYMBOLS:
  try:
   df=fs(ex,sym,"15m",200)
   if df is None:continue
   sc_,re=score(df,ex)
   if sc_<MIN_SCORE:continue
   typ="LONG" if any(x in "".join(re) for x in ["BULL","OVERSOLD"]) else "SHORT" if any(x in "".join(re) for x in ["BEAR","OVERB_B"]) else "NONE"
   if typ=="NONE":continue
   if not filt(sym,typ):continue
   key=f"{sym}_{typ}"
   if key in ca and (now-ca[key])<timedelta(hours=COOLDOWN_HOURS):continue
   price=df['close'].iloc[-1]
   sl=price*0.97 if typ=="LONG" else price*1.03
   tp=price*1.06 if typ=="LONG" else price*0.94
   strength="WEAK" if sc_<55 else "STRONG" if sc_<70 else "MAX"
   if strength=="WEAK":continue
   msg=f"🔥 *{sym} {typ} {strength} ({sc_}/100)*\nPrice: `{price:.5f}`\nSL: `{sl:.5f}` | TP: `{tp:.5f}`\nReasons: {', '.join(re[:5])}\nExchange: {exn}\nTime: {now.strftime('%H:%M UTC')}"
   tg(msg);ca[key]=now;sc(ca)
   if key not in tr:tr[key]={"entry":price,"sl":sl,"tp":tp,"time":now.isoformat(),"score":sc_,"type":typ}
   st(tr)
  except Exception as e:print(f"ERR {sym}: {e}");time.sleep(1)
if __name__=="__main__":main()
