import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

def get_env_clean(*names):
    for n in names:
        v=os.getenv(n)
        if v:
            v=v.strip().replace('"','').replace("'","").replace("\n","").replace("\r","").replace(" ","")
            if len(v)>3: return v
    return None

TELEGRAM_TOKEN=get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN","TELEGRAM_TOKEN")
TELEGRAM_CHAT=get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID","TELEGRAM_CHAT")

MANUAL_WATCHLIST=["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
PICK_HOURS={"ASIAN":[0,1],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=120
MAX_SIGNALS_PER_DAY=2

try: LAST_ALERT=json.load(open("cooldown_other.json"))
except: LAST_ALERT={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d')}

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT,"text":msg,"parse_mode":"Markdown"}, timeout=15)
    except: pass
    print(msg)

def get_killzone():
    h=datetime.now(timezone.utc).hour
    for sess,hours in PICK_HOURS.items():
        if h in hours: return sess,h,True
    return "DEAD ZONE",h,False

def can_send(sym,typ,mins):
    k=f"{sym}_{typ}"; now=time.time(); today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if LAST_ALERT.get("date")!=today: LAST_ALERT["count_today"]=0; LAST_ALERT["date"]=today
    if LAST_ALERT.get("count_today",0)>=MAX_SIGNALS_PER_DAY: return False
    if now-LAST_ALERT.get(k,0)>mins*60:
        LAST_ALERT[k]=now; LAST_ALERT["count_today"]+=1
        try: json.dump(LAST_ALERT,open("cooldown_other.json","w"))
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

def other_signal(df5m,df15m,df1h,df4h):
    price=df5m['close'].iloc[-1]; score=0; reasons=[]; buy=0; sell=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001; up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body

    # FIXED: REAL TRAP ONLY >3.0x BOTH - was 2.5x
    if low_r>=3.0 and up_r>=3.0:
        return "WAIT",2,[f"⚠️ BOTH SIDES Up {up_r:.1f}x Low {low_r:.1f}x - NO TRADE"],price,0,"",50,"RANGE","RANGE",up_r,low_r

    trend4h=get_trend(df4h); trend1h=get_trend(df1h); trend15m=get_trend(df15m)
    reasons.append(f"4H {trend4h} | 1H {trend1h} | 15M {trend15m}")

    # FIXED BOTH SIDES 1.2x = 3 POINTS - WILL CATCH 0.016575 -> 0.018
    if low_r>=1.2:
        score+=3; reasons.append(f"🐋 LOW GRAB {low_r:.1f}x LONG"); buy+=3
    elif low_r>=0.8:
        score+=2; reasons.append(f"Low wick {low_r:.1f}x"); buy+=1

    if up_r>=1.2:
        score+=3; reasons.append(f"🐋 HIGH GRAB {up_r:.1f}x SHORT"); sell+=3
    elif up_r>=0.8:
        score+=2; reasons.append(f"High wick {up_r:.1f}x"); sell+=1

    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    # FIXED: PERP WICK EXCEPTION 1.2x BOTH SIDES
    if (low_r>=1.2 or up_r>=1.2) and vol_r<1.0:
        vol_r=1.6
        reasons.append(f"PERP WICK EXCEPTION vol->1.6x")

    if vol_r>=1.2: score+=2; reasons.append(f"VOL UP x{vol_r:.1f}"); buy+=1; sell+=1
    elif vol_r>=1.0: score+=1; reasons.append(f"VOL x{vol_r:.1f}")

    c0,c1,c2=df5m['close'].iloc[-3:].values
    if c0>c1>c2 and trend4h!="DOWN" and trend1h!="DOWN": score+=2; reasons.append("2UP + TREND OK"); buy+=2
    if c0<c1<c2 and trend4h!="UP" and trend1h!="UP": score+=2; reasons.append("2DOWN + TREND OK"); sell+=2

    low_24=df1h['low'].tail(24).min(); high_24=df1h['high'].tail(24).max()
    loc=(price-low_24)/(high_24-low_24)*100 if high_24>low_24 else 50
    r5=float(rsi(df5m).iloc[-1])
    if loc<20 and r5<40 and trend4h!="DOWN": score+=2; reasons.append(f"BOTTOM {loc:.0f}% RSI {r5:.0f}"); buy+=2
    if loc>80 and r5>60 and trend4h!="UP": score+=2; reasons.append(f"TOP {loc:.0f}% RSI {r5:.0f}"); sell+=2

    score=max(0,min(10,score))
    # FIXED: BOTH SIDES BUY>=3 SELL>=3 SCORE 6 (was 7)
    if buy>=3 and score>=6 and trend4h!="DOWN" and trend1h!="DOWN": decision="BUY NOW"
    elif sell>=3 and score>=6 and trend4h!="UP" and trend1h!="UP": decision="SELL NOW"
    elif score>=4: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,price,vol_r,"",loc,trend4h,trend1h,up_r,low_r

def scan_one(args):
    sym,ex,session,is_pick=args
    try:
        df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df4h=pd.DataFrame(ex.fetch_ohlcv(sym,'4h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        decision,score,reasons,price,vol_r,_,loc,trend4h,trend1h,up_r,low_r=other_signal(df5m,df15m,df1h,df4h)
        print(f"{sym} {price:.5f} | 4H {trend4h} 1H {trend1h} Up {up_r:.1f} Low {low_r:.1f} | {decision} {score}/10")
        if score>=6 and ("BUY" in decision or "SELL" in decision):
            if is_pick and can_send(sym,f"{decision}_{session}",SIGNAL_COOLDOWN_MIN):
                if "BUY" in decision:
                    sl=price*0.992; tp1=price*1.012; tp2=price*1.025
                else:
                    sl=price*1.008; tp1=price*0.988; tp2=price*0.975
                risk=abs(price-sl)/price*100; rew1=abs(tp1-price)/price*100; rew2=abs(tp2-price)/price*100
                emoji="🟢" if "BUY" in decision else "🔴"
                msg=f"{emoji} *{sym} {decision} {score}/10 - {session}*\nPrice {price:.5f}\nSL {sl:.5f} (-{risk:.2f}%)\nTP1 {tp1:.5f} (+{rew1:.2f}%) TP2 {tp2:.5f} (+{rew2:.2f}%)\n4H {trend4h} | Vol x{vol_r:.1f} | Up {up_r:.1f}x Low {low_r:.1f}x\n"+"\n".join([f"- {r}" for r in reasons])
                send_telegram(msg)
    except Exception as e: print(f"Err {sym} {e}")

def scan():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== OTHER PERP SCAN {session} UTC {hour_utc} Pick={is_pick} ===")
    tasks=[(s,ex,session,is_pick) for s in MANUAL_WATCHLIST]
    with ThreadPoolExecutor(max_workers=5) as ex2: ex2.map(scan_one,tasks)

if __name__=="__main__": scan()
