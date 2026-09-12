import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

BALANCE_START = 14.99
TARGET = 60000.0
LEVERAGE = 5
TRADED_THIS_RUN, ALL_SIGNALS = False, []
try: LAST_ALERT = json.load(open("cooldown.json"))
except: LAST_ALERT = {}

# --- KOMA FLIP BEAST ---
try:
    from koma_flip_beast import scalp_plan as koma_beast_plan
    KOMA_BEAST = True
except:
    KOMA_BEAST = False
    koma_beast_plan = None

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

SYMBOLS = ["SIREN/USDT:USDT","LAB/USDT:USDT","KOMA/USDT:USDT","GRASS/USDT:USDT"]
SCALP_TP1 = 0.035
SCALP_SL = 0.022

TRADES_FILE = "/tmp/koma_trades.log"
def _log(pnl):
    try:
        with open(TRADES_FILE,"a") as f: f.write(f"{datetime.utcnow().isoformat()},{pnl}\n")
    except: pass

def _monthly_report():
    try:
        if datetime.utcnow().day!= 1: return
        if not os.path.exists(TRADES_FILE): return
        lines = open(TRADES_FILE).readlines()[-200:]
        total = len(lines)
        profit = sum(float(l.split(",")[1]) for l in lines if "," in l)
        send_telegram(f"📊 *MONTHLY {datetime.utcnow().strftime('%B %Y')}*\nTrades: {total}\nPNL: {profit:.2f}%\nTarget: $60K")
    except: pass

def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, vol_now, vol_avg, btc_trend, signal_type, reasons=None):
    if reasons is None: reasons = []
    reasons_str = " ".join(reasons).upper()
    whale_override = any(x in reasons_str for x in [
        "LIQ_GRAB", "WHALE_TRAP", "KOMA_PUMP_OVERRIDE", "BREAKOUT_LONG", "BREAKOUT_SHORT",
        "STOP_HUNT", "ACCUM", "W_PATTERN", "M_PATTERN", "WHALEVOL", "DOUBLE BOTTOM", "DOUBLE TOP", "VOLUP"
    ])
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    range_24h_pct = high_24h - low_24h
    location_24h = ((price - low_24h) / range_24h_pct * 100) if range_24h_pct > 0 else 50

    if range_4h_pct < 0.015:
        if not whale_override:
            return True, f"JUNCTION BOX {range_4h_pct*100:.2f}% WAIT"
        else:
            if vol_now < vol_avg * 1.1:
                return True, f"JUNCTION weak vol {vol_now/vol_avg:.1f}x WAIT"
            return False, f"CONFIRMED BREAKOUT Vol {vol_now/vol_avg:.1f}x"

    if not whale_override:
        if signal_type == "LONG" and location_24h > 85: return True, f"At top {location_24h:.1f}% no LONG"
        if signal_type == "SHORT" and location_24h < 15: return True, f"At bottom {location_24h:.1f}% no SHORT"
        if signal_type == "LONG" and rsi_1h > 82: return True, f"RSI {rsi_1h:.1f} no LONG"
        if signal_type == "SHORT" and rsi_1h < 18: return True, f"RSI {rsi_1h:.1f} no SHORT"

    if not whale_override and vol_now < vol_avg * 0.7:
        return True, f"Low vol {vol_now/vol_avg:.1f}x WAIT"

    if not whale_override:
        if btc_trend == "BEARISH" and signal_type == "LONG": return True, f"BTC bear no LONG"
        if btc_trend == "BULLISH" and signal_type == "SHORT": return True, f"BTC bull no SHORT"

    return False, f"CONFIRMED {signal_type} loc {location_24h:.0f}% RSI {rsi_1h:.0f} Vol {vol_now/vol_avg:.1f}x"

def send_telegram(msg):
    try:
        if TELEGRAM_TOKEN and TELEGRAM_CHAT:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except: pass
    print(msg)

def get_exchange():
    if not MEXC_KEY or not MEXC_SECRET: print("❌ KEYS MISSING"); return None
    return ccxt.mexc({'apiKey': MEXC_KEY,'secret': MEXC_SECRET,'options': {'defaultType': 'swap'},'enableRateLimit': True})

def get_auto_notional(free_bal):
    try: bal=float(free_bal)
    except: bal=BALANCE_START
    notional = round(bal * 0.23, 2)
    if notional < 3.0: notional = 3.0
    if notional > bal * 0.9: notional = bal * 0.9
    return notional

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
    if 0<=h<7: return "ASIAN","Range",h
    if 7<=h<12: return "LONDON","Breakout",h
    if 12<=h<17: return "NEW YORK","Trend",h
    if 17<=h<21: return "LONDON CLOSE","Reversal",h
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
            if ratio>=3.0: label=f"WHALEVOLx{ratio:.1f}"
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

# --- MANUAL STRUCTURE: 4H DIR + 1H STRUCT + 5-15M ENTRY ---
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
        vol_pumping = ratio5m > 1.2 and mom5m > 0.3
        vol_dying = ratio5m < 0.8
        if change>=SCALP_TP1:
            _log(change*100)
            return "TAKE PROFIT CLOSE LONG",9,"💰",{"4H":f"{trend4h} DIR mom{mom4h:.1f}%","1H":f"{trend1h} STRUCT mom{mom1h:.1f}%","15M":f"{trend15m} ENTRY {vol15m} {vol5m} +{change*100:.2f}% TP HIT","score":9,"reasons":[f"TP {change*100:.2f}% CLOSE NOW {whale_msg}"],"price":price}
        if change<=-SCALP_SL:
            _log(change*100)
            return "CUT LOSS CLOSE LONG",9,"✂️",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} {change*100:.2f}% SL","score":9,"reasons":[f"SL {change*100:.2f}% CLOSE"],"price":price}
        if vol_pumping and change>0:
            return "HOLD LONG - PUMP CONTINUES",9,"🟢",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} {vol5m} {change*100:.2f}% PUMPING","score":9,"reasons":[f"HOLD PROFIT {change*100:.2f}% VOL UP {vol5m} STILL PUMPING 🚀 {whale_msg}"],"price":price}
        if vol_dying and change>0.005:
            return "CLOSE LONG - VOLUME DYING",7,"💰",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} VOL DYING {vol5m} {change*100:.2f}%","score":7,"reasons":[f"TAKE PROFIT VOL DYING {change*100:.2f}% {vol5m}"],"price":price}
        return "HOLD LONG",8,"🟢",{"4H":f"{trend4h} DIR mom{mom4h:.1f}%","1H":f"{trend1h} STRUCT mom{mom1h:.1f}%","15M":f"{trend15m} ENTRY {vol15m} {vol5m} {change*100:.2f}% {whale_msg}","score":8,"reasons":[f"HOLD {change*100:.2f}% {whale_msg} {wm_msg}"],"price":price}

    if has_short and entry_price>0:
        change=(entry_price-price)/entry_price
        vol_dumping = ratio5m > 1.2 and mom5m < -0.3
        vol_dying = ratio5m < 0.8
        if change>=SCALP_TP1:
            _log(change*100)
            return "TAKE PROFIT CLOSE SHORT",9,"💰",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} +{change*100:.2f}% TP HIT","score":9,"reasons":[f"TP {change*100:.2f}% CLOSE NOW {whale_msg}"],"price":price}
        if change<=-SCALP_SL:
            _log(change*100)
            return "CUT LOSS CLOSE SHORT",9,"✂️",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} {change*100:.2f}% SL","score":9,"reasons":[f"SL {change*100:.2f}% CLOSE"],"price":price}
        if vol_dumping and change>0:
            return "HOLD SHORT - DUMP CONTINUES",9,"🔴",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} {vol5m} {change*100:.2f}% DUMPING","score":9,"reasons":[f"HOLD PROFIT {change*100:.2f}% VOL UP {vol5m} STILL DUMPING 📉 {whale_msg}"],"price":price}
        if vol_dying and change>0.005:
            return "CLOSE SHORT - VOLUME DYING",7,"💰",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} VOL DYING {vol5m} {change*100:.2f}%","score":7,"reasons":[f"TAKE PROFIT VOL DYING {change*100:.2f}% {vol5m}"],"price":price}
        return "HOLD SHORT",8,"🔴",{"4H":f"{trend4h} DIR","1H":f"{trend1h} STRUCT","15M":f"{trend15m} ENTRY {vol15m} {vol5m} {change*100:.2f}% {whale_msg}","score":8,"reasons":[f"HOLD {change*100:.2f}% {whale_msg} {wm_msg}"],"price":price}

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
    elif ratio5m<=0.6: score-=2
    if ratio15m>=1.5: score+=1; reasons.append(f"15M {vol15m}")

    is_whale = whale_type is not None or wm_type is not None or ratio5m>=2.5
    is_bull_structure = trend1h=="UP" or mom1h>0.5
    is_bear_structure = trend1h=="DOWN" or mom1h<-0.5
    is_bull_direction = trend4h=="UP" or mom4h>0.3
    is_bear_direction = trend4h=="DOWN" or mom4h<-0.3

    if (whale_type=="BULL_LIQ_GRAB" or wm_type=="W_PATTERN" or two_up) and mom5m>0.3 and ratio5m>=1.1 and 20<rsi5m<80:
        if not is_whale and not (is_bull_direction and is_bull_structure):
            decision="WAIT"; emoji="⚪"; reasons=[f"WAIT - 4H {trend4h} 1H {trend1h} not aligned LONG"]
        else:
            decision="BUY NOW"; emoji="🟢"; score+=3
            if two_up: reasons.append(f"5M ENTRY UP {mom5m:.1f}% x2")
            reasons.append(f"4H DIR {trend4h} + 1H STRUCT {trend1h} + 5-15M ENTRY")
    elif (whale_type=="BEAR_LIQ_GRAB" or wm_type=="M_PATTERN" or two_down) and mom5m<-0.2 and ratio5m>=1.1 and 20<rsi5m<80:
        if not is_whale and not (is_bear_direction and is_bear_structure):
            decision="WAIT"; emoji="⚪"; reasons=[f"WAIT - 4H {trend4h} 1H {trend1h} not aligned SHORT"]
        else:
            decision="SELL NOW"; emoji="🔴"; score+=3
            if two_down: reasons.append(f"5M ENTRY DOWN {mom5m:.1f}% x2")
            reasons.append(f"4H DIR {trend4h} + 1H STRUCT {trend1h} + 5-15M ENTRY")
    else:
        decision="WAIT"; emoji="⚪"; score=0
        reasons=[f"WAIT 5-15M ENTRY {mom5m:.1f}% {vol5m} | 1H STRUCT {trend1h} {mom1h:.1f}% | 4H DIR {trend4h} {mom4h:.1f}% RSI{int(rsi5m)}"]

    if "NOW" in decision:
        if score<4: decision="WAIT"; emoji="⚪"; score=0
        if ratio15m<0.5 and not is_whale: decision="WAIT"; emoji="⚪"; score=0

    if score>10: score=10
    if score<0: score=0
    info={"4H":f"{trend4h} DIR mom{mom4h:.1f}% RSI{int(rsi4h)}","1H":f"{trend1h} STRUCT mom{mom1h:.1f}% RSI{int(rsi1h)}","15M":f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m} | 5M ENTRY {vol5m} RSI{int(rsi5m)}","score":score,"reasons":reasons,"price":price}
    return decision,score,emoji,info

def safe_autopilot_enter(ex,sym,price,sess,score,info,decision,notional):
    global TRADED_THIS_RUN
    if not AUTOPILOT_ENABLED: return False
    if "WAIT" in decision: return False
    if "NOW" in decision and score<4: return False
    try:
        existing_side = None
        for p in ex.fetch_positions([sym]):
            c,s,_,_,_=parse_position(p)
            if abs(c)>0: existing_side = s; break
        try:
            bal=ex.fetch_balance()
            free_bal=bal['USDT']['free'] if 'USDT' in bal else notional
        except: free_bal=notional
        if existing_side:
            if ("BUY" in decision and existing_side=="long") or ("SELL" in decision and existing_side=="short"): return False
            if ("BUY" in decision and existing_side=="short") or ("SELL" in decision and existing_side=="long"):
                close_position(ex,sym); time.sleep(1.5)
                try:
                    bal2=ex.fetch_balance(); free2=bal2['USDT']['free'] if 'USDT' in bal2 else free_bal
                    new_notional=get_auto_notional(free2)
                except: free2=free_bal; new_notional=notional
                qty = new_notional / price
                try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
                except: pass
                side="buy" if "BUY" in decision else "sell"
                ex.create_market_order(sym,side,qty); TRADED_THIS_RUN=True
                send_telegram(f"🔄 *FLIPPED {sym}* {existing_side.upper()} -> {decision}\n💰 ${free2:.2f} Size ${new_notional}\n📍 {price:.5f}")
                return True
            if "CLOSE" in decision or "TAKE PROFIT" in decision: close_position(ex,sym); return True
        if not existing_side and "NOW" in decision and score>=4:
            qty = notional / price
            try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
            except: pass
            side="buy" if "BUY" in decision else "sell"
            ex.create_market_order(sym,side,qty)
            send_telegram(f"🤖 *AUTO {sym}* {decision} @ {price:.5f}\nSize ${notional:.2f} TP {SCALP_TP1*100}% SL {SCALP_SL*100}%\n{','.join(info['reasons'])}")
            return True
    except Exception as e: print(f"Auto err {sym} {e}")
    return False

def scan():
    global TRADED_THIS_RUN,ALL_SIGNALS
    TRADED_THIS_RUN=False; ALL_SIGNALS=[]
    ex=get_exchange()
    if not ex: return
    session,_,h=get_killzone()
    _monthly_report()

    try: bal=ex.fetch_balance(); free=bal['USDT']['free'] if 'USDT' in bal else BALANCE_START
    except: free=BALANCE_START
    notional=get_auto_notional(free)

    # --- AUTO KOMA 5MIN ALWAYS (24/7) ---
    if KOMA_BEAST and koma_beast_plan:
        try:
            res = koma_beast_plan(ex, free, send_telegram, lambda *a: True)
            print(f"KOMA BEAST AUTO: {res}")
        except Exception as e: print(f"KOMA beast err {e}")

    # --- MANUAL 15MIN PEAK HOURS ONLY + 0/15/30/45 ---
    minute = datetime.now(timezone.utc).minute
    if minute not in [0,15,30,45]:
        print(f"⏭️ Manual skip minute {minute} not 0/15/30/45")
        return

    if session=="DEAD ZONE":
        print(f"💤 DEAD ZONE {h}UTC - Manual skip, KOMA auto already done")
        return

    try:
        btc_df=pd.DataFrame(ex.fetch_ohlcv("BTC/USDT:USDT",'1h',limit=50),columns=['t','o','h','l','c','v'])
        btc_ema9=btc_df['c'].ewm(span=9).mean().iloc[-1]
        btc_ema21=btc_df['c'].ewm(span=21).mean().iloc[-1]
        btc_trend="BULLISH" if btc_ema9>btc_ema21 else "BEARISH"
    except: btc_trend="RANGE"

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
                    if abs(c)>0: entry=e; has_long=(s=="long"); has_short=(s=="short")
            except: pass
            decision,score,emoji,info=check_scalp_engine(df4h,df1h,df15m,df5m,sym,has_long,has_short,entry)
            if "WAIT" in decision: continue
            low_24h=df1h['low'].tail(24).min(); high_24h=df1h['high'].tail(24).max()
            low_4h=df4h['low'].tail(6).min(); high_4h=df4h['high'].tail(6).max()
            _,rsi1h,_,_=get_mom_rsi_vol(df1h)
            vol_avg=df15m['volume'].tail(20).mean(); vol_now=df15m['volume'].iloc[-1]
            sig_type="LONG" if "BUY" in decision else "SHORT" if "SELL" in decision else "NONE"
            if sig_type!="NONE" and "HOLD" not in decision and "CLOSE" not in decision:
                blocked, filter_msg = check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi1h, vol_now, vol_avg, btc_trend, sig_type, info['reasons'])
                if blocked: continue
                else: info['reasons'].append(filter_msg)
            safe_autopilot_enter(ex,sym,price,session,score,info,decision,notional)
            # 60 MIN COOLDOWN
            if can_send(sym,decision,60):
                mg=""
                if "BUY NOW" in decision: mg=f"\n 👉 LONG @ {price:.5f} SL {(price*(1-SCALP_SL)):.5f} TP {(price*(1+SCALP_TP1)):.5f}"
                if "SELL NOW" in decision: mg=f"\n 👉 SHORT @ {price:.5f} SL {(price*(1+SCALP_SL)):.5f} TP {(price*(1+SCALP_TP1)):.5f}"
                if "HOLD" in decision: mg=f"\n 📈 STILL PUMPING VOL UP"
                if "CLOSE" in decision: mg=f"\n 💰 CLOSING PROFIT"
                msg=f"{emoji} *{sym} {decision}* {info['score']}/10\n{info['4H']}\n{info['1H']}\n{info['15M']}\n{', '.join(info['reasons'])}{mg}\n⏰ {session} {h}UTC"
                send_telegram(msg)
                ALL_SIGNALS.append(msg)
        except Exception as e: print(f"Err {sym} {e}")

if __name__=="__main__":
    scan()
