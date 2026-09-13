import os, ccxt, pandas as pd, requests, time, json
from datetime import datetime, timezone

BALANCE_START = 14.99
TARGET = 60000.0
LEVERAGE = 10
TRADED_THIS_RUN, ALL_SIGNALS = False, []
try: LAST_ALERT = json.load(open("cooldown.json"))
except: LAST_ALERT = {}

try:
    from koma_flip_beast import scalp_plan as koma_beast_plan
    KOMA_BEAST = True
except:
    KOMA_BEAST = False
    koma_beast_plan = None

KOMA_PUMP_TRIGGER = 1.5
KOMA_DUMP_TRIGGER = -1.5
KOMA_SLEEP_TP = 3.0
KOMA_SLEEP_SL = 2.5

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
ENGINE = os.getenv("ENGINE","BOTH").upper()

SYMBOLS = ["KOMA/USDT:USDT"]
# KOMA KEPT FOR MANUAL SIGNAL ONLY - BEAST OWNS TRADING
MANUAL_WATCHLIST = ["GRASS/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT","SIREN/USDT:USDT","KOMA/USDT:USDT","VELVET/USDT:USDT"]

SCALP_TP1 = 0.05
SCALP_SL = 0.04
TRADES_FILE = "/tmp/koma_trades.log"

def _log(pnl):
    try:
        with open(TRADES_FILE,"a") as f: f.write(f"{datetime.utcnow().isoformat()},{pnl}\n")
    except: pass

def _monthly_report():
    try:
        if not os.path.exists(TRADES_FILE): return
        if datetime.utcnow().day!= 1: return
        lines = open(TRADES_FILE).readlines()[-200:]
        total = len(lines)
        profit = sum(float(l.split(",")[1]) for l in lines if "," in l)
        send_telegram(f"📊 *MONTHLY {datetime.utcnow().strftime('%B %Y')}*\nEngine: {ENGINE}\nTrades: {total}\nPNL: {profit:.2f}%\nTarget: $60K")
    except: pass

def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, vol_now, vol_avg, btc_trend, signal_type, reasons=None):
    if reasons is None: reasons = []
    reasons_str = " ".join(reasons).upper()
    whale_override = any(x in reasons_str for x in ["LIQ_GRAB","WHALE_TRAP","KOMA_PUMP_OVERRIDE","BREAKOUT","STOP_HUNT","ACCUM","W_PATTERN","M_PATTERN","WHALEVOL","DOUBLE","BOS"])
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    range_24h_pct = high_24h - low_24h
    location_24h = ((price - low_24h) / range_24h_pct * 100) if range_24h_pct > 0 else 50
    if range_4h_pct < 0.015:
        if not whale_override: return True, f"JUNCTION BOX {range_4h_pct*100:.2f}% WAIT"
        else:
            if vol_now < vol_avg * 0.3: return True, f"JUNCTION weak vol {vol_now/vol_avg:.1f}x WAIT"
            return False, f"CONFIRMED BREAKOUT Vol {vol_now/vol_avg:.1f}x"
    if not whale_override:
        if signal_type == "LONG" and location_24h > 85: return True, f"At top {location_24h:.1f}% no LONG"
        if signal_type == "SHORT" and location_24h < 15: return True, f"At bottom {location_24h:.1f}% no SHORT"
        if signal_type == "LONG" and rsi_1h > 82: return True, f"RSI {rsi_1h:.1f} no LONG"
        if signal_type == "SHORT" and rsi_1h < 18: return True, f"RSI {rsi_1h:.1f} no SHORT"
    if not whale_override and vol_now < vol_avg * 0.5: return True, f"Low vol {vol_now/vol_avg:.1f}x WAIT"
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
    notional = round(bal * 0.5, 2)
    if notional < 3.0: notional = 3.0
    if notional > bal * 0.9: notional = round(bal * 0.9,2)
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

def get_session_cooldown(session, decision):
    if "TAKE PROFIT" in decision or "CLOSE NOW" in decision or "REVERSAL" in decision: return 15
    if "HOLD" in decision: return 60
    if "JUNCTION" in decision: return 30
    return 20

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

def detect_bos_1h(df1h):
    try:
        high_20 = df1h['high'].iloc[-21:-1].max()
        low_20 = df1h['low'].iloc[-21:-1].min()
        close = df1h['close'].iloc[-1]
        prev_close = df1h['close'].iloc[-2]
        if close > high_20 and prev_close <= high_20: return "BOS_UP", f"1H BOS UP break {high_20:.5f}"
        if close < low_20 and prev_close >= low_20: return "BOS_DOWN", f"1H BOS DOWN break {low_20:.5f}"
        return None, ""
    except: return None, ""

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
    bos_type,bos_msg = detect_bos_1h(df1h)
    is_koma = "KOMA" in sym

    # FIXED: 30m change like beast, not 5m vs 1h
    try: change_30m = (df5m['close'].iloc[-1] - df5m['close'].iloc[-6]) / df5m['close'].iloc[-6] * 100
    except: change_30m = 0

    if is_koma and not has_long and not has_short:
        if change_30m >= KOMA_PUMP_TRIGGER:
            return "SELL NOW",10,"🔴",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"KOMA_PUMP_OVERRIDE {change_30m:.2f}%","score":10,"reasons":[f"KOMA_PUMP_OVERRIDE {change_30m:.2f}% SELL"],"price":price}
        if change_30m <= KOMA_DUMP_TRIGGER:
            return "BUY NOW",10,"🟢",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"KOMA_DUMP_OVERRIDE {change_30m:.2f}%","score":10,"reasons":[f"KOMA_PUMP_OVERRIDE {change_30m:.2f}% BUY"],"price":price}

    if has_long and entry_price>0:
        change=(price-entry_price)/entry_price
        tp = (KOMA_SLEEP_TP/100) if is_koma else SCALP_TP1
        sl = (KOMA_SLEEP_SL/100) if is_koma else SCALP_SL
        if change>=tp: _log(change*100); return "TAKE PROFIT CLOSE LONG",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"TP {change*100:.2f}%","score":9,"reasons":[f"TP {change*100:.2f}%"],"price":price}
        if change<=-sl: _log(change*100); return "CUT LOSS CLOSE LONG",9,"✂️",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"SL {change*100:.2f}%","score":9,"reasons":[f"SL {change*100:.2f}%"],"price":price}
        if rsi5m>75 or (trend15m=="DOWN" and mom5m<-0.5):
            return "CLOSE NOW - REVERSAL LONG",8,"⚠️",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{vol5m} {change*100:.2f}% REVERSAL","score":8,"reasons":[f"REVERSAL {change*100:.2f}% RSI{int(rsi5m)}"],"price":price}
        return "HOLD LONG PROFIT",8,"🟢",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{vol5m} {change*100:.2f}%","score":8,"reasons":[f"HOLD {change*100:.2f}%"],"price":price}

    if has_short and entry_price>0:
        change=(entry_price-price)/entry_price
        tp = (KOMA_SLEEP_TP/100) if is_koma else SCALP_TP1
        sl = (KOMA_SLEEP_SL/100) if is_koma else SCALP_SL
        if change>=tp: _log(change*100); return "TAKE PROFIT CLOSE SHORT",9,"💰",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"TP {change*100:.2f}%","score":9,"reasons":[f"TP {change*100:.2f}%"],"price":price}
        if change<=-sl: _log(change*100); return "CUT LOSS CLOSE SHORT",9,"✂️",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"SL {change*100:.2f}%","score":9,"reasons":[f"SL {change*100:.2f}%"],"price":price}
        if rsi5m<25 or (trend15m=="UP" and mom5m>0.5):
            return "CLOSE NOW - REVERSAL SHORT",8,"⚠️",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{vol5m} {change*100:.2f}% REVERSAL","score":8,"reasons":[f"REVERSAL {change*100:.2f}% RSI{int(rsi5m)}"],"price":price}
        return "HOLD SHORT PROFIT",8,"🔴",{"4H":f"{trend4h}","1H":f"{trend1h}","15M":f"{vol5m} {change*100:.2f}%","score":8,"reasons":[f"HOLD {change*100:.2f}%"],"price":price}

    c0=df5m['close'].iloc[-1]; c1=df5m['close'].iloc[-2]; c2=df5m['close'].iloc[-3]
    two_up=c0>c1 and c1>c2; two_down=c0<c1 and c1<c2
    score=0; reasons=[]
    if whale_type=="BULL_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}")
    if whale_type=="BEAR_LIQ_GRAB": score+=3; reasons.append(f"🐋 {whale_msg}")
    if wm_type=="W_PATTERN": score+=3; reasons.append(f"🔄 {wm_msg}")
    if wm_type=="M_PATTERN": score+=3; reasons.append(f"🔄 {wm_msg}")
    if bos_type=="BOS_UP": score+=3; reasons.append(f"📈 {bos_msg}")
    if bos_type=="BOS_DOWN": score+=3; reasons.append(f"📉 {bos_msg}")
    if ratio5m>=1.0: score+=2; reasons.append(f"🔥 {vol5m}")
    elif ratio5m>=0.8: score+=1; reasons.append(vol5m)
    if ratio15m>=1.0: score+=1; reasons.append(f"15M {vol15m}")

    dir_ok_long = trend4h in ["UP","RANGE"]
    dir_ok_short = trend4h in ["DOWN","RANGE"]

    if (whale_type=="BULL_LIQ_GRAB" or wm_type=="W_PATTERN" or two_up or bos_type=="BOS_UP") and mom5m>0.2 and ratio5m>=0.8 and 20<rsi5m<80 and dir_ok_long:
        if trend1h=="UP" or bos_type=="BOS_UP":
            decision="BUY NOW"; emoji="🟢"; score+=3; reasons.append(f"4H DIR {trend4h} + 1H BOS {trend1h} + 5-15M ENTRY OK")
        else:
            decision="JUNCTION WAIT"; emoji="🔀"; score=3; reasons.append(f"4H {trend4h} but 1H {trend1h} no BOS - JUNCTION")
            info={"4H":f"{trend4h} DIR mom{mom4h:.1f}% RSI{int(rsi4h)}","1H":f"{trend1h} STRUCT mom{mom1h:.1f}% RSI{int(rsi1h)} BOS:{bos_msg}","15M":f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m} | 5M ENTRY {vol5m} RSI{int(rsi5m)}","score":score,"reasons":reasons,"price":price}
            return decision,score,emoji,info
    elif (whale_type=="BEAR_LIQ_GRAB" or wm_type=="M_PATTERN" or two_down or bos_type=="BOS_DOWN") and mom5m<-0.2 and ratio5m>=0.8 and 20<rsi5m<80 and dir_ok_short:
        if trend1h=="DOWN" or bos_type=="BOS_DOWN":
            decision="SELL NOW"; emoji="🔴"; score+=3; reasons.append(f"4H DIR {trend4h} + 1H BOS {trend1h} + 5-15M ENTRY OK")
        else:
            decision="JUNCTION WAIT"; emoji="🔀"; score=3; reasons.append(f"4H {trend4h} but 1H {trend1h} no BOS - JUNCTION")
            info={"4H":f"{trend4h} DIR mom{mom4h:.1f}% RSI{int(rsi4h)}","1H":f"{trend1h} STRUCT mom{mom1h:.1f}% RSI{int(rsi1h)} BOS:{bos_msg}","15M":f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m} | 5M ENTRY {vol5m} RSI{int(rsi5m)}","score":score,"reasons":reasons,"price":price}
            return decision,score,emoji,info
    else:
        decision="WAIT"; emoji="⚪"; score=0; reasons=[f"WAIT ENTRY 5-15M mom {mom5m:.1f}% {vol5m} 1H BOS {bos_type}"]

    if score>10: score=10
    info={"4H":f"{trend4h} DIR mom{mom4h:.1f}% RSI{int(rsi4h)}","1H":f"{trend1h} BOS {bos_msg} mom{mom1h:.1f}% RSI{int(rsi1h)}","15M":f"{trend15m} mom{mom15m:.1f}% RSI{int(rsi15m)} {vol15m} | 5M ENTRY {vol5m} RSI{int(rsi5m)}","score":score,"reasons":reasons,"price":price}
    return decision,score,emoji,info

def safe_autopilot_enter(ex,sym,price,sess,score,info,decision,notional):
    global TRADED_THIS_RUN
    # === FIX: KOMA MANUAL NEVER TRADES - BEAST OWNS KOMA ===
    if "KOMA" in sym:
        return False

    if not AUTOPILOT_ENABLED: return False
    if "WAIT" in decision or "JUNCTION" in decision or "HOLD" in decision: return False
    if "NOW" in decision and score<3: return False
    try:
        existing_side = None
        for p in ex.fetch_positions([sym]):
            c,s,_,_,_=parse_position(p)
            if abs(c)>0: existing_side = s; break
        try: bal=ex.fetch_balance(); free_bal=bal['USDT']['free'] if 'USDT' in bal else notional
        except: free_bal=notional
        if existing_side:
            if ("BUY" in decision and existing_side=="long") or ("SELL" in decision and existing_side=="short"): return False
            if ("BUY" in decision and existing_side=="short") or ("SELL" in decision and existing_side=="long"):
                close_position(ex,sym); time.sleep(1.5)
                try: bal2=ex.fetch_balance(); free2=bal2['USDT']['free'] if 'USDT' in bal2 else free_bal; new_notional=get_auto_notional(free2)
                except: free2=free_bal; new_notional=notional
                qty = new_notional * LEVERAGE / price
                try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
                except: pass
                side="buy" if "BUY" in decision else "sell"
                ex.create_market_order(sym,side,qty); TRADED_THIS_RUN=True
                send_telegram(f"🔄 *FLIPPED {sym}* {existing_side.upper()} -> {decision}\n💰 ${free2:.2f} Size ${new_notional}\n📍 {price:.5f}")
                return True
            if "CLOSE" in decision or "TAKE PROFIT" in decision: close_position(ex,sym); return True
        if not existing_side and "NOW" in decision and score>=3:
            qty = notional * LEVERAGE / price
            try: ex.set_leverage(LEVERAGE,sym); ex.set_margin_mode('isolated',sym)
            except: pass
            side="buy" if "BUY" in decision else "sell"
            ex.create_market_order(sym,side,qty)
            send_telegram(f"🤖 *AUTO {sym}* {decision} @ {price:.5f}\nSize ${notional:.2f} TP {KOMA_SLEEP_TP}% SL {KOMA_SLEEP_SL}%\n{','.join(info['reasons'])}")
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
    print(f"ENGINE={ENGINE} AUTOPILOT={AUTOPILOT_ENABLED} Balance=${free:.2f} / ${TARGET} Progress {(free/TARGET*100):.4f}%")

    if ENGINE in ["AUTO","BOTH","CONCURRENT",""]:
        if KOMA_BEAST and koma_beast_plan:
            try:
                res = koma_beast_plan(ex, free, send_telegram, lambda *a: True)
                print(f"KOMA BEAST AUTO TRADE: {res}")
            except Exception as e: print(f"KOMA beast err {e}")

    if ENGINE in ["MANUAL","BOTH","CONCURRENT",""]:
        try:
            btc_df=pd.DataFrame(ex.fetch_ohlcv("BTC/USDT:USDT",'1h',limit=50),columns=['t','o','h','l','c','v'])
            btc_ema9=btc_df['c'].ewm(span=9).mean().iloc[-1]
            btc_ema21=btc_df['c'].ewm(span=21).mean().iloc[-1]
            btc_trend="BULLISH" if btc_ema9>btc_ema21 else "BEARISH"
        except: btc_trend="RANGE"
        for sym in MANUAL_WATCHLIST:
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
                if "WAIT" in decision and score==0:
                    print(f"MANUAL WAIT {sym} {info['15M']}"); continue
                low_24h=df1h['low'].tail(24).min(); high_24h=df1h['high'].tail(24).max()
                low_4h=df4h['low'].tail(6).min(); high_4h=df4h['high'].tail(6).max()
                _,rsi1h,_,_=get_mom_rsi_vol(df1h)
                try: vol_now=df5m['volume'].iloc[-1]; vol_avg=df5m['volume'].rolling(20).mean().iloc[-1]
                except: vol_now=1; vol_avg=1
                filtered, reason = check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi1h, vol_now, vol_avg, btc_trend, "LONG" if "BUY" in decision or "HOLD LONG" in decision else "SHORT", info['reasons'])
                if "KOMA_PUMP_OVERRIDE" in str(info['reasons']): filtered=False; reason=f"KOMA {KOMA_PUMP_TRIGGER}% OVERRIDE SIGNAL"
                if filtered and not any(x in decision for x in ["TAKE PROFIT","HOLD","CLOSE NOW","JUNCTION"]):
                    print(f"Filter {sym} {reason}"); continue
                if "HOLD" in decision:
                    msg = f"{emoji} *{decision} {sym}* {score}/10\n💰 PnL Holding - Trend still OK\n4H {info['4H']}\n1H {info['1H']} BOS\n15M {info['15M']}\nPrice {price}\nAction: HOLD PROFIT\nSession {session}"
                elif "TAKE PROFIT" in decision:
                    msg = f"{emoji} *{decision} {sym}* {score}/10\n💰 TP HIT - LOCK PROFIT NOW\n4H {info['4H']}\n1H {info['1H']}\n15M {info['15M']}\nPrice {price}\nAction: TAKE PROFIT\n{reason}"
                elif "CLOSE NOW" in decision:
                    msg = f"{emoji} *{decision} {sym}* {score}/10\n⚠️ REVERSAL WARNING - MARKET REVERSING\n4H {info['4H']}\n1H {info['1H']}\n15M {info['15M']}\nPrice {price}\nAction: CLOSE TRADE\n{reason}"
                elif "JUNCTION" in decision:
                    msg = f"{emoji} *{decision} {sym}* {score}/10\n🔀 JUNCTION - AT KEY LEVEL\n4H {info['4H']}\n1H {info['1H']}\n15M {info['15M']}\nPrice {price}\nAction: WAIT - Dont enter, at junction\n{reason}"
                else:
                    msg = f"{emoji} *MANUAL SIGNAL {sym}* {decision} Score {score}/10\n4H {info['4H']}\n1H {info['1H']} BOS\n15M {info['15M']} ENTRY 5-15M\nPrice {price}\n{reason}\nSession {session} {h}UTC\n(SIGNAL ONLY - NO MONEY USED)"

                cooldown_key = f"{decision}_{sym}_{session}"
                cd_mins = get_session_cooldown(session, decision)
                if can_send(sym, cooldown_key, cd_mins):
                    send_telegram(msg)
                    ALL_SIGNALS.append(msg)
            except Exception as e:
                print(f"Err {sym} {e}")

if __name__ == "__main__":
    scan()
