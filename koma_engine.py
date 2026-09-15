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
BODY_EXIT_RATIO=0.60
FLIP_BREAK_PCT=0.001

try: LAST_ALERT=json.load(open("cooldown_koma.json"))
except: LAST_ALERT={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}

def save_cooldown():
    try: json.dump(LAST_ALERT,open("cooldown_koma.json","w"))
    except: pass

def get_exchanges():
    api_key = os.getenv("MEXC_API_KEY") or os.getenv("MEXC_APIKEY") or os.getenv("API_KEY") or ""
    secret = os.getenv("MEXC_SECRET") or os.getenv("MEXC_SECRET_KEY") or os.getenv("SECRET") or ""
    api_key=api_key.strip().replace('"','').replace("'","")
    secret=secret.strip().replace('"','').replace("'","")
    ex_public=ccxt.mexc({'enableRateLimit':True})
    if len(api_key)>10 and len(secret)>10:
        print(f"KOMA: private mode ON")
        ex_private=ccxt.mexc({'apiKey':api_key,'secret':secret,'enableRateLimit':True,'options':{'defaultType':'swap'}})
        return ex_public, ex_private
    print("KOMA: scan only mode")
    return ex_public, None

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

def scan():
    ex_public, ex_private = get_exchanges()
    session,hour_utc,is_pick=get_killzone()
    kalimoni=(hour_utc+3)%24
    print(f"\n=== KOMA {session} Kalimoni {kalimoni} ===")
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()

        if ex_private:
            try:
                for p in ex_private.fetch_positions([SYMBOL]):
                    if float(p.get('contracts',0) or 0)==0: continue
                    side=p.get('side','').lower()
                    last_flip=LAST_ALERT.get("flips",{}).get(SYMBOL, CEIL if side=='short' else FLOOR)
                    reason=None
                    if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='short' and c>last_flip*(1+FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if side=='long' and c<last_flip*(1-FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if up_r>=3.0 and low_r>=3.0: reason="BOTH WICKS"
                    if reason:
                        ex_private.create_order(SYMBOL,'market','buy' if side=='short' else 'sell', float(p.get('contracts',0)))
                        LAST_ALERT.setdefault("exits",{})[SYMBOL]=time.time()
                        LAST_ALERT.get("flips",{}).pop(SYMBOL,None)
                        save_cooldown()
                        send_telegram(f"⚠️ *KOMA EXIT {side.upper()}* {reason}")
                        return
            except Exception as e: print(f"KOMA exit err {e}")

        print(f"KOMA {price:.5f} body {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x | {'PICK' if is_pick else 'DEAD'}")
    except Exception as e: print(f"KOMA err {e}")

if __name__=="__main__":
    for i in range(4):
        scan()
        if i<3: time.sleep(60)
