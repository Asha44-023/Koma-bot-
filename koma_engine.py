import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

def get_env_clean(*names):
    for n in names:
        v=os.getenv(n)
        if v:
            v=v.strip().replace('"','').replace("'","").replace("\n","").replace("\r","").replace(" ","")
            if len(v)>3:
                return v
    return None

TELEGRAM_TOKEN=get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN","TELEGRAM_TOKEN")
TELEGRAM_CHAT=get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID","TELEGRAM_CHAT")

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT,"text":msg,"parse_mode":"Markdown"}, timeout=15)
    except:
        pass
    print(msg)

PICK_HOURS={"ASIAN":[0,1,2,3],"LONDON":[8,9,10,11],"NEW YORK":[13,14,15,16]}
SIGNAL_COOLDOWN_MIN=45
MAX_SIGNALS_PER_DAY=6
KOMA_SYMBOLS=["KOMA/USDT:USDT"]
OTHER_SYMBOLS=["GRASS/USDT:USDT","VELVET/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","HEI/USDT:USDT"]

try:
    LAST_ALERT=json.load(open("cooldown.json"))
except:
    LAST_ALERT={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d')}

def get_killzone_pick():
    h=datetime.now(timezone.utc).hour
    for sess,hours in PICK_HOURS.items():
        if h in hours:
            return sess,h,True
    return "DEAD ZONE",h,False

def can_send_killzone(sym):
    session,hour_utc,is_pick=get_killzone_pick()
    if not is_pick:
        return False,session
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if LAST_ALERT.get("date")!=today:
        LAST_ALERT["count_today"]=0
        LAST_ALERT["date"]=today
    if LAST_ALERT.get("count_today",0)>=MAX_SIGNALS_PER_DAY:
        return False,session
    k=f"{sym}_SIGNAL"
    if time.time()-LAST_ALERT.get(k,0) < SIGNAL_COOLDOWN_MIN*60:
        return False,session
    return True,session

def mark_sent(sym):
    LAST_ALERT[f"{sym}_SIGNAL"]=time.time()
    LAST_ALERT["count_today"]=LAST_ALERT.get("count_today",0)+1
    try:
        json.dump(LAST_ALERT,open("cooldown.json","w"))
    except:
        pass

def rsi(df,p=14):
    d=df['close'].diff()
    g=d.where(d>0,0).rolling(p).mean()
    l=-d.where(d<0,0).rolling(p).mean()
    return 100-(100/(1+g/l))

def get_wick_levels(df5m):
    recent=df5m.tail(50).copy()
    recent['body']=abs(recent['close']-recent['open'])
    recent['up_wick']=recent['high']-recent[['open','close']].max(axis=1)
    recent['low_wick']=recent[['open','close']].min(axis=1)-recent['low']
    recent['up_r']=recent['up_wick']/(recent['body']+0.000001)
    recent['low_r']=recent['low_wick']/(recent['body']+0.000001)
    tops=recent[recent['up_r']>1.5]['high']
    bots=recent[recent['low_r']>1.5]['low']
    CEIL=tops.max() if len(tops)>0 else recent['high'].max()
    FLOOR=bots.min() if len(bots)>0 else recent['low'].min()
    MID=(CEIL+FLOOR)/2
    FLIP=(tops.median()+bots.median())/2 if len(tops)>0 and len(bots)>0 else MID
    return CEIL,FLOOR,MID,FLIP

def check_koma(df5m,df15m,df1h):
    price=df5m['close'].iloc[-1]
    CEIL,FLOOR,MID,FLIP=get_wick_levels(df5m)
    score=0; reasons=[]; buy=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001
    up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
    if low_r>2.5:
        score+=3; reasons.append(f"LOW GRAB {low_r:.1f}x FLOOR {FLOOR:.5f} LONG 9/10"); buy+=3
    if up_r>1.8 and price<CEIL:
        score+=2; reasons.append(f"UP REJECT {up_r:.1f}x CEIL {CEIL:.5f}"); buy+=2
    if abs(price-FLIP)/FLIP<0.004:
        score+=2; reasons.append(f"AT FLIP {FLIP:.5f}"); buy+=1
    r5=rsi(df5m).iloc[-1]
    if r5<30:
        score+=2; reasons.append(f"RSI OS {r5:.0f}"); buy+=2
    elif 30<r5<65:
        score+=1; reasons.append(f"RSI OK {r5:.0f}")
    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    if vol_r>=1.2:
        score+=1; reasons.append(f"VOL UP x{vol_r:.1f} REAL")
    score=max(0,min(10,score))
    decision="BUY NOW" if buy>=3 and score>=7 else ("WAIT" if score>=5 else "NO TRADE")
    return decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r

def detect_whale(df):
    o=df['open'].iloc[-1]; c=df['close'].iloc[-1]; h=df['high'].iloc[-1]; l=df['low'].iloc[-1]
    body=abs(c-o) or 0.0001
    upper=h-max(o,c); lower=min(o,c)-l
    if lower>body*2.5 and upper<body*0.5:
        return "BULL_LIQ_GRAB", f"BULL LIQ GRAB {lower/body:.1f}x LONG"
    if upper>body*2.5 and lower<body*0.5:
        return "BEAR_LIQ_GRAB", f"BEAR LIQ GRAB {upper/body:.1f}x SHORT"
    if upper>body*1.5 and lower>body*1.5:
        return "WHALE_WICK", "WHALE WICK both sides"
    return None,""

def check_other_coin(sym,df5m,df15m,df1h):
    price=df5m['close'].iloc[-1]
    score=0; reasons=[]; buy=0; sell=0
    whale_type,whale_msg=detect_whale(df5m)
    if whale_type=="BULL_LIQ_GRAB":
        score+=3; reasons.append(f"🐋 {whale_msg} 9/10"); buy+=3
    if whale_type=="BEAR_LIQ_GRAB":
        score+=3; reasons.append(f"🐋 {whale_msg} 9/10"); sell+=3
    vol_avg=df5m['volume'].rolling(20).mean().iloc[-1] or 1
    vol_now=df5m['volume'].iloc[-1]
    vol_r=vol_now/vol_avg
    if vol_r>=1.5:
        score+=2; reasons.append(f"VOL INCREASE x{vol_r:.1f} REAL BUY"); buy+=2
    elif vol_r>=1.2:
        score+=1; reasons.append(f"VOL UP x{vol_r:.1f}"); buy+=1
    elif vol_r<=0.6:
        score-=1; reasons.append(f"VOL DECREASE x{vol_r:.1f} SELL / fake"); sell+=1
    vol15_avg=df15m['volume'].rolling(20).mean().iloc[-1] or 1
    vol15_r=df15m['volume'].iloc[-1]/vol15_avg
    if vol15_r>=1.2:
        score+=1; reasons.append(f"15M VOL CONFIRM x{vol15_r:.1f}")
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]
    body=abs(c-o) or 0.0001
    up_r=(h-max(o,c))/body
    if len(df5m)>=2:
        prev_up=(df5m['high'].iloc[-2]-max(df5m['open'].iloc[-2],df5m['close'].iloc[-2]))/(abs(df5m['close'].iloc[-2]-df5m['open'].iloc[-2]) or 0.0001)
        if up_r>1.5 and prev_up>1.5:
            score-=2; reasons.append("DOUBLE WICK FAKE top 2x - NO TRADE")
    c0,c1,c2=df5m['close'].iloc[-3:].values
    mom5=((c0-c1)/c1*100) if c1>0 else 0
    if c0>c1>c2 and mom5>0.1:
        score+=1; reasons.append(f"5m 2UP {mom5:.2f}%"); buy+=1
    if c0<c1<c2 and mom5<-0.1:
        score+=1; reasons.append(f"5m 2DOWN {mom5:.2f}%"); sell+=1
    r5=rsi(df5m).iloc[-1]
    low_24=df1h['low'].tail(24).min(); high_24=df1h['high'].tail(24).max()
    loc=(price-low_24)/(high_24-low_24)*100 if high_24>low_24 else 50
    if loc<20 and r5<40:
        score+=2; reasons.append(f"BOTTOM {loc:.0f}% RSI {r5:.0f} LONG"); buy+=2
    elif loc>80 and r5>60:
        score+=2; reasons.append(f"TOP {loc:.0f}% RSI {r5:.0f} SHORT"); sell+=2
    if vol_r>=2.5 and body < (h-df5m['low'].iloc[-1])*0.3:
        score+=2; reasons.append(f"WHALE MANIPULATION vol {vol_r:.1f}x small body"); buy+=1
    score=max(0,min(10,score))
    if buy>=3 and score>=7:
        decision="BUY NOW"
    elif sell>=3 and score>=7:
        decision="SELL NOW"
    elif score>=5:
        decision="WAIT"
    else:
        decision="NO TRADE"
    return decision,score,reasons,price,vol_r,whale_msg,loc

def scan_one_symbol(sym, ex):
    try:
        df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        session,hour_utc,is_pick=get_killzone_pick()
        kalimoni=(hour_utc+3)%24
        if "KOMA" in sym:
            decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r=check_koma(df5m,df15m,df1h)
            print(f"{sym} {session} {kalimoni}:00 | Price {price:.5f} Wick {FLOOR:.5f}-{CEIL:.5f} | {decision} {score}/10")
            if score>=8 and "BUY" in decision:
                ok,sess=can_send_killzone(sym)
                if ok:
                    msg=f"🔥 *{sym} {decision} Score {score}/10 - {sess} PICK*\nPrice {price:.5f}\nWick Ceil {CEIL:.5f} Floor {FLOOR:.5f} Mid {MID:.5f} Flip {FLIP:.5f}\nUp {up_r:.1f}x Low {low_r:.1f}x {kalimoni}:00 Kalimoni\n\n" + "\n".join([f"- {r}" for r in reasons])
                    send_telegram(msg); mark_sent(sym)
        else:
            decision,score,reasons,price,vol_r,whale_msg,loc=check_other_coin(sym,df5m,df15m,df1h)
            print(f"{sym} {session} | Price {price:.5f} Vol x{vol_r:.1f} Loc {loc:.0f}% | {decision} {score}/10 | {whale_msg}")
            if score>=8 and ("BUY" in decision or "SELL" in decision):
                ok,sess=can_send_killzone(sym)
                if ok:
                    emoji="🟢" if "BUY" in decision else "🔴"
                    msg=f"{emoji} *{sym} {decision} Score {score}/10 - {sess} PICK*\nPrice {price:.5f}\nVol {vol_r:.1f}x Loc {loc:.0f}% {kalimoni}:00 Kalimoni {sess}\n\n" + "\n".join([f"- {r}" for r in reasons])
                    send_telegram(msg); mark_sent(sym)
    except Exception as e:
        print(f"Err {sym} {e}")

if __name__=="__main__":
    ex=ccxt.mexc({'enableRateLimit': True})
    session,hour_utc,is_pick=get_killzone_pick()
    print(f"SCAN START {session} UTC {hour_utc} Kalimoni {(hour_utc+3)%24} Pick {is_pick}")
    all_syms=KOMA_SYMBOLS+OTHER_SYMBOLS
    with ThreadPoolExecutor(max_workers=6) as executor:
        executor.map(lambda s: scan_one_symbol(s, ex), all_syms)
    print("SCAN DONE - Exit GREEN")
