import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

def get_env_clean(*names):
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
        if len(df5m)<25: return
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        if h==l: return
        body=abs(c-o) or ((h-l)*0.1) or 0.00001
        body_ratio=body/((h-l) or 0.00001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[-1]; vol_prev=df5m['volume'].iloc[-2]
        vol_avg=df5m['volume'].rolling(20).mean().iloc[-1] or 1
        if vol_avg==0: vol_avg=vol or 1
        vol_trend=vol/vol_prev if vol_prev>0 else 1.0
        recent_low=df5m['low'].tail(20).min(); recent_high=df5m['high'].tail(20).max()
        swept_low = (l <= recent_low * 1.002) or (low_r >= 2.2)
        swept_high = (h >= recent_high * 0.998) or (up_r >= 2.2)
        vol_inc = vol > vol_prev
        vol_dec = vol < vol_prev

        if ex_private:
            try:
                for p in ex_private.fetch_positions([SYMBOL]):
                    if float(p.get('contracts',0) or 0)==0: continue
                    side=p.get('side','').lower()
                    last_flip=COOLDOWN_KOMA.get("flips",{}).get(SYMBOL, CEIL if side=='short' else FLOOR)
                    reason=None
                    if side=='short' and c>o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='long' and c<o and body_ratio>=BODY_EXIT_RATIO: reason=f"BODY {body_ratio:.2f}"
                    if side=='short' and c>last_flip*(1+FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if side=='long' and c<last_flip*(1-FLIP_BREAK_PCT): reason=f"FLIP BROKE"
                    if up_r>=3.0 and low_r>=3.0: reason=f"BOTH WICKS"
                    if reason:
                        ex_private.create_order(SYMBOL,'market','buy' if side=='short' else 'sell', float(p.get('contracts',0)))
                        COOLDOWN_KOMA.setdefault("exits",{})[SYMBOL]=time.time()
                        COOLDOWN_KOMA.get("flips",{}).pop(SYMBOL,None); save_koma()
                        send_telegram(f"⚠️ *KOMA EXIT {side.upper()}* {reason} at {price:.5f}")
                        return
            except Exception as e: print(f"KOMA exit {e}")

        print(f"KOMA {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x vol {vol/vol_avg:.2f}x trend {vol_trend:.2f}x {'INC' if vol_inc else 'DEC'} sweptL {swept_low} sweptH {swept_high}")

        if not is_pick: return

        if low_r>=1.2 and swept_low:
            if price > l * (1+SWEEP_DIST_PCT): return
            if low_r < 5.0 and vol < vol_avg*0.15: return
            # VOLUME INCREASE = BUY
            if low_r < 5.0 and not vol_inc and vol_trend < 0.8:
                print(f"SKIP KOMA BUY vol decreasing {vol_trend:.2f}x need INC")
                return
            if can_send_koma():
                COOLDOWN_KOMA.setdefault("flips",{})[SYMBOL]=FLOOR; save_koma()
                sl=l*(1-SL_BUFFER); risk=price-sl
                tp1=price+risk*1.5; tp2=price+risk*3.0; tp3=CEIL*(1-TP_BUFFER)
                score=int(min(low_r/3,1)*50 + min(vol_trend/2,1)*50)
                send_telegram(f"🟢 *KOMA BUY SWEEP Low {low_r:.1f}x at {price:.5f}* SCORE {score} VOL INC {vol_trend:.2f}x vol {vol/vol_avg:.2f}x\nSL {sl:.5f} below wick {l:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")

        if up_r>=1.2 and swept_high:
            if price < h * (1-SWEEP_DIST_PCT): return
            if up_r < 5.0 and vol < vol_avg*0.15: return
            # VOLUME DECREASE = SELL (or vol spike exhaustion)
            if up_r < 5.0 and vol_inc and vol_trend > 1.8:
                print(f"SKIP KOMA SELL vol spike INC {vol_trend:.2f}x need DEC/exhaustion")
                return
            if can_send_koma():
                COOLDOWN_KOMA.setdefault("flips",{})[SYMBOL]=CEIL; save_koma()
                sl=h*(1+SL_BUFFER); risk=sl-price
                tp1=price-risk*1.5; tp2=price-risk*3.0; tp3=FLOOR*(1+TP_BUFFER)
                score=int(min(up_r/3,1)*50 + min(vol/vol_avg/1.5,1)*50)
                send_telegram(f"🔴 *KOMA SELL SWEEP High {up_r:.1f}x at {price:.5f}* SCORE {score} VOL {'INC' if vol_inc else 'DEC'} {vol_trend:.2f}x vol {vol/vol_avg:.2f}x\nSL {sl:.5f} above wick {h:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")
    except Exception as e: print(f"KOMA err {e}")

def scan_other_one(sym, ex_public, ex_private, session, is_pick):
    try:
        df5m=pd.DataFrame(ex_public.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
        df1d=pd.DataFrame(ex_public.fetch_ohlcv(sym,'1d',limit=100),columns=['timestamp','open','high','low','close','volume'])
        if len(df5m)<25: return
        o=df5m['open'].iloc[-1]; c=df5m['close'].iloc[-1]; h=df5m['high'].iloc[-1]; l=df5m['low'].iloc[-1]
        if h==l: return
        body=abs(c-o) or ((h-l)*0.1) or 0.00001
        body_ratio=body/((h-l) or 0.00001)
        up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; CEIL=df1d['high'].tail(10).max(); FLOOR=df1d['low'].tail(10).min()
        vol=df5m['volume'].iloc[-1]; vol_prev=df5m['volume'].iloc[-2]
        vol_avg=df5m['volume'].rolling(20).mean().iloc[-1] or 1
        if vol_avg==0: vol_avg=vol or 1
        vol_trend=vol/vol_prev if vol_prev>0 else 1.0
        vol_inc = vol > vol_prev
        recent_low=df5m['low'].tail(20).min(); recent_high=df5m['high'].tail(20).max()
        swept_low = (l <= recent_low * 1.002) or (low_r >= 2.2)
        swept_high = (h >= recent_high * 0.998) or (up_r >= 2.2)

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

        print(f"{sym} {price:.5f} Up {up_r:.1f}x Low {low_r:.1f}x vol {vol/vol_avg:.2f}x trend {vol_trend:.2f}x {'INC' if vol_inc else 'DEC'} sweptL {swept_low} sweptH {swept_high}")

        if not is_pick: return

        if low_r>=1.5 and swept_low:
            if price > l * (1+SWEEP_DIST_PCT): return
            if low_r < 5.0 and vol < vol_avg*0.15: return
            # VOL INC = BUY
            if low_r < 5.0 and vol_trend < 0.75:
                print(f"SKIP {sym} BUY need VOL INC trend {vol_trend:.2f}x")
                return
            if can_send_other(sym, price):
                COOLDOWN_OTHER.setdefault("flips",{})[sym]=FLOOR; save_other()
                sl=l*(1-SL_BUFFER); risk=price-sl
                tp1=price+risk*1.5; tp2=price+risk*3.0; tp3=CEIL*(1-TP_BUFFER)
                score=int(min(low_r/3,1)*40 + min(vol_trend,2)/2*60)
                dist_pct=(price-l)/l*100
                send_telegram(f"🟢 *{sym} BUY SWEEP Low {low_r:.1f}x at {price:.5f}* SCORE {score} VOL INC {vol_trend:.2f}x dist {dist_pct:.1f}% vol {vol/vol_avg:.2f}x\nSL {sl:.5f} below wick {l:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")

        if up_r>=1.5 and swept_high:
            if price < h * (1-SWEEP_DIST_PCT): return
            if up_r < 5.0 and vol < vol_avg*0.15: return
            # VOL DEC = SELL (exhaustion)
            if up_r < 5.0 and vol_trend > 1.9:
                print(f"SKIP {sym} SELL need VOL DEC/Exhaust trend {vol_trend:.2f}x")
                return
            if can_send_other(sym, price):
                COOLDOWN_OTHER.setdefault("flips",{})[sym]=CEIL; save_other()
                sl=h*(1+SL_BUFFER); risk=sl-price
                tp1=price-risk*1.5; tp2=price-risk*3.0; tp3=FLOOR*(1+TP_BUFFER)
                score=int(min(up_r/3,1)*40 + min(vol/vol_avg/1.5,1)*60)
                dist_pct=(h-price)/h*100
                send_telegram(f"🔴 *{sym} SELL SWEEP High {up_r:.1f}x at {price:.5f}* SCORE {score} VOL {'INC' if vol_inc else 'DEC'} {vol_trend:.2f}x dist {dist_pct:.1f}% vol {vol/vol_avg:.2f}x\nSL {sl:.5f} above wick {h:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")
    except Exception as e: print(f"{sym} err {e}")

def main():
    ex_public, ex_private = get_exchanges()
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== 5% WICK=SWEEP + VOL TREND SCAN {session} UTC {hour_utc} PICK={is_pick} ===")
    scan_koma(ex_public, ex_private, session, is_pick)
    time.sleep(2)
    for s in OTHER_LIST:
        scan_other_one(s, ex_public, ex_private, session, is_pick)
        time.sleep(3)

if __name__=="__main__":
    for i in range(4):
        main()
        if i<3: time.sleep(60)
