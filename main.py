import ccxt,requests,os,json,pandas as pd
from datetime import datetime,timedelta
import time
BOT=os.getenv("TELEGRAM_BOT_TOKEN");CHAT=os.getenv("TELEGRAM_CHAT_ID");MIN_SCORE=45
CF="last_alerts.json";TF="trades.json";COOLDOWN_HOURS=2
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
def wh_c(df):
 try:
  avg=df['vol'].iloc[-20:-1].mean();cr=df.iloc[-1];bo=abs(cr['close']-cr['open'])+0.000001;wu=cr['high']-max(cr['open'],cr['close']);wd=min(cr['open'],cr['close'])-cr['low'];rg=cr['high']-cr['low']+0.000001
  if cr['vol']>avg*2.5 and wd>bo*1.5 and wu<bo*0.5:return "WHALE_BUY_WICK",15
  if cr['vol']>avg*2.5 and wu>bo*1.5 and wd<bo*0.5:return "WHALE_SELL_WICK",15
  if cr['vol']>avg*2 and wu>rg*0.6 and cr['close']<cr['open']*1.001:return "SPOOF_SELL",20
  if cr['vol']>avg*2 and wd>rg*0.6 and cr['close']>cr['open']*0.999:return "SPOOF_BUY",20
  return "NO_WHALE",0
 except:return "NO_WHALE",0
def cvd_c(df):
 try:
  mid=(df['high'].iloc[-1]+df['low'].iloc[-1])/2;av=df['vol'].iloc[-20:-1].mean();vt=df['vol'].iloc[-5:].mean()/(av+0.0001);pc=(df['close'].iloc[-1]-df['close'].iloc[-5])/(df['close'].iloc[-5]+0.0001)
  if pc<-0.01 and df['close'].iloc[-1]>mid and vt>1.3:return "CVD_BULL",20
  if pc>0.01 and df['close'].iloc[-1]<mid and vt>1.3:return "CVD_BEAR",20
  return "CVD_NEUT",0
 except:return "CVD_NEUT",0
def vp_c(df):
 try:
  rv=df['vol'].iloc[-3:].mean();pv=df['vol'].iloc[-15:-3].mean()+0.0001;pu=df['close'].iloc[-1]>df['close'].iloc[-5];vu=rv>pv*1.4
  if pu and vu:return "VOL_BULL",15
  if not pu and vu:return "VOL_BEAR",15
  if pu and not vu:return "WEAK_BULL_TRAP",15
  if not pu and not vu:return "WEAK_BEAR_TRAP",15
  return "VOL_NEUT",0
 except:return "VOL_NEUT",0
def liq_c(df):
 try:
  rh=df['high'].iloc[-20:-1].max();rl=df['low'].iloc[-20:-1].min();cr=df.iloc[-1]
  if cr['high']>rh*1.005 and cr['close']<rh:return "LIQ_SELL",20
  if cr['low']<rl*0.995 and cr['close']>rl:return "LIQ_BUY",20
  return "NO_LIQ",0
 except:return "NO_LIQ",0
def hs_c(df):
 try:
  for i in range(-20,-5):
   if df['low'].iloc[i:i+5].min()<df['low'].iloc[i-5:i].min()*0.99 and df['low'].iloc[i:i+5].min()<df['low'].iloc[-10:-5].min()*0.99:return "INV_HS_BULL",25
   if df['high'].iloc[i:i+5].max()>df['high'].iloc[i-5:i].max()*1.01 and df['high'].iloc[i:i+5].max()>df['high'].iloc[-10:-5].max()*1.01:return "HS_BEAR",25
  return "NO_HS",0
 except:return "NO_HS",0
def pat_c(df15,df1h):
 s=0;si=[]
 try:
  h=df15['high'].iloc[-15:];l=df15['low'].iloc[-15:];c=df15['close']
  if l.iloc[2]<l.iloc[5]*0.99 and c.iloc[-1]>c.iloc[-5:-1].max():si.append("W_PAT");s+=15
  if h.iloc[2]>h.iloc[5]*0.99 and c.iloc[-1]<c.iloc[-5:-1].min():si.append("M_PAT");s+=15
  if df1h['close'].iloc[-1]>df1h['high'].iloc[-20:-1].max():si.append("BOS_UP");s+=15
  if df1h['close'].iloc[-1]<df1h['low'].iloc[-20:-1].min():si.append("BOS_DOWN");s+=15
  if df15['low'].iloc[-1]>df15['high'].iloc[-3]:si.append("FVG_BULL");s+=10
  if df15['high'].iloc[-1]<df15['low'].iloc[-3]:si.append("FVG_BEAR");s+=10
 except:pass
 return si,s
def calc(entry,sig,df1h):
 try:
  atr=(df1h['high']-df1h['low']).rolling(14).mean().iloc[-1]
  if atr!=atr or atr==0:atr=entry*0.02
  if sig=="BUY":
   sl=df1h['low'].iloc[-10:].min()*0.998
   if sl>=entry:sl=entry-atr*1.5
   r=entry-sl;return sl,entry+r*1.5,entry+r*3,entry+r*5
  else:
   sl=df1h['high'].iloc[-10:].max()*1.002
   if sl<=entry:sl=entry+atr*1.5
   r=sl-entry;return sl,entry-r*1.5,entry-r*3,entry-r*5
 except:return entry*0.98,entry*1.03,entry*1.06,entry*1.10
def main():
 last=lc();tr=lt();still={}
 ex,exn=ge();btc=btc_t(ex)
 for sym,data in tr.items():
  if (datetime.now()-datetime.fromisoformat(data['time'])).total_seconds()/3600<48:still[sym]=data
 st(still);sent=set()
 for sym in SYMBOLS:
  if sym in last and datetime.now()-last[sym]<timedelta(hours=COOLDOWN_HOURS):continue
  if sym in still or sym in sent:continue
  df1h=fs(ex,sym,"1h",150)
  if df1h is None:continue
  df15=fs(ex,sym,"15m",150)
  if df15 is None:df15=df1h
  df5=fs(ex,sym,"5m",100)
  if df5 is None:df5=df15
  entry=df5['close'].iloc[-1];total=0;trigs=[];sig=None;trigs.append(exn);trigs.append(btc)
  hs,hs_s=hs_c(df1h)
  if hs_s>0:trigs.append(hs);total+=hs_s;sig="BUY" if "BULL" in hs else "SELL"
  li,li_s=liq_c(df15)
  if li_s>0:trigs.append(li);total+=li_s;sig="BUY" if "BUY" in li else "SELL"
  wh,wh_s=wh_c(df15)
  if wh_s>0:trigs.append(wh);total+=wh_s;sig="BUY" if "BUY" in wh else "SELL" if "SELL" in wh else sig
  cv,cv_s=cvd_c(df15)
  if cv_s>0:trigs.append(cv);total+=cv_s;sig="BUY" if "BULL" in cv else "SELL" if "BEAR" in cv else sig
  pt,pt_s=pat_c(df15,df1h)
  for p in pt:trigs.append(p)
  total+=pt_s
  if sig is None:
   if "W_PAT" in pt or "BOS_UP" in pt or "FVG_BULL" in pt:sig="BUY"
   if "M_PAT" in pt or "BOS_DOWN" in pt or "FVG_BEAR" in pt:sig="SELL"
  ob,ob_s=ob_c(df15)
  if ob_s>0:trigs.append(ob);total+=ob_s;sig="BUY" if "BULL" in ob else "SELL" if "BEAR" in ob else sig
  eq,eq_s=eq_c(df15)
  if eq_s>0:trigs.append(eq);total+=eq_s;sig="BUY" if "BULL" in eq else "SELL"
  tu,tu_s=tur_c(df15)
  if tu_s>0:trigs.append(tu);total+=tu_s;sig="BUY" if "BULL" in tu else "SELL"
  ms,ms_s=mss_c(df1h)
  if ms_s>0:trigs.append(ms);total+=ms_s;sig="BUY" if "BULL" in ms else "SELL"
  pd,pd_s=pd_c(df1h);trigs.append(pd);total+=pd_s
  kz,kz_s=kz_c();trigs.append(kz);total+=kz_s
  vp,vp_s=vp_c(df15)
  if vp_s>0:trigs.append(vp);total+=vp_s
  r=rsi(df15['close']).iloc[-1]
  if r<30:trigs.append("RSI_OS");total+=15;sig="BUY" if sig is None else sig
  if r>70:trigs.append("RSI_OB");total+=15;sig="SELL" if sig is None else sig
  # FIX OPPOSITE SIGNALS
  if sig=="SELL":
   if "DISCOUNT_BULL" in trigs:trigs.remove("DISCOUNT_BULL");total-=10
   if "RSI_OS" in trigs:trigs.remove("RSI_OS");total-=15
   if "BULL_OB" in trigs:trigs.remove("BULL_OB");total-=20
   if "INV_HS_BULL" in trigs:trigs.remove("INV_HS_BULL");total-=25
  if sig=="BUY":
   if "PREMIUM_BEAR" in trigs:trigs.remove("PREMIUM_BEAR");total-=10
   if "RSI_OB" in trigs:trigs.remove("RSI_OB");total-=15
   if "BEAR_OB" in trigs:trigs.remove("BEAR_OB");total-=20
   if "HS_BEAR" in trigs:trigs.remove("HS_BEAR");total-=25
  is_bear=("LIQ_SELL" in trigs and "SPOOF_SELL" in trigs)
  is_bull=("LIQ_BUY" in trigs and "SPOOF_BUY" in trigs)
  if is_bear and sig=="SELL":sig="BUY";trigs.append("REAL_TRAP_BULL");total=75
  if is_bull and sig=="BUY":sig="SELL";trigs.append("REAL_TRAP_BEAR");total=75
  if total>100:total=100
  if total<0:total=0
  if total>=MIN_SCORE and sig is not None:
   if btc=="BTC_BEAR" and sig=="BUY" and total<60:continue
   if not filt(sym,"SHORT" if sig=="SELL" else "LONG"):continue
   sl,tp1,tp2,tp3=calc(entry,sig,df1h);clean=sym.replace(":USDT","")
   # FIX QUALITY - ONLY REAL TRAP
   if "REAL_TRAP" in ",".join(trigs):q="TRAP-TAKE!"
   elif total<55:q="WEAK-SKIP"
   elif total<70:q="GOOD"
   elif total<85:q="STRONG"
   else:q="MAX"
   dc=gc(sym)
   msg=f"{clean} {sig} {total}/100 {q} Price {entry:.6f} ({dc:+.2f}%) SL {sl:.6f} TP1 {tp1:.6f} TP2 {tp2:.6f} TP3 {tp3:.6f} {','.join(trigs[:8])}"
   tg(msg);last[sym]=datetime.now();sc(last);sent.add(sym);still[sym]={"type":sig,"entry":entry,"time":datetime.now().isoformat()};st(still)
  time.sleep(1)
if __name__=="__main__":main()
