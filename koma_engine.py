import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

def get_env_clean(*names):
    for n in names:
        v=os.getenv(n)
        if v:
            v=v.strip().replace('"','').replace("'","").replace("\n","").replace("\r","").replace(" ","")
            if len(v)>3: return v
    return None

TELEGRAM_TOKEN=get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN","TELEGRAM_TOKEN")
TELEGRAM_CHAT=get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID","TELEGRAM_CHAT")

SYMBOL="KOMA/USDT:USDT"
PICK_HOURS={"ASIAN":[0,1],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=90
MAX_SIGNALS_PER_DAY=3

try: LAST_ALERT=json.load(open("cooldown_koma.json"))
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
        try: json.dump(LAST_ALERT,open("cooldown_koma.json","w"))
        except: pass
        return True
    return False

def rsi(df,p=14):
    try:
        d=df['close'].diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean(); rs=g/l
        return 100-(100/(1+rs))
    except: return pd.Series([50]*len(df))

def get_wick_levels(df5m):
    try:
        high_20=df5m['high'].tail(20).max()
        low_20=df5m['low'].tail(20).min()
        mid=(high_20+low_20)/2
        ceil=high_20
        floor=low_20
        flip=df5m['close'].tail(20).median()
        return ceil,floor,mid,flip
    except:
        p=df5m['close'].iloc[-1]
        return p*1.02,p*0.98,p,p

def check_koma(df5m,df15m,df1h):
    price=df5m['close'].iloc[-1]
    CEIL,FLOOR,MID,FLIP=get_wick_levels(df5m)
    score=0; reasons=[]; buy=0; sell=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001
    up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body

    # PERP EXCEPTION: Only block if BOTH sides >2.5x (real trap)
    if low_r>=2.5 and up_r>=2.5:
        return "WAIT",2,[f"⚠️ BOTH SIDES WHALE Up {up_r:.1f}x Low {low_r:.1f}x - NO TRADE"],CEIL,FLOOR,MID,FLIP,price,up_r,low_r

    if low_r>=2.5:
        score+=3; reasons.append(f"LOW GRAB {low_r:.1f}x FLOOR {FLOOR:.5f} LONG"); buy+=3
    elif low_r>=1.2:
        score+=2; reasons.append(f"LOW WICK {low_r:.1f}x"); buy+=1

    if up_r>=2.5:
        score+=3; reasons.append(f"HIGH GRAB {up_r:.1f}x CEIL {CEIL:.5f} SHORT"); sell+=3
    elif up_r>=1.2:
        score+=2; reasons.append(f"HIGH WICK {up_r:.1f}x"); sell+=1

    if abs(price-FLIP)/FLIP<0.006:
        score+=1; reasons.append(f"AT FLIP {FLIP:.5f}")

    r5=float(rsi(df5m).iloc[-1])
    if r5<35: score+=2; reasons.append(f"RSI OS {r5:.0f} BUY"); buy+=2
    elif r5>65: score+=2; reasons.append(f"RSI OB {r5:.0f} SELL"); sell+=2
    else: score+=1; reasons.append(f"RSI {r5:.0f}")

    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    if vol_r>=1.2: score+=2; reasons.append(f"VOL REAL x{vol_r:.1f}")
    elif vol_r>=1.0: score+=1; reasons.append(f"VOL x{vol_r:.1f}")

    # MEXC PERP FIX: Big wick = valid even with low vol
    if (low_r>=2.5 or up_r>=2.5) and vol_r<1.0:
        reasons.append(f"PERP WICK EXCEPTION Vol {vol_r:.1f}x ignored"); score+=1

    score=max(0,min(10,score))
    if buy>=3 and score>=6 and buy>sell: decision="BUY NOW"
    elif sell>=3 and score>=6 and sell>buy: decision="SELL NOW"
    elif score>=4: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r

def scan():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    kalimoni=(hour_utc+3)%24
    print(f"\n=== KOMA SCAN {session} UTC {hour_utc} / Kalimoni {kalimoni} Pick={is_pick} ===")
    try:
        df5m=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df15m=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1h=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r=check_koma(df5m,df15m,df1h)
        print(f"KOMA {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x | {decision} {score}/10")

        if score>=6 and ("BUY" in decision or "SELL" in decision) and is_pick and can_send(SYMBOL,f"{decision}_{session}",SIGNAL_COOLDOWN_MIN):
            if "BUY" in decision:
                sl_raw = FLOOR*0.999
                sl = max(sl_raw, price*0.992) # cap -0.8%
                tp1 = price*1.012
                tp2 = FLIP if FLIP>price else price*1.025
                emoji="🟢"
            else:
                sl_raw = CEIL*1.001
                sl = min(sl_raw, price*1.008) # cap +0.8%
                tp1 = price*0.988
                tp2 = FLIP if FLIP<price else price*0.975
                emoji="🔴"

            risk_pct = abs(price-sl)/price*100
            reward1 = abs(tp1-price)/price*100
            reward2 = abs(tp2-price)/price*100

            msg=(
                f"{emoji} *{SYMBOL} {decision} Score {score}/10 - {session} PICK*\n"
                f"Price {price:.5f}\n"
                f"Ceil {CEIL:.5f} Floor {FLOOR:.5f} Flip {FLIP:.5f}\n"
                f"Up {up_r:.1f}x Low {low_r:.1f}x {kalimoni}:00 Kalimoni\n\n"
                f"*TRADE PLAN:*\n"
                f"SL {sl:.5f} (-{risk_pct:.2f}%)\n"
                f"TP1 {tp1:.5f} (+{reward1:.2f}%)\n"
                f"TP2 {tp2:.5f} (+{reward2:.2f}%)\n\n"
                +"\n".join([f"- {r}" for r in reasons])
            )
            send_telegram(msg)
    except Exception as e:
        print(f"Err KOMA {e}")

if __name__=="__main__":
    scan()
