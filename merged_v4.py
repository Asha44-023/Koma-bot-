import ccxt, pandas as pd, time, json, os, requests
from datetime import datetime, timezone

SYMBOLS=["KOMA/USDT:USDT","GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
PURE_PICK={"ASIAN":[23,0,1],"FRANKFURT":[6,7],"LONDON":[8,9],"NEW YORK":[13,14]}
PICK_HOURS={"ASIAN":[23,0,1],"FRANKFURT":[6,7,8],"LONDON":[8,9,10,11,12],"NEW YORK":[13,14,15,16,17,18,19,20,21,22,23]}
SIGNAL_COOLDOWN_MIN=45
NO_REENTRY_CANDLES=4
WHALE_VOL=2.5

try: COOLDOWN=json.load(open("cooldown.json"))
except: COOLDOWN={"signals":{},"exits":{}}

def save_cooldown():
    try: json.dump(COOLDOWN,open("cooldown.json","w"))
    except: pass

def send_telegram(msg):
    print(msg)
    token=os.getenv("TELEGRAM_BOT_TOKEN")
    chat=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if token and chat:
        try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id":chat,"text":msg}, timeout=10)
        except: pass

def get_killzone():
    h=datetime.now(timezone.utc).hour
    for sess,hrs in PURE_PICK.items():
        if h in hrs: return f"{sess} PICK",h,True
    for sess,hrs in PICK_HOURS.items():
        if h in hrs: return sess,h,False
    return "DEAD ZONE",h,False

def can_send(sym):
    now=time.time()
    if now-COOLDOWN.get("exits",{}).get(sym,0) < NO_REENTRY_CANDLES*5*60: return False
    last=COOLDOWN.get("signals",{}).get(sym,0)
    if now-last > SIGNAL_COOLDOWN_MIN*60 or sym not in COOLDOWN.get("signals",{}):
        COOLDOWN["signals"][sym]=now; save_cooldown(); return True
    return False

def get_vol_trends(ex, sym):
    try:
        df1=pd.DataFrame(ex.fetch_ohlcv(sym,'1m',limit=10),columns=['t','o','h','l','c','v'])
        df3=pd.DataFrame(ex.fetch_ohlcv(sym,'3m',limit=10),columns=['t','o','h','l','c','v'])
        df5=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=30),columns=['t','o','h','l','c','v'])
        df15=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=20),columns=['t','o','h','l','c','v'])
        v1t=df1['v'].iloc[-2]/df1['v'].iloc[-3] if df1['v'].iloc[-3]>0 else 1.0
        v3t=df3['v'].iloc[-2]/df3['v'].iloc[-3] if df3['v'].iloc[-3]>0 else 1.0
        v5t=df5['v'].iloc[-2]/df5['v'].iloc[-3] if df5['v'].iloc[-3]>0 else 1.0
        v15t=df15['v'].iloc[-2]/df15['v'].iloc[-3] if df15['v'].iloc[-3]>0 else 1.0
        v5_avg=df5['v'].iloc[-22:-2].mean() or 1
        v5_3trend=df5['v'].iloc[-4:-1].mean()/(df5['v'].iloc[-7:-4].mean() or 1)
        return v1t,v3t,v5t,v15t,df5['v'].iloc[-2]/v5_avg,v5_3trend,df5
    except:
        return 1.0,1.0,1.0,1.0,None

def scan(sym, ex, session, is_pick):
    try:
        v1t,v3t,v5t,v15t,vol_x_avg,v5_3trend,df5m = get_vol_trends(ex,sym)
        if df5m is None: return
        df1d=pd.DataFrame(ex.fetch_ohlcv(sym,'1d',limit=20),columns=['t','o','h','l','c','v'])
        if len(df5m)<25: return
        i=-2; o,c,h,l=df5m['o'].iloc[i],df5m['c'].iloc[i],df5m['h'].iloc[i],df5m['l'].iloc[i]
        body=abs(c-o) or (h-l)*0.2; up_r=(h-max(o,c))/body; low_r=(min(o,c)-l)/body
        price=c; bullish=c>o; bearish=c<o
        CEIL=df1d['h'].tail(10).max(); FLOOR=df1d['l'].tail(10).min()
        LOCAL_CEIL=df5m['h'].iloc[-22:-2].max(); LOCAL_FLOOR=df5m['l'].iloc[-22:-2].min()
        recent_low=df5m['l'].iloc[-22:-2].min(); recent_high=df5m['h'].iloc[-22:-2].max()
        swept_low=(l<=recent_low*1.002) or (low_r>=2.2); swept_high=(h>=recent_high*0.998) or (up_r>=2.2)
        near_ceiling=price>=CEIL*0.998; near_floor=price<=FLOOR*1.002; is_middle=not near_ceiling and not near_floor
        print(f"{sym} {price:.5f} L{low_r:.1f} H{up_r:.1f} 1m{v1t:.1f}x 3m{v3t:.1f}x 5m{v5t:.1f}x 15m{v15t:.1f}x vol{vol_x_avg:.1f}x [{session}]")
        if not is_pick: return
        if up_r>=3.0 and low_r>=3.0: return
        retail_slow_buy = v1t>=1.3 and v3t>=1.2 and v5t>=1.1 and v15t>=1.0 and bullish and low_r<1.5
        retail_slow_sell = v1t>=1.3 and v3t>=1.2 and v5t>=1.1 and v15t>=1.0 and bearish and up_r<1.5
        whale_flash_buy = v1t>=2.5 and low_r>=2.0 and bullish
        whale_flash_sell = v1t>=2.5 and up_r>=2.0 and bearish
        buy_wick = low_r>=1.2 and swept_low and v5t>=0.75
        buy_vol_middle = v5t>=1.25 and bullish and v5_3trend>=1.15 and is_middle
        sell_wick = up_r>=1.2 and swept_high and v5t<=1.9
        sell_vol_middle = v5t<=0.80 and bearish and v5_3trend<=0.90 and is_middle
        if (retail_slow_buy or whale_flash_buy or buy_wick or buy_vol_middle) and can_send(sym):
            sl = FLOOR*0.988 if near_floor else LOCAL_FLOOR*0.988 if is_middle else l*0.988
            if price-sl>0:
                tp1=price+(price-sl)*1.5; tp2=price+(price-sl)*3.0; tp3=CEIL*0.994 if near_floor else LOCAL_CEIL*0.994
                tag=""
                if retail_slow_buy: tag+=" RETAIL SLOW BUY→15m/1H"
                if whale_flash_buy: tag+=" WHALE FLASH BUY⚡"
                if buy_vol_middle: tag+=" VOL🔼"
                if buy_wick: tag+=" WICK"
                if vol_x_avg and vol_x_avg>=WHALE_VOL: tag+=" WHALE"
                send_telegram(f"🟢 {sym} BUY {low_r:.1f}x{tag} at {price:.5f} 1m{v1t:.1f}x 3m{v3t:.1f}x 5m{v5t:.1f}x [{session}] SL {sl:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")
        if (retail_slow_sell or whale_flash_sell or sell_wick or sell_vol_middle) and can_send(sym):
            sl = CEIL*1.012 if near_ceiling else LOCAL_CEIL*1.012 if is_middle else h*1.012
            if sl-price>0:
                tp1=price-(sl-price)*1.5; tp2=price-(sl-price)*3.0; tp3=FLOOR*1.006 if near_ceiling else LOCAL_FLOOR*1.006
                tag=""
                if retail_slow_sell: tag+=" RETAIL SLOW SELL→15m/1H"
                if whale_flash_sell: tag+=" WHALE FLASH SELL⚡"
                if sell_vol_middle: tag+=" VOL🔽"
                if sell_wick: tag+=" WICK"
                send_telegram(f"🔴 {sym} SELL {up_r:.1f}x{tag} at {price:.5f} 1m{v1t:.1f}x 3m{v3t:.1f}x 5m{v5t:.1f}x [{session}] SL {sl:.5f} TP1 {tp1:.5f} TP2 {tp2:.5f} TP3 {tp3:.5f}")
    except Exception as e: print(f"{sym} err {e}")

def main():
    ex=ccxt.mexc({'enableRateLimit':True})
    session,hour_utc,is_pick=get_killzone()
    print(f"\n=== FINAL V4 RETAIL+WHALE 1m+3m+5m+15m {session} UTC {hour_utc} ===")
    for s in SYMBOLS: scan(s,ex,session,is_pick); time.sleep(1.5)

if __name__=="__main__": main()
