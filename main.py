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
SIGNAL_COOLDOWN_MIN=30
MAX_SIGNALS_PER_DAY=10
EXTEND_PCT=0.04
BODY_EXIT_RATIO=0.60
FLIP_BREAK_PCT=0.001 # 0.1% close beyond ceil/floor = flip broken
NO_REENTRY_CANDLES=3

try: LAST_ALERT=json.load(open("cooldown_other.json"))
except: LAST_ALERT={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}

def save_cooldown():
    try: json.dump(LAST_ALERT,open("cooldown_other.json","w"))
    except: pass

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
    # No re-entry after exit
    last_exit=LAST_ALERT.get("exits",{}).get(sym,0)
    if now-last_exit < NO_REENTRY_CANDLES*5*60: return False
    if now-LAST_ALERT.get(k,0)>mins*60:
        LAST_ALERT[k]=now; LAST_ALERT[last_price_key]=price; LAST_ALERT["count_today"]+=1
        save_cooldown()
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

def other_signal(df5m,df15m,df1h,df4h,df1d):
    price=df5m['close'].iloc[-1]; score=0; reasons=[]; buy=0; sell=0
    o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
    body=abs(c-o) or 0.0001; up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
    body_ratio=body/((h-l) or 0.0001)
    low_1d=df1d['low'].tail(10).min(); high_1d=df1d['high'].tail(10).max()
    FLOOR=low_1d; CEIL=high_1d
    BUY_ZONE_TOP=FLOOR*(1+EXTEND_PCT)
    SELL_ZONE_BOTTOM=CEIL*(1-EXTEND_PCT)

    # Flip memory
    trend4h=get_trend(df4h); trend1h=get_trend(df1h); trend15m=get_trend(df15m)
    reasons.append(f"4H {trend4h} | 1H {trend1h} | 15M {trend15m}")

    o1=df1d['open'].iloc[-1]; c1=df1d['close'].iloc[-1]; h1=df1d['high'].iloc[-1]; l1=df1d['low'].iloc[-1]
    body1=abs(c1-o1) or 0.0001; up_r_1d=(h1-max(o1,c1))/body1; low_r_1d=(min(o1,c1)-l1)/body1

    if low_r>=1.2 and low_r_1d>=1.0: score+=4; reasons.append(f"🐋 FRACTAL LOW {low_r_1d:.1f}x + 5m {low_r:.1f}x"); buy+=4
    elif low_r>=1.2: score+=3; reasons.append(f"LOW GRAB {low_r:.1f}x"); buy+=3
    elif low_r>=0.8: score+=1; reasons.append(f"Low wick {low_r:.1f}x"); buy+=1

    if up_r>=1.2 and up_r_1d>=1.0: score+=4; reasons.append(f"🐋 FRACTAL HIGH {up_r_1d:.1f}x + 5m {up_r:.1f}x"); sell+=4
    elif up_r>=1.2: score+=3; reasons.append(f"HIGH GRAB {up_r:.1f}x"); sell+=3
    elif up_r>=0.8: score+=1; reasons.append(f"High wick {up_r:.1f}x"); sell+=1

    if price <= BUY_ZONE_TOP: score+=3; reasons.append(f"BUY ZONE {FLOOR:.5f}->{BUY_ZONE_TOP:.5f}"); buy+=3
    if price >= SELL_ZONE_BOTTOM: score+=3; reasons.append(f"SELL ZONE {SELL_ZONE_BOTTOM:.5f}->{CEIL:.5f}"); sell+=3

    vol_r=df5m['volume'].iloc[-1]/(df5m['volume'].rolling(20).mean().iloc[-1] or 1)
    if (low_r>=1.2 or up_r>=1.2) and vol_r<1.0: vol_r=1.6; reasons.append(f"WICK EXCEPTION vol->1.6x")
    if vol_r>=1.2: score+=2; reasons.append(f"VOL x{vol_r:.1f}"); buy+=1; sell+=1
    elif vol_r>=1.0: score+=1; reasons.append(f"VOL x{vol_r:.1f}")

    c0,c1,c2=df5m['close'].iloc[-3:].values
    if c0>c1>c2 and trend4h!="DOWN": score+=2; reasons.append("2UP"); buy+=2
    if c0<c1<c2 and trend4h!="UP": score+=2; reasons.append("2DOWN"); sell+=2

    loc=(price-df1h['low'].tail(24).min())/(df1h['high'].tail(24).max()-df1h['low'].tail(24).min())*100 if df1h['high'].tail(24).max()>df1h['low'].tail(24).min() else 50
    r5=float(rsi(df5m).iloc[-1])
    if loc<20 and r5<40: score+=2; reasons.append(f"BOTTOM {loc:.0f}% RSI {r5:.0f}"); buy+=2
    if loc>80 and r5>60: score+=2; reasons.append(f"TOP {loc:.0f}% RSI {r5:.0f}"); sell+=2

    score=max(0,min(10,score))
    if buy>=4 and score>=6 and trend4h!="DOWN" and trend1h!="DOWN": decision="BUY NOW"
    elif sell>=4 and score>=6 and trend4h!="UP" and trend1h!="UP": decision="SELL NOW"
    elif score>=4: decision="WAIT"
    else: decision="NO TRADE"
    return decision,score,reasons,price,vol_r,body_ratio,loc,trend4h,trend1h,up_r,low_r,FLOOR,CEIL,BUY_ZONE_TOP,SELL_ZONE_BOTTOM

def scan_one(args):
    sym,ex,session,is_pick=args
    try:
        df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df4h=pd.DataFrame(ex.fetch_ohlcv(sym,'4h',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex.fetch_ohlcv(sym,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])

        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        price=c; body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        FLOOR=df1d['low'].tail(10).min(); CEIL=df1d['high'].tail(10).max()

        # === 100% EXIT ENGINE ===
        try:
            positions=ex.fetch_positions([sym])
            for p in positions:
                contracts=float(p.get('contracts',0) or 0)
                if contracts==0: continue
                side=p.get('side','').lower()
                entry=float(p.get('entryPrice',0))
                pnl=float(p.get('unrealizedPnl',0) or 0)
                # Store flip on entry
                if sym not in LAST_ALERT.get("flips",{}):
                    LAST_ALERT.setdefault("flips",{})[sym]=CEIL if side=='short' else FLOOR
                    save_cooldown()
                last_flip=LAST_ALERT.get("flips",{}).get(sym, CEIL if side=='short' else FLOOR)

                exit_reason=None
                # 1) Body break
                if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: exit_reason=f"BODY BREAK {body_ratio:.2f}"
                if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: exit_reason=f"BODY BREAK {body_ratio:.2f}"
                # 2) Flip price break (LAB 0.05010 logic in wick language)
                if side=='short' and c > last_flip*(1+FLIP_BREAK_PCT): exit_reason=f"FLIP BROKE {last_flip:.5f}->{c:.5f}"
                if side=='long' and c < last_flip*(1-FLIP_BREAK_PCT): exit_reason=f"FLIP BROKE {last_flip:.5f}->{c:.5f}"
                # 3) Both wicks volatility = get out
                up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
                if up_r>=3.0 and low_r>=3.0: exit_reason=f"BOTH WICKS {up_r:.1f}x/{low_r:.1f}x VOLATILITY EXIT"

                if exit_reason:
                    side_close='buy' if side=='short' else 'sell'
                    ex.create_order(sym,'market',side_close,contracts)
                    LAST_ALERT.setdefault("exits",{})[sym]=time.time()
                    LAST_ALERT.get("flips",{}).pop(sym,None)
                    save_cooldown()
                    send_telegram(f"⚠️ *{sym} AUTO EXIT {side.upper()}* {exit_reason} | Entry {entry:.5f} PnL {pnl:.2f}")
                    return
        except Exception as e:
            print(f"Exit err {sym} {e}")

        decision,score,reasons,price,vol_r,body_ratio,loc,trend4h,trend1h,up_r,low_r,FLOOR,CEIL,BUY_ZONE_TOP,SELL_ZONE_BOTTOM=other_signal(df5m,df15m,df1h,df4h,df1d)
        print(f"{sym} {price:.5f} body {body_ratio:.2f} Up {up_r:.1f} Low {low_r:.1f} | {decision} {score}/10")
        if score>=6 and ("BUY" in decision or "SELL" in decision):
            if is_pick and can_send(sym,f"{decision}_{session}",SIGNAL_COOLDOWN_MIN,price):
                # Store flip for future exit
                LAST_ALERT.setdefault("flips",{})[sym]=CEIL if "SELL" in decision else FLOOR
                save_cooldown()
                if "BUY" in decision: sl=max(FLOOR*0.995, price*0.99); tp1=price*1.015; tp2=CEIL*0.98
                else: sl=min(CEIL*1.005, price*1.01); tp1=price*0.985; tp2=FLOOR*1.02
                risk=abs(price-sl)/price*100; rew1=abs(tp1-price)/price*100; rew2=abs(tp2-price)/price*100
                emoji="🟢" if "BUY" in decision else "🔴"
                msg=f"{emoji} *{sym} {decision} {score}/10 - {session}*\nPrice {price:.5f}\nFloor {FLOOR:.5f} Ceil {CEIL:.5f}\nFlip stored {LAST_ALERT['flips'][sym]:.5f}\nBody {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x\nSL {sl:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f}\n"+"\n".join([f"- {r}" for r in reasons])
                send_telegram(msg)
    except Exception as e: print(f"Err {sym} {e}"); import traceback; traceback.print_exc()

def scan():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== OTHER SCAN {session} UTC {hour_utc} ===")
    tasks=[(s,ex,session,is_pick) for s in MANUAL_WATCHLIST]
    with ThreadPoolExecutor(max_workers=5) as ex2: ex2.map(scan_one,tasks)

if __name__=="__main__":
    for i in range(4):
        scan()
        if i<3: time.sleep(60)
