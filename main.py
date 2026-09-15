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

KOMA_SYMBOL="KOMA/USDT:USDT"
OTHER_LIST=["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
PICK_HOURS={"ASIAN":[0,1],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=45
BODY_EXIT_RATIO=0.55
FLIP_BREAK_PCT=0.001
NO_REENTRY_CANDLES=4
EXTEND_PCT_OTHER=0.02
EXTEND_PCT_KOMA=0.025

try: COOLDOWN_OTHER=json.load(open("cooldown_other.json"))
except: COOLDOWN_OTHER={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}
try: COOLDOWN_KOMA=json.load(open("cooldown_koma.json"))
except: COOLDOWN_KOMA={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}

def save_other():
    try: json.dump(COOLDOWN_OTHER,open("cooldown_other.json","w"))
    except: pass
def save_koma():
    try: json.dump(COOLDOWN_KOMA,open("cooldown_koma.json","w"))
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

def get_exchanges():
    api_key = os.getenv("MEXC_API_KEY") or os.getenv("MEXC_APIKEY") or os.getenv("API_KEY") or ""
    secret = os.getenv("MEXC_SECRET") or os.getenv("MEXC_SECRET_KEY") or os.getenv("SECRET") or ""
    api_key=api_key.strip().replace('"','').replace("'","")
    secret=secret.strip().replace('"','').replace("'","")
    ex_public=ccxt.mexc({'enableRateLimit':True})
    if len(api_key)>10 and len(secret)>10:
        ex_private=ccxt.mexc({'apiKey':api_key,'secret':secret,'enableRateLimit':True,'options':{'defaultType':'swap'}})
        return ex_public, ex_private
    return ex_public, None

def can_send_other(sym, price):
    now=time.time()
    if now-COOLDOWN_OTHER.get("exits",{}).get(sym,0) < NO_REENTRY_CANDLES*5*60: return False
    if now-COOLDOWN_OTHER.get(sym,0) > SIGNAL_COOLDOWN_MIN*60:
        COOLDOWN_OTHER[sym]=now; save_other(); return True
    return False

def can_send_koma():
    now=time.time()
    k=f"{KOMA_SYMBOL}_SCAN"
    if now-COOLDOWN_KOMA.get("exits",{}).get(KOMA_SYMBOL,0) < NO_REENTRY_CANDLES*5*60: return False
    if now-COOLDOWN_KOMA.get(k,0) > SIGNAL_COOLDOWN_MIN*60:
        COOLDOWN_KOMA[k]=now; save_koma(); return True
    return False

def scan_koma(ex_public, ex_private, session, is_pick):
    SYMBOL=KOMA_SYMBOL
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[-1]; vol_avg=df5m['volume'].rolling(20).mean().iloc[-1] or 1

        if ex_private:
            try:
                for p in ex_private.fetch_positions([SYMBOL]):
                    if float(p.get('contracts',0) or 0)==0: continue
                    side=p.get('side','').lower()
                    last_flip=COOLDOWN_KOMA.get("flips",{}).get(SYMBOL, CEIL if side=='short' else FLOOR)
                    reason=None
                    if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='short' and c > last_flip*(1+FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if side=='long' and c < last_flip*(1-FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if up_r>=3.0 and low_r>=3.0: reason=f"BOTH WICKS"
                    if reason:
                        ex_private.create_order(SYMBOL,'market','buy' if side=='short' else 'sell', float(p.get('contracts',0)))
                        COOLDOWN_KOMA.setdefault("exits",{})[SYMBOL]=time.time()
                        COOLDOWN_KOMA.get("flips",{}).pop(SYMBOL,None); save_koma()
                        send_telegram(f"⚠️ *KOMA EXIT {side.upper()}* {reason} at {price:.5f}")
                        return
            except Exception as e: print(f"KOMA exit {e}")

        print(f"KOMA {price:.5f} body {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x Floor {FLOOR:.5f}")

        if not is_pick: return
        # TIGHT FILTER
        if low_r>=1.2:
            if price > FLOOR*1.03:
                print(f"SKIP KOMA BUY price {price:.5f} too far from floor {FLOOR:.5f}")
                return
            if low_r>6 and vol < vol_avg*0.8:
                print(f"SKIP KOMA huge wick low vol")
                return
            if can_send_koma():
                COOLDOWN_KOMA.setdefault("flips",{})[SYMBOL]=FLOOR; save_koma()
                send_telegram(f"🟢 *KOMA BUY Low {low_r:.1f}x at {price:.5f}* Floor {FLOOR:.5f} body {body_ratio:.2f}")

        if up_r>=1.2:
            if price < CEIL*0.97:
                print(f"SKIP KOMA SELL price too far from ceil {CEIL:.5f}")
                return
            if up_r>6 and vol < vol_avg*0.8:
                print(f"SKIP KOMA huge wick low vol")
                return
            if can_send_koma():
                COOLDOWN_KOMA.setdefault("flips",{})[SYMBOL]=CEIL; save_koma()
                send_telegram(f"🔴 *KOMA SELL High {up_r:.1f}x at {price:.5f}* Ceil {CEIL:.5f} body {body_ratio:.2f}")

    except Exception as e: print(f"KOMA err {e}")

def scan_other_one(sym, ex_public, ex_private, session, is_pick):
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(sym,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[-1]; vol_avg=df5m['volume'].rolling(20).mean().iloc[-1] or 1

        if ex_private:
            try:
                for p in ex_private.fetch_positions([sym]):
                    if float(p.get('contracts',0) or 0)==0: continue
                    side=p.get('side','').lower()
                    last_flip=COOLDOWN_OTHER.get("flips",{}).get(sym, CEIL if side=='short' else FLOOR)
                    reason=None
                    if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='short' and c>last_flip*(1+FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if side=='long' and c<last_flip*(1-FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if up_r>=3.0 and low_r>=3.0: reason=f"BOTH WICKS"
                    if reason:
                        ex_private.create_order(sym,'market','buy' if side=='short' else 'sell', float(p.get('contracts',0)))
                        COOLDOWN_OTHER.setdefault("exits",{})[sym]=time.time()
                        COOLDOWN_OTHER.get("flips",{}).pop(sym,None); save_other()
                        send_telegram(f"⚠️ *{sym} EXIT {side.upper()}* {reason}")
                        return
            except Exception as e: print(f"Exit {sym} {e}")

        print(f"{sym} {price:.5f} body {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x")

        if not is_pick: return

        # TIGHT FILTER - price must be within 3% of floor/ceil
        if low_r>=1.5:
            if price > FLOOR*1.03:
                print(f"SKIP {sym} BUY {price:.5f} too far from floor {FLOOR:.5f}")
                return
            if low_r>6 and vol < vol_avg*0.8:
                print(f"SKIP {sym} huge wick fake")
                return
            if can_send_other(sym, price):
                COOLDOWN_OTHER.setdefault("flips",{})[sym]=FLOOR; save_other()
                send_telegram(f"🟢 *{sym} BUY Low wick {low_r:.1f}x at {price:.5f}* Floor {FLOOR:.5f}")

        if up_r>=1.5:
            if price < CEIL*0.97:
                print(f"SKIP {sym} SELL {price:.5f} too far from ceil {CEIL:.5f}")
                return
            if up_r>6 and vol < vol_avg*0.8:
                print(f"SKIP {sym} huge wick fake")
                return
            if can_send_other(sym, price):
                COOLDOWN_OTHER.setdefault("flips",{})[sym]=CEIL; save_other()
                send_telegram(f"🔴 *{sym} SELL High wick {up_r:.1f}x at {price:.5f}* Ceil {CEIL:.5f}")

    except Exception as e: print(f"{sym} err {e}")

def main():
    ex_public, ex_private = get_exchanges()
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== TIGHT SCAN {session} UTC {hour_utc} PICK={is_pick} ===")
    scan_koma(ex_public, ex_private, session, is_pick)
    with ThreadPoolExecutor(max_workers=5) as pool:
        for s in OTHER_LIST:
            pool.submit(scan_other_one, s, ex_public, ex_private, session, is_pick)

if __name__=="__main__":
    for i in range(4):
        main()
        if i<3: time.sleep(60)
