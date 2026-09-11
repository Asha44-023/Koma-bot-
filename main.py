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
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=15)
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

def get_trend(df):
    try:
        ema9=df['close'].ewm(span=9).mean().iloc[-1]
        ema21=df['close'].ewm(span=21).mean().iloc[-1]
        ema50=df['close'].ewm(span=50).mean().iloc[-1]
        price=df['close'].iloc[-1]
        if ema9>ema21>ema50 and price>ema9: return "UP", ema9, ema21, ema50
        if ema9<ema21<ema50 and price<ema9: return "DOWN", ema9, ema21, ema50
        return "RANGE", ema9, ema21, ema50
    except: return "RANGE",0,0,0

def get_mom_rsi_vol(df):
    try:
        d=df['close'].diff(); g=(d.where(d>0,0)).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
        rs=g/l; rsi_v=100-(100/(1+rs)); rsi=float(rsi_v.iloc[-1])
    except: rsi=50
    try: mom=((df['close'].iloc[-1]-df['close'].iloc[-10])/df['close'].iloc[-10])*100
    except: mom=0
    try:
        avg=df['volume'].rolling(20).mean().iloc[-1]
        last=df['volume'].iloc[-1]
        if pd.isna(avg) or avg==0 or last==0: ratio=1.0; label="VOLx1.0"
        else:
            ratio=last/avg; ratio=min(max(ratio,0.1),5.0)
            if ratio>=2.0: label=f"WHALEVOLx{ratio:.1f}"
            elif ratio>=1.3: label=f"VOLUPx{ratio:.1f}"
            elif ratio<=0.7: label=f"VOLDOWNx{ratio:.1f}"
            else: label=f"VOLx{ratio:.1f}"
    except: ratio=1.0; label="VOLx1.0"
    return mom,rsi,ratio,label

def check_mtf_no_noise(df4h, df1h, df15m, sym):
    trend4h, _, _, _ = get_trend(df4h)
    mom4h, rsi4h, ratio4h, vol4h = get_mom_rsi_vol(df4h)
    trend1h, _, _, _ = get_trend(df1h)
    mom1h, rsi1h, ratio1h, vol1h = get_mom_rsi_vol(df1h)
    trend15m, ema9_15, _, _ = get_trend(df15m)
    mom15m, rsi15m, ratio15m, vol15m = get_mom_rsi_vol(df15m)

    score=0; reasons=[]

    # 4H DIRECTION - BIG PICTURE
    if trend4h=="UP": reasons.append("4H-UP"); score+=2
    elif trend4h=="DOWN": reasons.append("4H-DOWN"); score+=2
    else: reasons.append("4H-RANGE")

    # 1H STRUCTURE - MIDDLE
    if trend1h=="UP": reasons.append("1H-UP"); score+=2
    elif trend1h=="DOWN": reasons.append("1H-DOWN"); score+=2
    else: reasons.append("1H-RANGE")

    # WHALE GRAB 15M
    try:
        body=abs(df15m['close'].iloc[-1]-df15m['open'].iloc[-1])
        upper=df15m['high'].iloc[-1]-max(df15m['open'].iloc[-1],df15m['close'].iloc[-1])
        lower=min(df15m['open'].iloc[-1],df15m['close'].iloc[-1])-df15m['low'].iloc[-1]
        if body>0 and ratio15m>1.3:
            if upper>body*2: reasons.append("BEARLIQGRAB"); score+=2
            if lower>body*2: reasons.append("BULLLIQGRAB"); score+=2
    except: pass

    # === ANTI-FLIP 15M ENTRY - NO NOISE ===
    try:
        c0=df15m['close'].iloc[-1]; c1=df15m['close'].iloc[-2]; c2=df15m['close'].iloc[-3]
        two_up = c0>c1 and c1>c2
        two_down = c0<c1 and c1<c2
        price_above_ema = c0>ema9_15
        price_below_ema = c0<ema9_15
        # RSI not extreme
        rsi_ok = 30<rsi15m<70

        if trend15m=="UP" and mom15m>0.5 and two_up and price_above_ema and rsi_ok:
            reasons.append(f"15m-UP {mom15m:.1f}% x2 CONFIRMED"); score+=3
            entry_ok=True
        elif trend15m=="UP" and mom15m>0.5:
            reasons.append(f"15m-UP {mom15m:.1f}% WAITING 2ND"); entry_ok=False
        elif trend15m=="DOWN" and mom15m<-0.5 and two_down and price_below_ema and rsi_ok:
            reasons.append(f"15m-DOWN {mom15m:.1f}% x2 CONFIRMED"); score+=3
            entry_ok=True
        elif trend15m=="DOWN" and mom15m<-0.5:
            reasons.append(f"15m-DOWN {mom15m:.1f}% WAITING 2ND"); entry_ok=False
        else:
            reasons.append(f"15m-{trend15m} {mom15m:.1f}% NO-MOM"); entry_ok=False

        # Volume check
        if ratio15m>=1.3: reasons.append(vol15m); score+=1
        elif ratio15m<=0.5: reasons.append(f"{vol15m} LOW-VOL"); entry_ok=False; score-=1
        else: reasons.append(vol15m)

    except:
        entry_ok=False

    # ALIGNMENT BONUS - NO NOISE CORE
    if trend4h=="UP" and trend1h=="UP" and entry_ok and "CONFIRMED" in ''.join(reasons):
        decision="BUY"; emoji="🟢"; score+=3; reasons.append("ALIGNED-UP")
    elif trend4h=="DOWN" and trend1h=="DOWN" and entry_ok and "CONFIRMED" in ''.join(reasons):
        decision="SELL"; emoji="🔴"; score+=3; reasons.append("ALIGNED-DOWN")
    elif trend4h==trend1h and trend4h!="RANGE" and entry_ok:
        decision="BUY" if trend4h=="UP" else "SELL"; emoji="🟡"; score+=1
    else:
        decision="AVOID"; emoji="⚪"

    # Final filters
    if rsi15m>78 or rsi15m<22: decision="AVOID"; reasons.append(f"RSI{int(rsi15m)} EXTREME"); score=max(0,score-2)
    if "WAITING" in ''.join(reasons): decision="AVOID"; emoji="⚪"
    if score<6: decision="AVOID"; emoji="⚪"

    if score<0: score=0
    if score>10: score=10

    info = {
      "4H": f"{trend4h} mom{mom4h:.1f}% RSI{int(rsi4h)}",
      "1H": f"{trend1h} mom{mom1h:.1f}% RSI{int(rsi1h)}",
      "15M": f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m}",
      "score": score, "reasons": reasons
    }
    return decision, score, emoji, info

def safe_autopilot_enter(ex,sym,side,price,sess,score,info):
    global TRADED_THIS_RUN
    if sess=="DEAD ZONE": return False
    if score<7: return False # Only high quality
    try:
        has=False; ps=""; pp=0
        for p in ex.fetch_positions([sym]):
            c,s,pnl,_=parse_position(p)
            if abs(c)>0: has=True; ps=s; pp=pnl; break
        if has:
            want_long="buy" in side.lower(); is_long=ps=="long"
            if (want_long and is_long) or (not want_long and not is_long): return False
            if pp>0.02:
                if can_send(sym,"FLIP",10): send_telegram(f"🔄 *FLIP* {sym} {ps.upper()} ${pp:.4f} -> {side.upper()} SCORE {score}/10 | {sess}")
                close_position(ex,sym); time.sleep(1.5)
            else: return False
        if TRADED_THIS_RUN and not has: return False
        qty=int(NOTIONAL/price); qty=max(1,min(qty,MAX_QTY_CAP))
        try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
        except: pass
        ex.create_market_order(sym,side.lower(),qty)
        TRADED_THIS_RUN=True
        send_telegram(f"✅ *ENTERED MTF NO-NOISE* {sym} {side.upper()} SCORE {score}/10 {qty} @ {price} | {sess} | {','.join(info['reasons'])}")
        return True
    except: return False

def scan():
    global TRADED_THIS_RUN, ALL_SIGNALS
    TRADED_THIS_RUN=False; ALL_SIGNALS=[]
    ex=get_exchange()
    if not ex: return
    session,vol,h=get_killzone()
    try: bal=ex.fetch_balance(); free=bal['USDT']['free'] if 'USDT' in bal else 0
    except: free="?"
    for sym in SYMBOLS:
        try:
            df4h=pd.DataFrame(ex.fetch_ohlcv(sym,'4h',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
            price=df15m['close'].iloc[-1]
            decision,score,emoji,info = check_mtf_no_noise(df4h,df1h,df15m,sym)
            line=f"{emoji} *{decision}* {sym} @ {price:.5f} | SCORE {score}/10\n 4H: {info['4H']}\n 1H: {info['1H']}\n 15M: {info['15M']}\n → {','.join(info['reasons'])}"
            ALL_SIGNALS.append(line)
            if decision=="BUY": safe_autopilot_enter(ex,sym,"buy",price,ex.fetch_ohlcv(sym,'15m',limit=1)[0][0],score,info) if False else safe_autopilot_enter(ex,sym,"buy",price,get_killzone()[0],score,info)
            elif decision=="SELL": safe_autopilot_enter(ex,sym,"sell",price,get_killzone()[0],score,info)
            time.sleep(1.2)
        except Exception as e: print(f"Err {sym} {e}"); continue
    try:
        header=f"📊 *{get_killzone()[0]} KILLZONE {get_killzone()[2]}UTC - MTF NO-NOISE*\n💰 Bal: ${free} | $14.99 → $10k | ANTI-FLIP ON\n*4H Direction | 1H Structure | 15M x2 Entry*\n{'-'*35}\n\n"
        body="\n\n".join(ALL_SIGNALS)
        footer="\n\n✅ RULES:\n🟢 BUY 7-10 = 4H UP +1H UP +15m 2x CONFIRMED\n🔴 SELL 7-10 = 4H DOWN +1H DOWN +15m 2x CONFIRMED\n⚪ AVOID 0-6 = WAITING 2ND or NO ALIGN = NO NOISE"
        send_telegram(header+body+footer)
    except: pass
    print("✅ MTF No-Noise Done")

if __name__=="__main__": scan()
