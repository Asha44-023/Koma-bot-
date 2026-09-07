import os, time, requests, pandas as pd
from datetime import datetime

COINS = ["KOMAUSDT","LABUSDT","HEIUSDT","SIRENUSDT","GRASSUSDT","VELVETUSDT"]
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT_ID,"text":m,"parse_mode":"Markdown"}, timeout=10)
    except: print(m)

def klines(sym, interval, lim=200):
    try:
        url=f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={lim}"
        r=requests.get(url,timeout=10).json()
        df=pd.DataFrame(r,columns=["t","o","h","l","c","v","ct","qv","tr","tb","tq","ig"])
        for k in ["o","h","l","c","v"]: df[k]=df[k].astype(float)
        return df
    except: return None

def ema(s,p): return s.ewm(span=p,adjust=False).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.where(d>0,0).rolling(p).mean(); l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/l))
def bos(df):
    if len(df)<25: return None
    if df["c"].iloc[-1]>df["h"].iloc[-21:-1].max(): return "BOS_BULL"
    if df["c"].iloc[-1]<df["l"].iloc[-21:-1].min(): return "BOS_BEAR"
    return None
def dbl(df):
    if len(df)<40: return None
    rh=df["h"].iloc[-15:].nlargest(2)
    if len(rh)==2 and abs(rh.iloc[0]-rh.iloc[1])/rh.iloc[0]<0.015 and df["c"].iloc[-1]<df["c"].iloc[-5]: return "DOUBLE_TOP_BEARISH"
    rl=df["l"].iloc[-15:].nsmallest(2)
    if len(rl)==2 and abs(rl.iloc[0]-rl.iloc[1])/rl.iloc[0]<0.015 and df["c"].iloc[-1]>df["c"].iloc[-5]: return "DOUBLE_BOTTOM_BULLISH"
    return None

def analyze(sym):
    df5=klines(sym,"5m",200); df15=klines(sym,"15m",200); df1h=klines(sym,"1h",200); df4h=klines(sym,"4h",200)
    if None in [df5,df15,df1h,df4h]: return None
    price=df5["c"].iloc[-1]
    dir4h="BULL" if ema(df4h["c"],50).iloc[-1]>ema(df4h["c"],200).iloc[-1] else "BEAR"
    b1h=bos(df1h); st1h=b1h if b1h else ("BULL" if df1h["c"].iloc[-1]>ema(df1h["c"],50).iloc[-1] else "BEAR")
    e9_5=ema(df5["c"],9).iloc[-1]; e21_5=ema(df5["c"],21).iloc[-1]; e9_15=ema(df15["c"],9).iloc[-1]; e21_15=ema(df15["c"],21).iloc[-1]
    r5=rsi(df5["c"]).iloc[-1]; vavg=df5["v"].iloc[-21:-1].mean(); vnow=df5["v"].iloc[-1]; vsp=vnow/vavg if vavg>0 else 1
    pat=dbl(df15); b5=bos(df5)
    bull=0; rsn=[]
    if dir4h=="BULL": bull+=1; rsn.append("4H BULL")
    if "BULL" in st1h: bull+=1; rsn.append(f"1H {st1h}")
    if e9_5>e21_5: bull+=1; rsn.append("5m EMA9>21")
    if e9_15>e21_15: bull+=1
    if 45<r5<68: bull+=1; rsn.append(f"RSI {r5:.1f}")
    if vsp>1.5: bull+=2; rsn.append(f"VOL x{vsp:.1f}")
    if b5=="BOS_BULL": bull+=2; rsn.append("BOS 5m BULL")
    if pat and "BULLISH" in pat: bull+=2; rsn.append(pat)
    bear=0
    if dir4h=="BEAR": bear+=1
    if "BEAR" in st1h: bear+=1
    if e9_5<e21_5: bear+=1
    if e9_15<e21_15: bear+=1
    if vsp>1.5: bear+=2
    if b5=="BOS_BEAR": bear+=2
    if pat and "BEARISH" in pat: bear+=2
    sig=None
    if bull>=6 and dir4h=="BULL": sig="BUY"
    elif bear>=6 and dir4h=="BEAR": sig="SELL"
    if sig:
        atr=(df15["h"].iloc[-14:]-df15["l"].iloc[-14:]).mean()
        if sig=="BUY": entry=price; sl=entry-atr*1.5; tp1=entry+atr*2; tp2=entry+atr*3.5; tp3=entry+atr*5
        else: entry=price; sl=entry+atr*1.5; tp1=entry-atr*2; tp2=entry-atr*3.5; tp3=entry-atr*5
        risk=abs(entry-sl)/entry*100; rew=abs(tp1-entry)/entry*100
        return {"sym":sym,"sig":sig,"price":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3,"risk":risk,"rew":rew,"r5":r5,"vsp":vsp,"rsn":rsn,"dir4h":dir4h,"st1h":st1h,"pat":pat,"b5":b5}
    return None

found=False
for c in COINS:
    r=analyze(c); time.sleep(0.4)
    if r:
        found=True
        tg(f"*{r['sym']} {r['sig']} SIGNAL* | 5m/15m ENTRY\n\nEntry: `{r['price']:.6f}`\nSL: `{r['sl']:.6f}` (-{r['risk']:.2f}%)\nTP1: `{r['tp1']:.6f}` (+{r['rew']:.2f}%)\nTP2: `{r['tp2']:.6f}`\nTP3: `{r['tp3']:.6f}`\n\n4H: {r['dir4h']} | 1H: {r['st1h']}\nBOS: {r['b5']} | Pattern: {r['pat']}\nRSI: {r['r5']:.1f} | VOL: x{r['vsp']:.2f}\nReasons: {', '.join(r['rsn'])}\nTime: {datetime.utcnow().strftime('%H:%M UTC')}")
if not found:
    tg(f"SCAN {datetime.utcnow().strftime('%H:%M UTC')} | Checked {', '.join(COINS)} | No A+ setup. Bot alive - 4H/1H/5m/BOS/RSI/Vol scanned. Next scan in 15m.")
