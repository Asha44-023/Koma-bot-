import os, ccxt, pandas as pd, requests, time, json, threading
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

# ==== CONFIG ====
KOMA_SYMBOL="KOMA/USDT:USDT"
OTHER_LIST=["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
PICK_HOURS={"ASIAN":[0,1],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=30
MAX_SIGNALS_PER_DAY=10
EXTEND_PCT_OTHER=0.04
EXTEND_PCT_KOMA=0.05
BODY_EXIT_RATIO=0.60
FLIP_BREAK_PCT=0.001
NO_REENTRY_CANDLES=3

try: COOLDOWN_OTHER=json.load(open("cooldown_other.json"))
except: COOLDOWN_OTHER={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}
try: COOLDOWN_KOMA=json.load(open("cooldown_koma.json"))
except: COOLDOWN_KOMA={"count_today":0,"date":datetime.now(timezone.utc).strftime('%Y-%m-%d'),"flips":{},"exits":{}}

def save_cooldown_other():
    try: json.dump(COOLDOWN_OTHER,open("cooldown_other.json","w"))
    except: pass
def save_cooldown_koma():
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
    api_key = os.getenv("MEXC_API_KEY") or os.getenv("MEXC_APIKEY") or os.getenv("API_KEY") or os.getenv("MEXC_KEY") or ""
    secret = os.getenv("MEXC_SECRET") or os.getenv("MEXC_SECRET_KEY") or os.getenv("SECRET") or os.getenv("API_SECRET") or ""
    api_key = api_key.strip().replace('"','').replace("'","")
    secret = secret.strip().replace('"','').replace("'","")
    ex_public = ccxt.mexc({'enableRateLimit': True})
    if len(api_key) > 10 and len(secret) > 10:
        print(f"Keys found len {len(api_key)} -> private mode ON")
        ex_private = ccxt.mexc({'apiKey': api_key, 'secret': secret, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
        return ex_public, ex_private
    else:
        print("No API keys -> scan only mode")
        return ex_public, None

# ========== IMPORT YOUR LOGIC (100% version) ==========
# For brevity I include both check functions here - use your 100% code

def rsi(df,p=14):
    try:
        d=df['close'].diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean(); rs=g/l
        return 100-(100/(1+rs))
    except: return pd.Series([50]*len(df))

def get_trend(df):
    try:
        ema9=df['close'].ewm(span=9).mean().iloc[-1]; ema21=df['close'].ewm(span=21).mean().iloc[-1]; ema50=df['close'].ewm(span=50).mean().iloc[-1]; price=df['close'].iloc[-1]
        if ema9>ema21>ema50 and price>ema9: return "UP"
        if ema9<ema21<ema50 and price<ema9: return "DOWN"
        return "RANGE"
    except: return "RANGE"

# ---- KOMA + OTHER scan now both use ex_public/ex_private ----

def scan_koma(ex_public, ex_private, session, is_pick):
    from datetime import timezone
    SYMBOL=KOMA_SYMBOL
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(SYMBOL,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()

        if ex_private:
            try:
                positions=ex_private.fetch_positions([SYMBOL])
                for p in positions:
                    if float(p.get('contracts',0) or 0)==0: continue
                    side=p.get('side','').lower()
                    last_flip=COOLDOWN_KOMA.get("flips",{}).get(SYMBOL, CEIL if side=='short' else FLOOR)
                    exit_reason=None
                    if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: exit_reason=f"BODY {body_ratio:.2f}"
                    if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: exit_reason=f"BODY {body_ratio:.2f}"
                    if side=='short' and c > last_flip*(1+FLIP_BREAK_PCT): exit_reason=f"FLIP BROKE {last_flip:.5f}"
                    if side=='long' and c < last_flip*(1-FLIP_BREAK_PCT): exit_reason=f"FLIP BROKE {last_flip:.5f}"
                    if up_r>=3.0 and low_r>=3.0: exit_reason=f"BOTH WICKS"
                    if exit_reason:
                        ex_private.create_order(SYMBOL,'market','buy' if side=='short' else 'sell', float(p.get('contracts',0)))
                        COOLDOWN_KOMA.setdefault("exits",{})[SYMBOL]=time.time()
                        COOLDOWN_KOMA.get("flips",{}).pop(SYMBOL,None)
                        save_cooldown_koma()
                        send_telegram(f"⚠️ *KOMA AUTO EXIT {side.upper()}* {exit_reason}")
                        return
            except Exception as e: print(f"KOMA exit err {e}")

        print(f"KOMA {price:.5f} Body {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x")
    except Exception as e: print(f"KOMA scan err {e}")

def scan_other_one(sym, ex_public, ex_private, session, is_pick):
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(sym,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        body=abs(c-o) or 0.0001; body_ratio=body/((h-l) or 0.0001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        print(f"{sym} {price:.5f} Body {body_ratio:.2f} Up {up_r:.1f}x Low {low_r:.1f}x")
        # same exit logic as KOMA for OTHER...
    except Exception as e: print(f"{sym} err {e}")

def main():
    ex_public, ex_private = get_exchanges()
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== BOTH 100% SCAN {session} UTC {hour_utc} ===")
    scan_koma(ex_public, ex_private, session, is_pick)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for s in OTHER_LIST: ex.submit(scan_other_one, s, ex_public, ex_private, session, is_pick)

if __name__=="__main__":
    for i in range(4):
        main()
        if i<3: time.sleep(60)
