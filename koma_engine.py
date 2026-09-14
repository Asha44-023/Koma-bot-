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

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT,"text":msg,"parse_mode":"Markdown"}, timeout=15)
    except: pass
    print(msg)

PICK_HOURS={"ASIAN":[0,1,2,3],"LONDON":[8,9,10,11],"NEW YORK":[13,14,15,16]}
SIGNAL_COOLDOWN_MIN=30
MAX_SIGNALS_PER_DAY=10
KOMA_SYMBOLS=["KOMA/USDT:USDT"]

try: LAST_ALERT=json.load(open("cooldown_koma.json"))
except: LAST_ALERT={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d')}

def get_killzone_pick():
    h=datetime.now(timezone.utc).hour
    for sess,hours in PICK_HOURS.items():
        if h in hours: return sess,h,True
    return "DEAD ZONE",h,False

def can_send_killzone(sym):
    session,hour_utc,is_pick=get_killzone_pick()
    if not is_pick: return False,session
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if LAST_ALERT.get("date")!=today: LAST_ALERT["count_today"]=0; LAST_ALERT["date"]=today
    if LAST_ALERT.get("count_today",0)>=MAX_SIGNALS_PER_DAY: return False,session
    if time.time()-LAST_ALERT.get(f"{sym}_SIGNAL",0) < SIGNAL_COOLDOWN_MIN*60: return False,session
    return True,session

def mark_sent(sym):
    LAST_ALERT[f"{sym}_SIGNAL"]=time.time()
    LAST_ALERT["count_today"]=LAST_ALERT.get("count_today",0)+1
    try: json.dump(LAST_ALERT,open("cooldown_koma.json","w"))
    except: pass

def rsi(df,p=14):
    d=df['close'].diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean()
    return 100-(100/(1+g/l))

def get_wick_levels(df5m):
    recent=df5m.tail(50).copy()
    recent['body']=abs(recent['close']-recent['open'])
    recent['up_wick']=recent['high']-recent[['open','close']].max(axis=1)
    recent['low_wick']=recent[['open','close']].min(axis=1)-recent['low']
    recent['up_r']=recent['up_wick']/(recent['body']+0.000001)
    recent['low_r']=recent['low_wick']/(recent['body']+0.000001)
    tops=recent[recent['up_r']>1.5]['high']; bots=recent[recent['low_r']>1.5]['low']
    CEIL=tops.max() if len(tops)>0 else recent['high'].max()
    FLOOR=bots.min() if len(bots)>0 else recent['low'].min()
    MID=(CEIL+FLOOR)/2; FLIP=(tops.median()+bots.median())/2 if len(tops)>0 and len(bots)>0 else MID
    return CEIL,FLOOR,MID,FLIP

def check_koma(df5m,df15m,df1h):
    price=df5m['close'].iloc[-1]; CEIL,FLOOR,MID,FLIP=get_wick_levels(df5m)
    score=0; reasons=[]; buy=0; sell=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001; up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
    if low_r>2.5: score+=3; reasons.append(f"LOW GRAB {low_r:.1f}x FLOOR {FLOOR:.5f} LONG"); buy+=3
    if up_r>2.5: score+=3; reasons.append(f"HIGH GRAB {up_r:.1f}x CEIL {CEIL:.5f} SHORT"); sell+=3
    if abs(price-FLIP)/FLIP<0.004: score+=2; reasons.append(f"AT FLIP {FLIP:.5f}"); buy+=1; sell+=1
    r5=rsi(df5m).iloc[-1]
    if r5<30: score+=2; reasons.append(f"RSI OS {r5:.0f} BUY"); buy+=2
    elif r5>70: score+=2; reasons.append(f"RSI OB {r5:.0f} SELL"); sell+=2
    else: score+=1; reasons.append(f"RSI {r5:.0f}")
    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    if vol_r>=1.2: score+=1; reasons.append(f"VOL UP x{vol_r:.1f}")
    score=max(0,min(10,score))
    if buy>=2 and score>=6 and buy>=sell: decision="BUY NOW"
    elif sell>=2 and score>=6 and sell>buy: decision="SELL NOW"
    elif score>=4: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r

def scan_one(sym, ex):
    df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
    df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
    df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
    session,hour_utc,is_pick=get_killzone_pick(); kalimoni=(hour_utc+3)%24
    decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r=check_koma(df5m,df15m,df1h)
    print(f"{sym} {session} {kalimoni}:00 | {price:.5f} | {decision} {score}/10")
    if score>=6 and ("BUY" in decision or "SELL" in decision):
        ok,sess=can_send_killzone(sym)
        if ok:
            emoji="🟢" if "BUY" in decision else "🔴"
            msg=f"{emoji} *{sym} {decision} Score {score}/10 - {sess} PICK*\nPrice {price:.5f}\nCeil {CEIL:.5f} Floor {FLOOR:.5f} Flip {FLIP:.5f}\nUp {up_r:.1f}x Low {low_r:.1f}x {kalimoni}:00 Kalimoni\n\n" + "\n".join([f"- {r}" for r in reasons])
            send_telegram(msg); mark_sent(sym)

if __name__=="__main__":
    ex=ccxt.mexc({'enableRateLimit': True})
    session,hour_utc,is_pick=get_killzone_pick()
    print(f"KOMA SCAN {session} UTC {hour_utc} Kalimoni {(hour_utc+3)%24} Pick {is_pick}")
    for sym in KOMA_SYMBOLS: scan_one(sym, ex)
    print("KOMA DONE")
