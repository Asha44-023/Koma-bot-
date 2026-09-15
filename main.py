import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

def get_env_clean(*names): return None
TELEGRAM_TOKEN=get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN")
TELEGRAM_CHAT=get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID")

KOMA_SYMBOL="KOMA/USDT:USDT"
OTHER_LIST=["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
PICK_HOURS={"ASIAN":[0,1],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=45
BODY_EXIT_RATIO=0.55
FLIP_BREAK_PCT=0.001
NO_REENTRY_CANDLES=4
SL_BUFFER=0.012
TP_BUFFER=0.006
SWEEP_DIST_PCT=0.05

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
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id":TELEGRAM_CHAT,"text":msg}, timeout=15)
    except: pass
    print(msg)

def get_killzone():
    h=datetime.now(timezone.utc).hour
    for sess,hours in PICK_HOURS.items():
        if h in hours: return sess,h,True
    return "DEAD ZONE",h,False

def get_exchanges():
    api_key = os.getenv("MEXC_API_KEY") or ""
    secret = os.getenv("MEXC_SECRET") or ""
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
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(KOMA_SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(KOMA_SYMBOL,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        if len(df5m)<30: return
        i=-2 # CLOSED CANDLE FIX - your bug was -1
        o,c,h,l = df5m['open'].iloc[i], df5m['close'].iloc[i], df5m['high'].iloc[i], df5m['low'].iloc[i]
        if h==l: return
        body=abs(c-o)
        if body < (h-l)*0.2: body=(h-l)*0.2 # FIX 0.0x bug - min 20% of range
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[i]; vol_prev=df5m['volume'].iloc[i-1]
        vol_avg=df5m['volume'].iloc[-26:-2].mean() or 1
        vol_trend=vol/vol_prev if vol_prev>0 else 1.0
        recent_low=df5m['low'].iloc[-22:-2].min(); recent_high=df5m['high'].iloc[-22:-2].max()
        swept_low = (l <= recent_low*1.002) or (low_r>=2.2)
        swept_high = (h >= recent_high*0.998) or (up_r>=2.2)
        print(f"KOMA {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x vol {vol/vol_avg:.2f}x trend {vol_trend:.2f}x {'INC' if vol>vol_prev else 'DEC'} sweptL {swept_low} sweptH {swept_high} CLOSED {i}")

        if not is_pick: return
        if up_r>=3.0 and low_r>=3.0: return # both wicks = indecision

        if low_r>=1.2 and swept_low:
            if price > l*(1+SWEEP_DIST_PCT): return
            if low_r < 5.0 and vol < vol_avg*0.15: return
            if low_r < 5.0 and vol_trend < 0.75:
                print(f"SKIP KOMA BUY need INC trend {vol_trend:.2f}x"); return
            if can_send_koma():
                sl=l*(1-SL_BUFFER); risk=price-sl
                send_telegram(f"🟢 *KOMA BUY SWEEP Low {low_r:.1f}x at {price:.5f}* VOL INC {vol_trend:.2f}x vol {vol/vol_avg:.2f}x\nSL {sl:.5f} TP {price+risk*1.5:.5f}/{price+risk*3:.5f}")

        if up_r>=1.2 and swept_high:
            if price < h*(1-SWEEP_DIST_PCT): return
            if up_r < 5.0 and vol < vol_avg*0.15: return
            if up_r < 5.0 and vol_trend > 1.9:
                print(f"SKIP KOMA SELL need DEC trend {vol_trend:.2f}x"); return
            if can_send_koma():
                sl=h*(1+SL_BUFFER); risk=sl-price
                send_telegram(f"🔴 *KOMA SELL SWEEP High {up_r:.1f}x at {price:.5f}* VOL {'INC' if vol>vol_prev else 'DEC'} {vol_trend:.2f}x vol {vol/vol_avg:.2f}x\nSL {sl:.5f} TP {price-risk*1.5:.5f}/{price-risk*3:.5f}")
    except Exception as e: print(f"KOMA err {e}")

def scan_other_one(sym, ex_public, ex_private, session, is_pick):
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(sym,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        if len(df5m)<30: return
        i=-2
        o,c,h,l = df5m['open'].iloc[i], df5m['close'].iloc[i], df5m['high'].iloc[i], df5m['low'].iloc[i]
        if h==l: return
        body=abs(c-o)
        if body < (h-l)*0.2: body=(h-l)*0.2
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[i]; vol_prev=df5m['volume'].iloc[i-1]
        vol_avg=df5m['volume'].iloc[-26:-2].mean() or 1
        vol_trend=vol/vol_prev if vol_prev>0 else 1.0
        recent_low=df5m['low'].iloc[-22:-2].min(); recent_high=df5m['high'].iloc[-22:-2].max()
        swept_low = (l <= recent_low*1.002) or (low_r>=2.2)
        swept_high = (h >= recent_high*0.998) or (up_r>=2.2)
        print(f"{sym} {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x vol {vol/vol_avg:.2f}x trend {vol_trend:.2f}x {'INC' if vol>vol_prev else 'DEC'} sweptL {swept_low} sweptH {swept_high} CLOSED {i}")

        if not is_pick: return
        if up_r>=3.0 and low_r>=3.0: return

        if low_r>=1.5 and swept_low:
            if price > l*(1+SWEEP_DIST_PCT): return
            if low_r < 5.0 and vol < vol_avg*0.15: return
            if low_r < 5.0 and vol_trend < 0.75: return
            if can_send_other(sym, price):
                sl=l*(1-SL_BUFFER); risk=price-sl
                send_telegram(f"🟢 *{sym} BUY SWEEP Low {low_r:.1f}x at {price:.5f}* SCORE VOL INC {vol_trend:.2f}x dist {(price-l)/l*100:.1f}% vol {vol/vol_avg:.2f}x\nSL {sl:.5f} TP1 {price+risk*1.5:.5f} TP2 {price+risk*3:.5f}")

        if up_r>=1.5 and swept_high:
            if price < h*(1-SWEEP_DIST_PCT): return
            if up_r < 5.0 and vol < vol_avg*0.15: return
            if up_r < 5.0 and vol_trend > 1.9: return
            if can_send_other(sym, price):
                sl=h*(1+SL_BUFFER); risk=sl-price
                send_telegram(f"🔴 *{sym} SELL SWEEP High {up_r:.1f}x at {price:.5f}* VOL {'INC' if vol>vol_prev else 'DEC'} {vol_trend:.2f}x dist {(h-price)/h*100:.1f}% vol {vol/vol_avg:.2f}x\nSL {sl:.5f} TP1 {price-risk*1.5:.5f} TP2 {price-risk*3:.5f}")
    except Exception as e: print(f"{sym} err {e}")

def main():
    ex_public, ex_private = get_exchanges()
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== 5% WICK=SWEEP + VOL TREND SCAN {session} UTC {hour_utc} PICK={is_pick} ===")
    scan_koma(ex_public, ex_private, session, is_pick)
    time.sleep(1)
    for s in OTHER_LIST:
        scan_other_one(s, ex_public, ex_private, session, is_pick)
        time.sleep(2)

if __name__=="__main__":
    for i in range(3):
        main()
        if i<2: time.sleep(30)
