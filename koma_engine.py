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
SIGNAL_COOLDOWN_MIN=30
MAX_SIGNALS_PER_DAY=5
EXTEND_PCT=0.05

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

def can_send(sym,typ,mins,price):
    k=f"{sym}_{typ}"; now=time.time(); today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if LAST_ALERT.get("date")!=today: LAST_ALERT["count_today"]=0; LAST_ALERT["date"]=today
    if LAST_ALERT.get("count_today",0)>=MAX_SIGNALS_PER_DAY: return False
    last_price_key=f"{sym}_{typ}_price"
    last_p=LAST_ALERT.get(last_price_key,0)
    if last_p!=0 and abs(price-last_p)/price < 0.01: return False
    if now-LAST_ALERT.get(k,0)>mins*60:
        LAST_ALERT[k]=now; LAST_ALERT[last_price_key]=price; LAST_ALERT["count_today"]+=1
        try: json.dump(LAST_ALERT,open("cooldown_koma.json","w"))
        except: pass
        return True
    return False

def rsi(df,p=14):
    try:
        d=df['close'].diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean(); rs=g/l
        return 100-(100/(1+rs))
    except: return pd.Series([50]*len(df))

def get_wick_levels(df5m, df1d):
    try:
        high_5m=df5m['high'].tail(100).max(); low_5m=df5m['low'].tail(100).min()
        high_1d=df1d['high'].tail(10).max(); low_1d=df1d['low'].tail(10).min()
        ceil=high_1d; floor=low_1d; mid=(ceil+floor)/2; flip=df5m['close'].tail(50).median()
        return ceil,floor,mid,flip,high_5m,low_5m
    except:
        p=df5m['close'].iloc[-1]
        return p*1.03,p*0.97,p,p,p*1.02,p*0.98

def check_koma(df5m,df15m,df1h,df1d):
    price=df5m['close'].iloc[-1]
    CEIL,FLOOR,MID,FLIP,high_5m,low_5m=get_wick_levels(df5m,df1d)
    BUY_ZONE_TOP = FLOOR * (1 + EXTEND_PCT)
    SELL_ZONE_BOTTOM = CEIL * (1 - EXTEND_PCT)
    score=0; reasons=[]; buy=0; sell=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001; up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
    o1=df1d['open'].iloc[-1]; c1=df1d['close'].iloc[-1]; h1=df1d['high'].iloc[-1]; l1=df1d['low'].iloc[-1]
    body1=abs(c1-o1) or 0.0001; up_r_1d=(h1-max(o1,c1))/body1; low_r_1d=(min(o1,c1)-l1)/body1

    if low_r>=3.0 and up_r>=3.0:
        return "WAIT",2,[f"⚠️ BOTH SIDES WHALE Up {up_r:.1f}x Low {low_r:.1f}x"],CEIL,FLOOR,MID,FLIP,price,up_r,low_r,BUY_ZONE_TOP,SELL_ZONE_BOTTOM

    if low_r>=1.2 and low_r_1d>=1.0: score+=4; reasons.append(f"FRACTAL LOW 1D {low_r_1d:.1f}x + 5m {low_r:.1f}x BUY"); buy+=4
    elif low_r>=1.2: score+=3; reasons.append(f"LOW GRAB {low_r:.1f}x FLOOR {FLOOR:.5f}"); buy+=3
    elif low_r>=0.8: score+=1; reasons.append(f"LOW WICK {low_r:.1f}x"); buy+=1
    if up_r>=1.2 and up_r_1d>=1.0: score+=4; reasons.append(f"FRACTAL HIGH 1D {up_r_1d:.1f}x + 5m {up_r:.1f}x SELL"); sell+=4
    elif up_r>=1.2: score+=3; reasons.append(f"HIGH GRAB {up_r:.1f}x CEIL {CEIL:.5f}"); sell+=3
    elif up_r>=0.8: score+=1; reasons.append(f"HIGH WICK {up_r:.1f}x"); sell+=1

    if price <= BUY_ZONE_TOP and price >= FLOOR*0.97: score+=3; reasons.append(f"IN BUY ZONE {FLOOR:.5f} -> {BUY_ZONE_TOP:.5f} (5% ext)"); buy+=3
    if price >= SELL_ZONE_BOTTOM and price <= CEIL*1.03: score+=3; reasons.append(f"IN SELL ZONE {SELL_ZONE_BOTTOM:.5f} -> {CEIL:.5f} (5% ext)"); sell+=3

    if abs(price-FLIP)/FLIP<0.008: score+=1; reasons.append(f"AT FLIP {FLIP:.5f}")

    r5=float(rsi(df5m).iloc[-1])
    if r5<35: score+=2; reasons.append(f"RSI OS {r5:.0f} BUY"); buy+=2
    elif r5>65: score+=2; reasons.append(f"RSI OB {r5:.0f} SELL"); sell+=2
    else: score+=1; reasons.append(f"RSI {r5:.0f}")

    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    if vol_r>=1.2: score+=2; reasons.append(f"VOL REAL x{vol_r:.1f}")
    elif vol_r>=1.0: score+=1; reasons.append(f"VOL x{vol_r:.1f}")

    if (low_r>=1.2 or up_r>=1.2) and vol_r<1.0:
        reasons.append(f"PERP WICK EXCEPTION Vol {vol_r:.1f}x ignored"); score+=1

    score=max(0,min(10,score))
    if buy>=4 and score>=6 and buy>sell: decision="BUY NOW"
    elif sell>=4 and score>=6 and sell>buy: decision="SELL NOW"
    elif score>=4: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r,BUY_ZONE_TOP,SELL_ZONE_BOTTOM

def scan():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    kalimoni=(hour_utc+3)%24
    print(f"\n=== KOMA SCAN {session} UTC {hour_utc} / Kalimoni {kalimoni} Pick={is_pick} ===")
    try:
        df5m=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df15m=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1h=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex.fetch_ohlcv(SYMBOL,'1D',limit=100),columns=['timestamp','open','high','low','close','volume'])
        decision,score,reasons,CEIL,FLOOR,MID,FLIP,price,up_r,low_r,BUY_ZONE_TOP,SELL_ZONE_BOTTOM=check_koma(df5m,df15m,df1h,df1d)
        print(f"KOMA {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x | {decision} {score}/10 | BuyZone {BUY_ZONE_TOP:.5f} SellZone {SELL_ZONE_BOTTOM:.5f}")
        if score>=6 and ("BUY" in decision or "SELL" in decision) and is_pick and can_send(SYMBOL,f"{decision}_{session}",SIGNAL_COOLDOWN_MIN,price):
            if "BUY" in decision: sl_raw=FLOOR*0.995; sl=max(sl_raw,price*0.99); tp1=price*1.015; tp2=CEIL*0.98; emoji="🟢"
            else: sl_raw=CEIL*1.005; sl=min(sl_raw,price*1.01); tp1=price*0.985; tp2=FLOOR*1.02; emoji="🔴"
            risk_pct=abs(price-sl)/price*100; reward1=abs(tp1-price)/price*100; reward2=abs(tp2-price)/price*100
            msg=(f"{emoji} *{SYMBOL} {decision} Score {score}/10 - {session} PICK*\nPrice {price:.5f}\nCeil {CEIL:.5f} (SellZone from {SELL_ZONE_BOTTOM:.5f})\nFloor {FLOOR:.5f} (BuyZone to {BUY_ZONE_TOP:.5f})\nFlip {FLIP:.5f} Up {up_r:.1f}x Low {low_r:.1f}x {kalimoni}:00 Kalimoni\n\n*TRADE PLAN:*\nSL {sl:.5f} (-{risk_pct:.2f}%)\nTP1 {tp1:.5f} (+{reward1:.2f}%)\nTP2 {tp2:.5f} (+{reward2:.2f}%)\n\n"+"\n".join([f"- {r}" for r in reasons]))
            send_telegram(msg)
    except Exception as e:
        print(f"Err KOMA {e}"); import traceback; traceback.print_exc()

if __name__=="__main__":
    for i in range(4):
        scan()
        if i<3: time.sleep(60)
