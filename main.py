import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

BALANCE, TARGET, LEVERAGE, NOTIONAL, MAX_QTY_CAP = 14.99, 10000.0, 10, 3.0, 50
TRADED_THIS_RUN, ALL_SIGNALS = False, []
try: LAST_ALERT = json.load(open("cooldown.json"))
except: LAST_ALERT = {}

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
    contracts=float(p.get('contracts',0) or 0)
    info=p.get('info',{})
    if contracts==0: contracts=float(info.get('holdVol',0) or info.get('vol',0) or 0)
    side=(p.get('side') or info.get('positionSide') or '').lower()
    if not side and abs(contracts)>0:
        s=str(info).lower()
        if 'long' in s or info.get('positionType')==1: side='long'
        elif 'short' in s or info.get('positionType')==2: side='short'
        else: side='long'
    pnl=p.get('unrealizedPnl')
    if pnl is None: pnl=info.get('unrealisedPnl') or info.get('unrealizedPnl') or 0
    try: pnl=float(pnl or 0)
    except: pnl=0.0
    return contracts,side,pnl,info

def close_position(ex,sym):
    try:
        for p in ex.fetch_positions([sym]):
            c,s,_,_=parse_position(p)
            if abs(c)>0:
                ex.create_market_order(sym,"sell" if s=="long" else "buy",abs(c),params={"reduceOnly":True})
                time.sleep(0.5); return True
    except: pass
    return False

def get_killzone():
    h=datetime.now(timezone.utc).hour
    if 0<=h<6: return "ASIAN","Range",h
    if 7<=h<12: return "LONDON","Breakout",h
    if 12<=h<17: return "NEW YORK","Trend",h
    if 17<=h<20: return "LONDON CLOSE","Reversal",h
    return "DEAD ZONE","Avoid",h

def can_send(sym,typ,mins):
    k=f"{sym}_{typ}"; now=time.time()
    if now-LAST_ALERT.get(k,0)>mins*60:
        LAST_ALERT[k]=now
        try: json.dump(LAST_ALERT,open("cooldown.json","w"))
        except: pass
        return True
    return False

def detect_whale_manipulation(df):
    r=[]
    try:
        avg=df['volume'].rolling(20).mean().iloc[-1]
        last=df['volume'].iloc[-1]
        prev=df['volume'].iloc[-2] if len(df)>1 else last
        if pd.isna(avg) or avg==0:
            avg=df['volume'].replace(0,pd.NA).rolling(20).mean().iloc[-1]
            if pd.isna(avg) or avg==0: avg=last if last>0 else 1
        if prev==0 or pd.isna(prev): prev=avg
        ratio=last/avg if avg>0 else 1.0
        ratio=min(ratio,5.0)
        chg=abs(df['close'].iloc[-1]-df['open'].iloc[-1])/df['open'].iloc[-1]*100 if df['open'].iloc[-1]!=0 else 0
        body=abs(df['close'].iloc[-1]-df['open'].iloc[-1])
        upper=df['high'].iloc[-1]-max(df['open'].iloc[-1],df['close'].iloc[-1])
        lower=min(df['open'].iloc[-1],df['close'].iloc[-1])-df['low'].iloc[-1]
        if ratio>=2.0: r.append(f"WHALEVOLx{ratio:.1f}")
        elif ratio>=1.3: r.append(f"VOLUPx{ratio:.1f}")
        elif ratio<=0.7 and last>0: r.append(f"VOLDOWNx{ratio:.1f}")
        else: r.append(f"VOLx{ratio:.1f}")
        if ratio>1.8 and chg<0.15: r.append("LIQABSORPTION")
        if body>0:
            if upper>body*2 and ratio>1.3: r.append("BEARLIQGRAB")
            if lower>body*2 and ratio>1.3: r.append("BULLLIQGRAB")
        if last>0 and prev>0:
            if df['close'].iloc[-1]>df['close'].iloc[-2] and last<prev*0.8: r.append("BEARVOL-DIV")
            if df['close'].iloc[-1]<df['close'].iloc[-2] and last<prev*0.8: r.append("BULLVOL-DIV")
        if ratio>1.3 and df['close'].iloc[-1]>df['close'].iloc[-2] and df['close'].iloc[-2]>df['close'].iloc[-3]: r.append("WHALEPUMPING")
        if ratio>1.3 and df['close'].iloc[-1]<df['close'].iloc[-2] and df['close'].iloc[-2]<df['close'].iloc[-3]: r.append("WHALEDUMPING")
    except: r.append("VOLx1.0")
    return r

def check_filters(df,sym):
    rsn,mom,rsi=[],0,50
    try:
        d=df['close'].diff(); g=(d.where(d>0,0)).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean(); rs=g/l; rsi_v=100-(100/(1+rs)); rsi=rsi_v.iloc[-1]
        if "KOMA" in sym and rsi>47: rsn.append(f"RSI{int(rsi)}")
        elif rsi>70: rsn.append(f"RSI{int(rsi)}OB")
        if rsi<30: rsn.append(f"RSI{int(rsi)}OS")
    except: pass
    try: rsn.append("BULLOB" if df['close'].iloc[-1]>df['open'].iloc[-1] else "BEAROB")
    except: rsn.append("BULLOB")
    try: rsn.append("WPATTERN" if df['close'].iloc[-1]>df['close'].iloc[-2] else "MPATTERN")
    except: pass
    try:
        mom=((df['close'].iloc[-1]-df['close'].iloc[-3])/df['close'].iloc[-3])*100
        if mom<-0.5: rsn.append("MARKETDUMPING")
        elif mom>0.5: rsn.append("MARKETPUMPING")
        else: rsn.append("NEUTRAL")
    except: rsn.append("NEUTRAL")
    rsn.extend(detect_whale_manipulation(df))
    if "KOMA" in sym and mom>1.0: rsn.append("KOMAPUMPOVERRIDE")
    return rsn,mom,rsi

def monitor_profit_rule(ex,sym,df,rsn,sess):
    try:
        for p in ex.fetch_positions([sym]):
            c,s,pnl,_=parse_position(p)
            if abs(c)>0 and pnl!=0:
                avg=df['volume'].rolling(20).mean().iloc[-1]
                if pd.isna(avg) or avg==0: avg=1
                ratio=df['volume'].iloc[-1]/avg if avg>0 else 1
                if pnl>0.05 and ("WHALEPUMPING" in rsn or "MARKETPUMPING" in rsn) and ratio>1.5:
                    if can_send(sym,"HOLD_PUMP",30): send_telegram(f"💎 *HOLD* {sym} {s.upper()} ${pnl:.4f} x{ratio:.1f} PUMPING")
                    return "HOLD"
                if "LIQABSORPTION" in rsn and pnl>=0:
                    if can_send(sym,"ABSORPTION",30): send_telegram(f"🐋 *ABSORPTION* {sym} {s.upper()} ${pnl:.4f} - HOLD BIG MOVE!")
                    return "HOLD"
                if "BULLLIQGRAB" in rsn or "BEARLIQGRAB" in rsn:
                    if can_send(sym,"LIQGRAB",30): send_telegram(f"🐋 *LIQ GRAB* {sym} {s.upper()} ${pnl:.4f} - HOLD!")
                    return "HOLD"
                if pnl>0.08 and ("MARKETDUMPING" in rsn or "WHALEDUMPING" in rsn):
                    if can_send(sym,"TAKE",15): send_telegram(f"📉 *TAKE* {sym} {s.upper()} ${pnl:.4f} DUMPING x{ratio:.1f}")
                    return "TAKE"
        return "NONE"
    except: return "NONE"

def safe_autopilot_enter(ex,sym,side,price,sess,df,rsn):
    global TRADED_THIS_RUN
    if sess=="DEAD ZONE": return False
    try:
        has=False; ps=""; pp=0
        for p in ex.fetch_positions([sym]):
            c,s,pnl,_=parse_position(p)
            if abs(c)>0: has=True; ps=s; pp=pnl; break
        hold=monitor_profit_rule(ex,sym,df,rsn,sess)
        if hold=="HOLD": return False
        if hold=="TAKE" and has and pp>0: close_position(ex,sym); time.sleep(1)
        if has:
            want_long="buy" in side.lower(); is_long=ps=="long"
            if (want_long and is_long) or (not want_long and not is_long): return False
            if pp>0.02:
                if can_send(sym,"FLIP",10): send_telegram(f"🔄 *FLIP* {sym} {ps.upper()} ${pp:.4f} -> {side.upper()} | {sess}")
                close_position(ex,sym); time.sleep(1.5)
            else: return False
        if TRADED_THIS_RUN and not has: return False
        qty=int(NOTIONAL/price); qty=max(1,min(qty,MAX_QTY_CAP))
        try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
        except: pass
        ex.create_market_order(sym,side.lower(),qty)
        TRADED_THIS_RUN=True
        whale=','.join([r for r in rsn if 'VOL' in r or 'LIQ' in r or 'WHALE' in r])
        send_telegram(f"✅ *ENTERED* {sym} {side.upper()} {qty} @ {price} | {sess} | {whale}")
        return True
    except Exception as e:
        if "2051" in str(e) or "maximum" in str(e).lower():
            try:
                q=int(1.0/price); q=max(1,min(q,10))
                ex.create_market_order(sym,side.lower(),q); TRADED_THIS_RUN=True
                send_telegram(f"✅ *ENTERED SMALL* {sym} {side} {q} @ {price} | {sess}"); return True
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
            price=df['close'].iloc[-1]; rsn,mom,rsi=check_filters(df,sym)
            sess,v,_=get_killzone()
            if sess in ["LONDON","NEW YORK"]: rsn.append(f"{sess}KILLZONE")
            side="BUY LONG" if "BULLOB" in rsn or "WPATTERN" in rsn or "BULLLIQGRAB" in rsn or "WHALEPUMPING" in rsn or "KOMAPUMPOVERRIDE" in rsn else "SELL SHORT"
            if "BEARLIQGRAB" in rsn or "WHALEDUMPING" in rsn: side="SELL SHORT"
            ALL_SIGNALS.append(f"{side} {sym} @ {price:.5f} mom {mom:.1f}% RSI {int(rsi)} | {','.join(rsn)}")
            oside="buy" if "BUY" in side else "sell"
            safe_autopilot_enter(ex,sym,oside,price,sess,df,rsn)
            time.sleep(1)
        except Exception as e: print(f"Err {sym} {e}"); continue
    try:
        lines=[]
        for sig in ALL_SIGNALS:
            try:
                main,details=sig.split("|") if "|" in sig else (sig,"")
                whale_icon="🐋" if any(x in details for x in ["WHALE","LIQGRAB","ABSORPTION"]) else "📍"
                vol_icon="🔥" if "VOLUP" in details or "WHALEVOL" in details else "💤" if "VOLDOWN" in details else "📊"
                lines.append(f"{whale_icon} {main.strip()}\n {vol_icon} {details.strip()}\n")
            except: lines.append(f"{sig}\n")
        summary=f"📊 *{session} KILLZONE {h}UTC - {vol}*\n💰 Bal: ${free} | $14.99 → $10k 10x\n{'-'*30}\n\n" + "\n".join(lines)
        send_telegram(summary)
    except: pass
    print("✅ Done Perfect")

if __name__=="__main__": scan()
