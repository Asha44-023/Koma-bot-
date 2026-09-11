import os, ccxt, pandas as pd, requests, time
from datetime import datetime, timezone

BALANCE, TARGET, LEVERAGE, NOTIONAL, MAX_QTY_CAP = 14.99, 10000.0, 10, 3.0, 50
TRADED_THIS_RUN, ALL_SIGNALS = False, []
LAST_ALERT = {} # COOLDOWN TRACKER
SYMBOLS = ["KOMA/USDT:USDT","GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","VELVET/USDT:USDT"]
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")
MEXC_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET") or os.getenv("API_SECRET")

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except: pass

def get_exchange():
    if not MEXC_KEY or not MEXC_SECRET: return None
    return ccxt.mexc({'apiKey': MEXC_KEY,'secret': MEXC_SECRET,'options': {'defaultType': 'swap'},'enableRateLimit': True})

def parse_position(p):
    contracts = float(p.get('contracts',0) or 0)
    info = p.get('info',{})
    if contracts == 0: contracts = float(info.get('holdVol',0) or info.get('vol',0) or 0)
    side = (p.get('side') or info.get('positionSide') or info.get('side') or '').lower()
    if not side and abs(contracts)>0:
        s = str(info).lower()
        if 'long' in s or info.get('positionType')==1: side='long'
        elif 'short' in s or info.get('positionType')==2: side='short'
        else: side='long'
    pnl = p.get('unrealizedPnl')
    if pnl is None: pnl = info.get('unrealisedPnl') or info.get('unrealizedPnl') or 0
    try: pnl=float(pnl or 0)
    except: pnl=0.0
    return contracts, side, pnl, info

def close_position(exchange,symbol):
    try:
        for p in exchange.fetch_positions([symbol]):
            c,s,pnl,_=parse_position(p)
            if abs(c)>0:
                side="sell" if s=="long" else "buy"
                exchange.create_market_order(symbol,side,abs(c),params={"reduceOnly":True})
                time.sleep(0.5)
                return True
    except: pass
    return False

def get_killzone():
    h=datetime.now(timezone.utc).hour
    if 0<=h<6: return "ASIAN","Range",h
    if 7<=h<12: return "LONDON","Breakout",h
    if 12<=h<17: return "NEW YORK","Trend",h
    if 17<=h<20: return "LONDON CLOSE","Reversal",h
    return "DEAD ZONE","Avoid",h

def can_send(symbol, typ, mins):
    key=f"{symbol}_{typ}"
    now=time.time()
    last=LAST_ALERT.get(key,0)
    if now-last>mins*60:
        LAST_ALERT[key]=now
        return True
    return False

def detect_whale_manipulation(df):
    reasons=[]
    try:
        avg_vol=df['volume'].rolling(20).mean().iloc[-1]
        last_vol=df['volume'].iloc[-1]
        prev_vol=df['volume'].iloc[-2] if len(df)>2 else last_vol
        vol_ratio=last_vol/avg_vol if avg_vol>0 else 1
        price_change=abs(df['close'].iloc[-1]-df['open'].iloc[-1])/df['open'].iloc[-1]*100 if df['open'].iloc[-1]!=0 else 0
        body=abs(df['close'].iloc[-1]-df['open'].iloc[-1])
        upper=df['high'].iloc[-1]-max(df['open'].iloc[-1],df['close'].iloc[-1])
        lower=min(df['open'].iloc[-1],df['close'].iloc[-1])-df['low'].iloc[-1]

        if vol_ratio>2.0: reasons.append(f"WHALEVOLx{vol_ratio:.1f}")
        elif vol_ratio>1.5: reasons.append(f"VOLUPx{vol_ratio:.1f}")
        elif vol_ratio<0.5: reasons.append(f"VOLDOWNx{vol_ratio:.1f}")
        else: reasons.append(f"VOLx{vol_ratio:.1f}")

        if vol_ratio>1.8 and price_change<0.15: reasons.append("LIQABSORPTION")
        if body>0:
            if upper>body*2 and vol_ratio>1.3: reasons.append("BEARLIQGRAB")
            if lower>body*2 and vol_ratio>1.3: reasons.append("BULLLIQGRAB")
        if df['close'].iloc[-1]>df['close'].iloc[-2] and last_vol<prev_vol*0.8: reasons.append("BEARVOL-DIV")
        if df['close'].iloc[-1]<df['close'].iloc[-2] and last_vol<prev_vol*0.8: reasons.append("BULLVOL-DIV")
        if vol_ratio>1.5 and df['close'].iloc[-1]>df['close'].iloc[-2] and df['close'].iloc[-2]>df['close'].iloc[-3]: reasons.append("WHALEPUMPING")
        if vol_ratio>1.5 and df['close'].iloc[-1]<df['close'].iloc[-2] and df['close'].iloc[-2]<df['close'].iloc[-3]: reasons.append("WHALEDUMPING")
    except: pass
    return reasons

def check_filters(df,symbol):
    reasons,mom,last_rsi=[],0,50
    try:
        d=df['close'].diff(); g=(d.where(d>0,0)).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean(); rs=g/l; rsi=100-(100/(1+rs)); last_rsi=rsi.iloc[-1]
        if "KOMA" in symbol and last_rsi>47: reasons.append(f"RSI{int(last_rsi)}")
        elif last_rsi>70: reasons.append(f"RSI{int(last_rsi)}OB")
        if last_rsi<30: reasons.append(f"RSI{int(last_rsi)}OS")
    except: pass
    try: reasons.append("BULLOB" if df['close'].iloc[-1]>df['open'].iloc[-1] else "BEAROB")
    except: reasons.append("BULLOB")
    try:
        if df['close'].iloc[-1]>df['close'].iloc[-2]: reasons.append("WPATTERN")
        else: reasons.append("MPATTERN")
    except: pass
    try:
        mom=((df['close'].iloc[-1]-df['close'].iloc[-3])/df['close'].iloc[-3])*100
        if mom<-0.5: reasons.append("MARKETDUMPING")
        elif mom>0.5: reasons.append("MARKETPUMPING")
        else: reasons.append("NEUTRAL")
    except: reasons.append("NEUTRAL")
    reasons.extend(detect_whale_manipulation(df))
    if "KOMA" in symbol and mom>1.0: reasons.append("KOMAPUMPOVERRIDE")
    return reasons,mom,last_rsi

def monitor_profit_rule(exchange,symbol,df,reasons,session):
    try:
        for p in exchange.fetch_positions([symbol]):
            c,s,pnl,_=parse_position(p)
            if abs(c)>0 and pnl!=0:
                avg=df['volume'].rolling(20).mean().iloc[-1]; last=df['volume'].iloc[-1]; ratio=last/avg if avg>0 else 1
                if pnl>0.05 and ("WHALEPUMPING" in reasons or "MARKETPUMPING" in reasons) and ratio>1.5:
                    if can_send(symbol,"HOLD_PUMP",30):
                        send_telegram(f"💎 *HOLD PROFIT* {symbol} {s.upper()} PnL ${pnl:.4f} VOL x{ratio:.1f} PUMPING - Let it run! (General rule)")
                    return "HOLD"
                if "LIQABSORPTION" in reasons and pnl>=0:
                    if can_send(symbol,"ABSORPTION",30):
                        send_telegram(f"🐋 *WHALE ABSORPTION* {symbol} {s.upper()} PnL ${pnl:.4f} Vol x{ratio:.1f} stuck - BIG MOVE HOLD!")
                    return "HOLD"
                if "BULLLIQGRAB" in reasons:
                    if can_send(symbol,"BULLGRAB",30):
                        send_telegram(f"🐋 *BULL LIQ GRAB* {symbol} {s.upper()} Whale stop hunt - PUMP coming HOLD!")
                    return "HOLD"
                if "BEARLIQGRAB" in reasons:
                    if can_send(symbol,"BEARGRAB",30):
                        send_telegram(f"🐋 *BEAR LIQ GRAB* {symbol} {s.upper()} Whale stop hunt - DUMP coming HOLD!")
                    return "HOLD"
                if pnl>0.08 and ("MARKETDUMPING" in reasons or "WHALEDUMPING" in reasons):
                    if can_send(symbol,"TAKE",15):
                        send_telegram(f"📉 *TAKE PROFIT* {symbol} {s.upper()} PnL ${pnl:.4f} DUMPING Vol x{ratio:.1f} - Close now!")
                    return "TAKE"
                if "BEARVOL-DIV" in reasons and s=="long" and pnl>0.05:
                    if can_send(symbol,"VOLDIV",20):
                        send_telegram(f"⚠️ *VOL DIVERGENCE* {symbol} Price up Vol down - Fake pump take profit! PnL ${pnl:.4f}")
                    return "TAKE"
        return "NONE"
    except: return "NONE"

def safe_autopilot_enter(exchange,symbol,side,price,session,df,reasons):
    global TRADED_THIS_RUN
    if session=="DEAD ZONE": return False
    try:
        positions=exchange.fetch_positions([symbol])
        has=False; ps=""; pp=0
        for p in positions:
            c,s,pnl,_=parse_position(p)
            if abs(c)>0: has=True; ps=s; pp=pnl; break
        hold_status=monitor_profit_rule(exchange,symbol,df,reasons,session)
        if hold_status=="HOLD": return False
        if hold_status=="TAKE" and has and pp>0:
            close_position(exchange,symbol); time.sleep(1)
        if has:
            want_long="buy" in side.lower(); is_long=ps=="long"
            if (want_long and is_long) or (not want_long and not is_long): return False
            if pp>0.02:
                if can_send(symbol,"FLIP",10):
                    send_telegram(f"🔄 *FLIP* {symbol} {ps.upper()} ${pp:.4f} -> {side.upper()} | {session}")
                close_position(exchange,symbol); time.sleep(1.5)
            else: return False
        if TRADED_THIS_RUN and not has: return False
        qty=int(NOTIONAL/price); qty=max(1,min(qty,MAX_QTY_CAP))
        try: exchange.set_leverage(LEVERAGE,symbol); exchange.set_margin_mode('isolated',symbol)
        except: pass
        exchange.create_market_order(symbol,side.lower(),qty)
        TRADED_THIS_RUN=True
        whale_info=','.join([r for r in reasons if 'VOL' in r or 'LIQ' in r or 'WHALE' in r])
        send_telegram(f"✅ *ENTERED* {symbol} {side.upper()} {qty} @ {price} | {session} | {whale_info}")
        return True
    except Exception as e:
        err=str(e)
        if "2051" in err or "maximum" in err.lower():
            try:
                q=int(1.0/price); q=max(1,min(q,10))
                exchange.create_market_order(symbol,side.lower(),q)
                TRADED_THIS_RUN=True
                send_telegram(f"✅ *ENTERED SMALL* {symbol} {side} {q} @ {price} | {session}")
                return True
            except: return False
        return False

def scan():
    global TRADED_THIS_RUN, ALL_SIGNALS
    TRADED_THIS_RUN=False; ALL_SIGNALS=[]
    ex=get_exchange()
    if not ex: return
    session,vol,h=get_killzone()
    try:
        bal=ex.fetch_balance(); free=bal['USDT']['free'] if 'USDT' in bal else 0
        for s in ["buy","sell"]:
            try: ex.create_market_order("ANIME/USDT:USDT",s,50,params={"reduceOnly":True})
            except: pass
    except: free="?"
    for sym in SYMBOLS:
        try:
            ohlcv=ex.fetch_ohlcv(sym,'15m',limit=100)
            df=pd.DataFrame(ohlcv,columns=['timestamp','open','high','low','close','volume'])
            price=df['close'].iloc[-1]; reasons,mom,rsi=check_filters(df,sym)
            sess,v,h=get_killzone()
            if sess in ["LONDON","NEW YORK"]: reasons.append(f"{sess}KILLZONE")
            score=85 if "KOMAPUMPOVERRIDE" in reasons or "BULLLIQGRAB" in reasons else 75
            if "WHALEPUMPING" in reasons: score+=5
            side="BUY LONG" if "BULLOB" in reasons or "WPATTERN" in reasons or "BULLLIQGRAB" in reasons or "WHALEPUMPING" in reasons or "KOMAPUMPOVERRIDE" in reasons else "SELL SHORT"
            if "BEARLIQGRAB" in reasons or "WHALEDUMPING" in reasons: side="SELL SHORT"
            ALL_SIGNALS.append(f"{side} {sym} @ {price:.5f} mom {mom:.1f}% RSI {int(rsi)} | {','.join(reasons)}")
            oside="buy" if "BUY" in side else "sell"
            safe_autopilot_enter(ex,sym,oside,price,sess,df,reasons)
            time.sleep(1)
        except Exception as e: print(f"Err {sym} {e}"); continue
    try:
        summary=f"📊 *SCAN {session} {h}UTC {vol}* | Bal ${free}\n$14.99 -> $10000 LEV 10x\n\n" + "\n".join(ALL_SIGNALS)
        send_telegram(summary)
    except: pass
    print("✅ Done Whale + Cooldown")

if __name__=="__main__": scan()
