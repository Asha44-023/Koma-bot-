import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

# === CONFIG ===
BALANCE_START = 14.99
TARGET = 10000.0
LEVERAGE = 10
MAX_QTY_CAP = 5000
TRADED_THIS_RUN, ALL_SIGNALS = False, []
try: LAST_ALERT = json.load(open("cooldown.json"))
except: LAST_ALERT = {}

def get_env_clean(*names):
    for n in names:
        v = os.getenv(n)
        if v:
            v = v.strip().replace('"','').replace("'","").replace("\n","").replace("\r","").replace(" ","")
            if len(v) > 3: return v
    return None

MEXC_KEY = get_env_clean("MEXC_API_KEY","MEXC_APIKEY","API_KEY","MEXC_KEY","KEY")
MEXC_SECRET = get_env_clean("MEXC_API_SECRET","MEXC_SECRET","API_SECRET","SECRET")
TELEGRAM_TOKEN = get_env_clean("TELEGRAM_BOT_TOKEN","BOT_TOKEN","TELEGRAM_TOKEN")
TELEGRAM_CHAT = get_env_clean("TELEGRAM_CHAT_ID","CHAT_ID","TELEGRAM_CHAT")

auto_env = get_env_clean("AUTOPILOT_ENABLED")
AUTOPILOT_ENABLED = True if not auto_env else str(auto_env).lower() in ["true","1","on","yes"]

SYMBOLS = ["SIREN/USDT:USDT","LAB/USDT:USDT","KOMA/USDT:USDT"] # YOUR SPECIAL FAST COINS - KEPT
SCALP_TP1 = 0.015
SCALP_SL = 0.008

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_exchange():
    if not MEXC_KEY or not MEXC_SECRET: print("❌ KEYS MISSING"); return None
    print(f"✅ MEXC OK {MEXC_KEY[:4]}..."); return ccxt.mexc({'apiKey': MEXC_KEY,'secret': MEXC_SECRET,'options': {'defaultType': 'swap'},'enableRateLimit': True})

def get_auto_notional(free_bal):
    try: bal=float(free_bal)
    except: bal=BALANCE_START
    if bal<50: return 3.0
    if bal<100: return 5.0
    if bal<300: return 10.0
    if bal<1000: return 20.0
    if bal<3000: return 35.0
    return 50.0

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
    entry=info.get('openPrice') or info.get('avgPrice') or p.get('entryPrice') or 0
    try: pnl=float(pnl or 0); entry=float(entry or 0)
    except: pnl=0.0; entry=0.0
    return contracts,side,pnl,entry,info

def close_position(ex,sym):
    try:
        for p in ex.fetch_positions([sym]):
            c,s,_,_,_=parse_position(p)
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
        if ema9>ema21>ema50 and price>ema9: return "UP",0,0,0
        if ema9<ema21<ema50 and price<ema9: return "DOWN",0,0,0
        return "RANGE",0,0,0
    except: return "RANGE",0,0,0

def get_mom_rsi_vol(df):
    try:
        d=df['close'].diff(); g=(d.where(d>0,0)).rolling(14).mean(); l=(-d.where(d<0,0)).rolling(14).mean()
        rs=g/l; rsi_v=100-(100/(1+rs)); rsi=float(rsi_v.iloc[-1])
    except: rsi=50
    try: mom=((df['close'].iloc[-1]-df['close'].iloc[-10])/df['close'].iloc[-10])*100
    except: mom=0
    try:
        avg=df['volume'].rolling(20).mean().iloc[-1]; last=df['volume'].iloc[-1]
        if pd.isna(avg) or avg==0 or last==0: ratio=1.0; label="VOLx1.0"
        else:
            ratio=last/avg; ratio=min(max(ratio,0.1),5.0)
            if ratio>=3.0: label=f"🔥WHALEVOLx{ratio:.1f}"
            elif ratio>=1.5: label=f"VOLUPx{ratio:.1f}"
            elif ratio<=0.5: label=f"VOLDOWNx{ratio:.1f} LOW"
            else: label=f"VOLx{ratio:.1f}"
    except: ratio=1.0; label="VOLx1.0"
    return mom,rsi,ratio,label

def detect_whale_manipulation(df):
    try:
        o=df['open'].iloc[-1]; c=df['close'].iloc[-1]; h=df['high'].iloc[-1]; l=df['low'].iloc[-1]
        body=abs(c-o)
        if body==0: body=0.0001
        upper=h-max(o,c); lower=min(o,c)-l
        if lower>body*2.5 and upper<body*0.5: return "BULL_LIQ_GRAB", f"BULL LIQ GRAB {lower/body:.1f}x"
        if upper>body*2.5 and lower<body*0.5: return "BEAR_LIQ_GRAB", f"BEAR LIQ GRAB {upper/body:.1f}x"
        if upper>body*1.5 and lower>body*1.5: return "WHALE_WICK", "WHALE WICK"
        return None,""
    except: return None,""

def detect_w_m_pattern(df):
    try:
        c0=df['close'].iloc[-1]; c1=df['close'].iloc[-2]
        l0=df['low'].iloc[-1]; l1=df['low'].iloc[-2]; l2=df['low'].iloc[-3]
        h0=df['high'].iloc[-1]; h1=df['high'].iloc[-2]; h2=df['high'].iloc[-3]
        if l0>l1 and l1<l2 and l0>l1*0.998 and c0>c1: return "W_PATTERN","W DOUBLE BOTTOM"
        if h0<h1 and h1>h2 and h0<h1*1.002 and c0<c1: return "M_PATTERN","M DOUBLE TOP"
        return None,""
    except: return None,""

def check_scalp_engine(df4h, df1h, df15m, df5m, sym, has_long, has_short, entry_price):
    trend4h,_,_,_ = get_trend(df4h)
    mom4h,rsi4h,_,_ = get_mom_rsi_vol(df4h)
    trend1h,_,_,_ = get_trend(df1h)
    mom1h,rsi1h,_,_ = get_mom_rsi_vol(df1h)
    trend15m,_,_,_ = get_trend(df15m)
    mom15m,rsi15m,ratio15m,vol15m = get_mom_rsi_vol(df15m)
    mom5m,rsi5m,ratio5m,vol5m = get_mom_rsi_vol(df5m)
    price=df5m['close'].iloc[-1]
    whale_type,whale_msg = detect_whale_manipulation(df5m)
    wm_type,wm_msg = detect_w_m_pattern(df5m)
    whale15,whale15_msg = detect_whale_manipulation(df15m)
    wm15,wm15_msg = detect_w_m_pattern(df15m)

    if has_long and entry_price>0:
        change=(price-entry_price)/entry_price
        if change>=SCALP_TP1: return "TAKE PROFIT",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} +{change*100:.2f}% {whale_msg} {wm_msg}","score":9,"reasons":[f"TP {change*100:.2f}% {whale_msg}"],"price":price}
        if change<=-SCALP_SL: return "TAKE PROFIT",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} SL {change*100:.2f}%","score":9,"reasons":[f"SL {change*100:.2f}%"],"price":price}
        return "HOLD LONG",8,"🟢",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} {vol15m} {vol5m} {change*100:.2f}% {whale_msg} {wm_msg}","score":8,"reasons":[f"HOLD {change*100:.2f}% {whale_msg} {wm_msg}"],"price":price}
    if has_short and entry_price>0:
        change=(entry_price-price)/entry_price
        if change>=SCALP_TP1: return "TAKE PROFIT",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} +{change*100:.2f}% {whale_msg} {wm_msg}","score":9,"reasons":[f"TP {change*100:.2f}% {whale_msg}"],"price":price}
        if change<=-SCALP_SL: return "TAKE PROFIT",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} SL {change*100:.2f}%","score":9,"reasons":[f"SL {change*100:.2f}%"],"price":price}
        return "HOLD SHORT",8,"🔴",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{trend15m} {vol15m} {vol5m} {change*100:.2f}% {whale_msg} {wm_msg}","score":8,"reasons":[f"HOLD {change*100:.2f}% {whale_msg} {wm_msg}"],"price":price}

    c0=df5m['close'].iloc[-1]; c1=df5m['close'].iloc[-2]; c2=df5m['close'].iloc[-3]
    two_up=c0>c1 and c1>c2; two_down=c0<c1 and c1<c2
    score=0; reasons=[]
    if whale_type=="BULL_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}")
    if whale_type=="BEAR_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}")
    if wm_type=="W_PATTERN": score+=3; reasons.append(f"🔄 {wm_msg}")
    if wm_type=="M_PATTERN": score+=3; reasons.append(f"🔄 {wm_msg}")
    if whale15: score+=1; reasons.append(f"15M {whale15_msg}")
    if wm15: score+=1; reasons.append(f"15M {wm15_msg}")
    if ratio5m>=2.5: score+=2; reasons.append(f"🔥 {vol5m}")
    elif ratio5m>=1.5: score+=1; reasons.append(vol5m)
    elif ratio5m<=0.6: score-=2; reasons.append(f"{vol5m} LOW NO ENTRY")
    if ratio15m>=1.5: score+=1; reasons.append(f"15M {vol15m}")
    if trend1h=="UP": score+=2
    if trend1h=="DOWN": score+=2
    if trend4h!="RANGE": score+=1

    if (whale_type=="BULL_LIQ_GRAB" or wm_type=="W_PATTERN" or two_up) and mom5m>0.5 and ratio5m>=1.2 and 30<rsi5m<70 and trend1h!="DOWN":
        if two_up: reasons.append(f"5M UP {mom5m:.1f}% x2")
        decision="BUY NOW"; emoji="🟢"; score+=3
    elif (whale_type=="BEAR_LIQ_GRAB" or wm_type=="M_PATTERN" or two_down) and mom5m<-0.5 and ratio5m>=1.2 and 30<rsi5m<70 and trend1h!="UP":
        if two_down: reasons.append(f"5M DOWN {mom5m:.1f}% x2")
        decision="SELL NOW"; emoji="🔴"; score+=3
    else:
        decision="AVOID BUY" if mom5m>=0 else "AVOID SELL"; emoji="⚪"; reasons.append(f"WAIT 5M {mom5m:.1f}% {vol5m} RSI{int(rsi5m)}")

    if "NOW" in decision:
        reasons.append(f"4H:{trend4h} 1H:{trend1h} 15M:{trend15m}")
        if score<6: decision=f"AVOID {decision.split()[0]}"; emoji="⚪"
        if ratio15m<0.5: decision=f"AVOID {decision.split()[0]}"; emoji="⚪"

    if score>10: score=10
    if score<0: score=0
    info={"4H":f"{trend4h} mom{mom4h:.1f}% RSI{int(rsi4h)}","1H":f"{trend1h} mom{mom1h:.1f}% RSI{int(rsi1h)}","15M":f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m} | 5M {vol5m} RSI{int(rsi5m)}","score":score,"reasons":reasons,"price":price}
    return decision,score,emoji,info

# === FIXED AUTOPILOT - SILENT + FAST COIN QTY FIX ===
def safe_autopilot_enter(ex,sym,price,sess,score,info,decision,notional):
    global TRADED_THIS_RUN
    if not AUTOPILOT_ENABLED: return False
    if sess=="DEAD ZONE": return False
    if "NOW" not in decision and "TAKE PROFIT" not in decision: return False
    if "NOW" in decision and score<6: return False
    try:
        has=False
        for p in ex.fetch_positions([sym]):
            c,_,_,_,_=parse_position(p)
            if abs(c)>0: has=True; break
        if "TAKE PROFIT" in decision and has:
            close_position(ex,sym)
            # Silent TP - no telegram, only log
            print(f"💰 AUTO TP {sym}"); return True
        if has or TRADED_THIS_RUN: return False
        # FIX FOR FAST LOW PRICE COINS SIREN/LAB/KOMA
        qty = notional / price
        # Round to exchange precision - keep float for 0.000xx coins
        qty = max(1, min(qty, MAX_QTY_CAP))
        try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
        except: pass
        side="buy" if "BUY" in decision else "sell"
        ex.create_market_order(sym,side,qty)
        TRADED_THIS_RUN=True
        print(f"🤖 AUTO {sym} {decision} qty {qty} @ {price}") # SILENT - NO TELEGRAM
        return True
    except Exception as e: print(f"Auto err {sym} {e}"); return False

def check_monthly_report(free):
    now = datetime.now(timezone.utc)
    if now.day == 1 and now.hour == 7 and now.minute < 10:
        pnl = float(free) - BALANCE_START
        send_telegram(f"📊 *MONTHLY AUTO INVESTMENT REPORT*\n💰 Balance: ${float(free):.2f} (Start ${BALANCE_START})\n📈 PnL: ${pnl:.2f}\n🎯 {float(free)/TARGET*100:.2f}% to $10k\n🤖 SIREN LAB KOMA Silent Compounding")

def scan():
    global TRADED_THIS_RUN,ALL_SIGNALS
    TRADED_THIS_RUN=False; ALL_SIGNALS=[]
    ex=get_exchange()
    if not ex: send_telegram("❌ MEXC KEY ERROR - Check Railway vars"); return
    session,_,h=get_killzone()
    # AUTOPILOT still runs even in DEAD? No, respect dead zone
    if session=="DEAD ZONE": print(f"💤 DEAD ZONE {h}UTC SILENT"); return
    try: bal=ex.fetch_balance(); free=bal['USDT']['free'] if 'USDT' in bal else BALANCE_START
    except: free=BALANCE_START
    notional=get_auto_notional(free)
    progress=(float(free)/TARGET)*100

    # === TIMER FIX: MANUAL ONLY ONCE PER HOUR ===
    current_min = datetime.now(timezone.utc).minute
    allow_manual = current_min < 10 # Only first 10 min of hour = 1 signal per hour

    # Monthly report check (auto silent)
    check_monthly_report(free)

    for sym in SYMBOLS:
        try:
            df4h=pd.DataFrame(ex.fetch_ohlcv(sym,'4h',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df1h=pd.DataFrame(ex.fetch_ohlcv(sym,'1h',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df15m=pd.DataFrame(ex.fetch_ohlcv(sym,'15m',limit=100),columns=['timestamp','open','high','low','close','volume'])
            df5m=pd.DataFrame(ex.fetch_ohlcv(sym,'5m',limit=100),columns=['timestamp','open','high','low','close','volume'])
            price=df5m['close'].iloc[-1]
            has_long=False; has_short=False; entry=0
            try:
                for p in ex.fetch_positions([sym]):
                    c,s,_,e,_=parse_position(p)
                    if abs(c)>0:
                        entry=e
                        if s=="long": has_long=True
                        else: has_short=True
            except: pass
            decision,score,emoji,info=check_scalp_engine(df4h,df1h,df15m,df5m,sym,has_long,has_short,entry)

            # === 1. AUTOPILOT ALWAYS EVERY 10 MIN (SILENT) ===
            safe_autopilot_enter(ex,sym,price,session,score,info,decision,notional)

            # === 2. MANUAL ONLY ONCE PER HOUR (CLEAN) ===
            if allow_manual:
                send_now=False
                if "NOW" in decision or "TAKE PROFIT" in decision: send_now=can_send(sym,decision,1)
                elif "HOLD" in decision: send_now=can_send(sym,decision,10)
                else: send_now=can_send(sym,decision,30)
                if send_now:
                    mg=""
                    if "BUY NOW" in decision: mg=f"\n 👉 MANUAL LONG @ {price:.5f} SL {(price*(1-SCALP_SL)):.5f} TP {(price*(1+SCALP_TP1)):.5f} | QTY {notional/price:.2f}"
                    if "SELL NOW" in decision: mg=f"\n 👉 MANUAL SHORT @ {price:.5f} SL {(price*(1+SCALP_SL)):.5f} TP {(price*(1-SCALP_TP1)):.5f} | QTY {notional/price:.2f}"
                    line=f"{emoji} *{decision}* {sym} @ {price:.5f} | SCORE {score}/10\n 4H: {info['4H']}\n 1H: {info['1H']}\n 15M: {info['15M']}\n → {','.join(info['reasons'])}{mg}"
                    ALL_SIGNALS.append(line)
            time.sleep(0.8)
        except Exception as e: print(f"Err {sym} {e}"); continue

    if ALL_SIGNALS and allow_manual:
        mode_txt="📱 MANUAL PEAK" if AUTOPILOT_ENABLED else "📱 MANUAL ONLY"
        header=f"⚡ *{get_killzone()[0]} {h}UTC - {mode_txt} - HOURLY CLEAN*\n💰 ${float(free):.2f} | Trade ${notional} | {progress:.2f}% to $10k | SIREN LAB KOMA\n{'-'*40}\n\n"
        body="\n\n".join(ALL_SIGNALS)
        footer="\n\n✅ MANUAL: 1 per hour | ASIAN 5UTC LONDON 7-9UTC NY 12-15UTC\n🤖 AUTO: Silent every 10min + Monthly Report 1st\n🐋 LIQ GRAB | 🔄 W/M | 🔥 WHALEVOL | TP1.5% SL0.8%"
        send_telegram(header+body+footer)
    print("✅ HOURLY CLEAN DONE")

if __name__=="__main__": scan()
