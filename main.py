import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

def get_env_clean(*names):
    for n in names:
        v = os.getenv(n)
        if v:
            v = v.strip().replace('"','').replace("'","").replace("\n","").replace("\r","").replace(" ","")
            if len(v) > 3: return v
    return None

TELEGRAM_TOKEN = get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN","TELEGRAM_TOKEN")
TELEGRAM_CHAT = get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID","TELEGRAM_CHAT")

MANUAL_WATCHLIST = ["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]

PICK_HOURS = {"ASIAN":[0,1,2,3],"LONDON":[8,9,10,11],"NEW YORK":[13,14,15,16]}
SIGNAL_COOLDOWN_MIN = 45
MAX_SIGNALS_PER_DAY = 6

try: LAST_ALERT = json.load(open("cooldown.json"))
except: LAST_ALERT = {"count_today":0,"date":datetime.now().strftime('%Y-%m-%d')}

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT,"text":msg,"parse_mode":"Markdown"}, timeout=15)
    except: pass
    print(msg)

def get_killzone():
    h=datetime.now(timezone.utc).hour
    for sess,hours in PICK_HOURS.items():
        if h in hours: return sess,h,True
    return "DEAD ZONE",h,False

def can_send(sym, typ, mins):
    k=f"{sym}_{typ}"; now=time.time(); today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if LAST_ALERT.get("date")!=today: LAST_ALERT["count_today"]=0; LAST_ALERT["date"]=today
    if LAST_ALERT.get("count_today",0)>=MAX_SIGNALS_PER_DAY: return False
    if now-LAST_ALERT.get(k,0)>mins*60:
        LAST_ALERT[k]=now; LAST_ALERT["count_today"]=LAST_ALERT.get("count_today",0)+1
        try: json.dump(LAST_ALERT,open("cooldown.json","w"))
        except: pass
        return True
    return False

def get_trend(df):
    try:
        ema9=df['close'].ewm(span=9).mean().iloc[-1]; ema21=df['close'].ewm(span=21).mean().iloc[-1]; ema50=df['close'].ewm(span=50).mean().iloc[-1]; price=df['close'].iloc[-1]
        if ema9>ema21>ema50 and price>ema9: return "UP"
        if ema9<ema21<ema50 and price<ema9: return "DOWN"
        return "RANGE"
    except: return "RANGE"

def rsi(df,p=14):
    try:
        d=df['close'].diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean(); rs=g/l
        return 100-(100/(1+rs))
    except: return pd.Series([50]*len(df))

def detect_whale(df):
    try:
        o=df['open'].iloc[-1]; c=df['close'].iloc[-1]; h=df['high'].iloc[-1]; l=df['low'].iloc[-1]; body=abs(c-o) or 0.0001
        upper=h-max(o,c); lower=min(o,c)-l
        if lower>body*2.5 and upper<body*0.5: return "BULL_LIQ_GRAB", f"BULL LIQ GRAB {lower/body:.1f}x LONG 9/10"
        if upper>body*2.5 and lower<body*0.5: return "BEAR_LIQ_GRAB", f"BEAR LIQ GRAB {upper/body:.1f}x SHORT 9/10"
        if upper>body*1.5 and lower>body*1.5: return "WHALE_WICK", "WHALE WICK both sides"
        return None,""
    except: return None,""

def other_signal(df5m, df15m, df1h, df4h):
    price=df5m['close'].iloc[-1]; score=0; reasons=[]; buy=0; sell=0
    trend4h=get_trend(df4h); trend1h=get_trend(df1h); trend15m=get_trend(df15m)
    reasons.append(f"4H {trend4h} | 1H {trend1h} | 15M {trend15m}")

    whale_type,whale_msg=detect_whale(df5m)
    if whale_type=="BULL_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}"); buy+=3
    if whale_type=="BEAR_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}"); sell+=3

    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    vol15_r=df15m['volume'].iloc[-1]/(df15m['volume'].rolling(20).mean().iloc[-1] or 1)

    if vol_r>=1.5: score+=2; reasons.append(f"VOL UP x{vol_r:.1f} BUY"); buy+=2
    elif vol_r<=0.6: score+=1; reasons.append(f"VOL DOWN x{vol_r:.1f} SELL"); sell+=1

    if vol15_r>=1.2: score+=1; reasons.append(f"15M VOL CONFIRM x{vol15_r:.1f}")

    # double wick fake
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; body=abs(c-o) or 0.0001; up_r=(h-max(o,c))/body
    if len(df5m)>=2:
        prev_up=(df5m['high'].iloc[-2]-max(df5m['open'].iloc[-2],df5m['close'].iloc[-2]))/(abs(df5m['close'].iloc[-2]-df5m['open'].iloc[-2]) or 0.0001)
        if up_r>1.5 and prev_up>1.5: score-=2; reasons.append("DOUBLE WICK FAKE top")

    # 1/4 HR DIRECTION
    c0,c1,c2=df5m['close'].iloc[-3:].values
    two_up=c0>c1>c2; two_down=c0<c1<c2

    if two_up and trend4h!="DOWN" and trend1h!="DOWN": score+=2; reasons.append(f"5M 2UP + 4H {trend4h} 1H {trend1h} DIR OK BUY"); buy+=2
    elif two_up and (trend4h=="DOWN" or trend1h=="DOWN"): score-=2; reasons.append(f"AGAINST TREND 4H {trend4h} 1H {trend1h} FILTER")

    if two_down and trend4h!="UP" and trend1h!="UP": score+=2; reasons.append(f"5M 2DOWN + 4H {trend4h} 1H {trend1h} DIR OK SELL"); sell+=2
    elif two_down and (trend4h=="UP" or trend1h=="UP"): score-=2; reasons.append(f"AGAINST TREND 4H {trend4h} 1H {trend1h} FILTER")

    low_24=df1h['low'].tail(24).min(); high_24=df1h['high'].tail(24).max()
    loc=(price-low_24)/(high_24-low_24)*100 if high_24>low_24 else 50
    r5=float(rsi(df5m).iloc[-1])

    if loc<20 and r5<40 and trend4h!="DOWN": score+=2; reasons.append(f"BOTTOM {loc:.0f}% RSI {r5:.0f}"); buy+=2
    if loc>80 and r5>60 and trend4h!="UP": score+=2; reasons.append(f"TOP {loc:.0f}% RSI {r5:.0f}"); sell+=2

    score=max(0,min(10,score))
    if buy>=4 and score>=8 and trend4h!="DOWN" and trend1h!="DOWN": decision="BUY NOW"
    elif sell>=4 and score>=8 and trend4h!="UP" and trend1h!="UP": decision="SELL NOW"
    elif score>=5: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,price,vol_r,whale_msg,loc,trend4h,trend1h

def scan():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    kalimoni=(hour_utc+3)%24
    print(f"\n=== SCAN {datetime.now().strftime('%H:%M')} {session} UTC {hour_utc} / Kalimoni {kalimoni} Pick={is_pick} ===")
    for sym in MANUAL_WATCHLIST:
        try:
            df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df4h=pd.DataFrame(ex.fetch_ohlcv(sym,'4h',limit=100),columns=['timestamp','open','high','low','close','volume'])

            decision,score,reasons,price,vol_r,whale_msg,loc,trend4h,trend1h=other_signal(df5m,df15m,df1h,df4h)
            print(f"{sym} | 4H {trend4h} 1H {trend1h} Vol x{vol_r:.1f} | {decision} {score}/10")

            if score>=8 and ("BUY" in decision or "SELL" in decision):
                if is_pick and can_send(sym,f"{decision}_{session}",SIGNAL_COOLDOWN_MIN):
                    emoji="🟢" if "BUY" in decision else "🔴"
                    msg=f"{emoji} *{sym} {decision} Score {score}/10 - {session} PICK*\n4H {trend4h} | 1H {trend1h}\nPrice {price:.5f} Vol x{vol_r:.1f} Loc {loc:.0f}%\n{whale_msg}\n\n" + "\n".join([f"- {r}" for r in reasons])
                    send_telegram(msg)
        except Exception as e:
            print(f"Err {sym} {e}")

if __name__=="__main__":
    while True:
        scan()
        time.sleep(20)
