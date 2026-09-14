import ccxt
import os, json, time
from datetime import datetime, timezone

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=11
SIZE_PCT=0.5
SL_PCT=8.0
MAX_HOLD_HOURS=6
MAX_HOLD_LOSS=8.0
PUMP_PAUSE=0.08
MIN_NOTIONAL=7
COMPOUND=True

RSI_PERIOD=7
ANTI_FLIP_MIN=3
VOL_BOSS_LONDON=0.6
VOL_BOSS_ASIA=0.5
BUFFER=0.003
MIN_LONG=1.2
FULL_HOUSE=2.8

STATE_FILE=f"koma_retest_state_{os.getenv('ENGINE','AUTO').lower()}.json"

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE).read())
    except: pass
    return {"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": 0, "house_sent": 0, "last_flip": 0, "last_side": ""}

def save_state(s):
    try: open(STATE_FILE,'w').write(json.dumps(s))
    except: pass

def get_rsi(closes, period=7):
    if len(closes) < period+1: return 50
    gains=0; losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>0: gains+=diff
        else: losses+=abs(diff)
    if losses==0: return 75 if gains>0 else 50
    rs=gains/losses
    return 100 - (100/(1+rs))

def scalp_plan(ex, free_bal, send_telegram, can_send):
    def _safe_send(msg):
        try:
            # FIX SPAM - daily only via can_send 24h, others 5 min
            if "NEW DAILY" in msg:
                if not can_send("KOMA", f"HOUSE_{msg[:40]}", 1440): return
            else:
                if not any(x in msg for x in ["💰","🐋","🔥","🛑","🎯","🕛","⚡","🔄"]): return
                if not can_send("KOMA", msg[:30], 5): return
            send_telegram(msg)
        except:
            try: send_telegram(msg)
            except: pass

    try:
        c1=ex.fetch_ohlcv(SYMBOL,'1m',limit=30)
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=60)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl1=[x[4] for x in c1]
        cl5=[x[4] for x in c5]
        if len(cD)<2: return "WAIT daily"
        price=cl1[-1]

        rsi = get_rsi(cl5, RSI_PERIOD)
        rsi_fast = get_rsi(cl1, 7)
        ema_fast = sum(cl5[-12:])/12
        ema_slow = sum(cl5[-26:])/26
        trend_up = ema_fast > ema_slow
        trend_down = ema_fast < ema_slow

        h_utc = datetime.now(timezone.utc).hour
        m_utc = datetime.now(timezone.utc).minute
        if h_utc in [0,8,16] and m_utc < 5: return f"HOLD FUNDING {h_utc}:00"
        session = "LONDON" if 8 <= h_utc < 13 else "NEW_YORK" if 13 <= h_utc < 21 else "ASIA"
        vol_need = VOL_BOSS_LONDON if session in ["LONDON","NEW_YORK"] else VOL_BOSS_ASIA

        pump = abs(cl1[-1]-cl1[-2])/cl1[-2] if len(cl1)>2 else 0
        va=sum([float(x[5] or 0) for x in c5[-21:-1]])/20 if len(c5)>21 else float(c5[-1][5] or 1)
        if va < 1: va = 1
        vr=float(c5[-1][5] or 0)/(va+0.001)
        vr = max(0.1, min(vr, 4.0))

        if pump > PUMP_PAUSE and vr < 0.8 and pump < 0.04:
            return f"⏸️ FAKE PUMP PAUSE {pump*100:.2f}% VOL {vr:.1f}x"

        today_high=max(cD[-1][2], cD[-1][1], cD[-1][4])
        today_low=min(cD[-1][3], cD[-1][1], cD[-1][4])
        if today_high==today_low or today_high-today_low < 0.0001:
            today_high=cD[-2][2]; today_low=cD[-2][3]
        RANGE_LOW=today_low * 0.999
        RANGE_HIGH=today_high * 1.001
        MID_HOUSE=(RANGE_HIGH+RANGE_LOW)/2
        RANGE_SIZE=RANGE_HIGH-RANGE_LOW+0.00001

        wick_low_15=c15[-1][3]; wick_high_15=c15[-1][2]
        close_15=c15[-1][4]; open_15=c15[-1][1]
        body_15=abs(close_15-open_15) + 0.00001
        wick_low_size = min(open_15, close_15) - wick_low_15
        wick_high_size = wick_high_15 - max(open_15, close_15)

        pos_side=None; amt=0; entry=0
        for p in ex.fetch_positions([SYMBOL]):
            c=float(p.get('contracts',0) or p.get('info',{}).get('holdVol',0) or 0)
            if abs(c)>0:
                pos_side=(p.get('side') or '').lower()
                txt=str(p).lower()
                if 'long' in txt and not pos_side: pos_side='long'
                if 'short' in txt and not pos_side: pos_side='short'
                amt=abs(c); entry=float(p.get('entryPrice') or p.get('info',{}).get('averageOpenPrice') or 0); break

        def set_iso():
            try: ex.set_margin_mode('ISOLATED', SYMBOL, {'leverage': LEVERAGE})
            except: pass
            try: ex.set_leverage(LEVERAGE, SYMBOL, {'marginMode': 'ISOLATED'})
            except:
                try: ex.set_leverage(LEVERAGE, SYMBOL)
                except: pass
            time.sleep(0.2)

        def get_qty(pct=1.0):
            try: bal=float(free_bal)
            except: bal=10.0
            notional = bal * SIZE_PCT * pct if COMPOUND else MIN_NOTIONAL * pct
            if notional < MIN_NOTIONAL: notional = MIN_NOTIONAL
            if notional > bal * 0.9: notional = bal * 0.9
            if bal < MIN_NOTIONAL: notional = bal * 0.9
            q=notional/price
            return float(ex.amount_to_precision(SYMBOL,q))

        state=load_state(); now=time.time(); day_id = int(cD[-1][0]/86400000)

        # ===== FIX SPAM - DAILY RESET =====
        if state.get("day_id",0)!= day_id:
            state["day_id"]=day_id
            state["first_low"]=False
            state["first_high"]=False
            state["house_sent"]=0
            save_state(state)

        if state.get("house_sent",0)!= day_id:
            if can_send("KOMA", f"HOUSE_{day_id}", 1440):
                _safe_send(f"📅 NEW DAILY HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID_HOUSE:.5f} RSI {rsi:.0f}")
                state["house_sent"]=day_id
                save_state(state)

        last_flip = state.get("last_flip",0)
        if now - last_flip < ANTI_FLIP_MIN*60 and pos_side is None:
            if not (trend_down and vr >= 1.0) and not (trend_up and vr >= 1.0):
                return f"HOLD ANTI-FLIP {int((ANTI_FLIP_MIN*60 - (now-last_flip))/60)}m"

        at_mid = abs(price - MID_HOUSE)/RANGE_SIZE < 0.25
        mid_bull_rev = wick_low_size > body_15*1.2 and at_mid and vr >= 0.7 and 30 <= rsi <= 68 and rsi_fast < 60
        mid_bear_rev = wick_high_size > body_15*1.2 and at_mid and vr >= 0.7 and 32 <= rsi <= 70 and rsi_fast > 40
        at_bottom = wick_low_15 <= RANGE_LOW*1.015
        at_top = wick_high_15 >= RANGE_HIGH*0.985
        is_cut_low = wick_low_15 < RANGE_LOW
        is_cut_high = wick_high_15 > RANGE_HIGH

        if pos_side and entry>0:
            if state.get("pos_time",0)==0: state["pos_time"]=now; save_state(state)
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            held_hours=(now-state.get("pos_time",now))/3600

            if now - last_flip > 180:
                if pos_side=='long' and pct >= MIN_LONG and rsi > 65 and not at_bottom:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    time.sleep(0.15); set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                    state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="long"; save_state(state)
                    m=f"🔄 INSIDE LONG->SHORT {price:.5f} +{pct:.1f}% RSI {rsi:.0f} 1.2% {pct*11:.1f}% ROE"; _safe_send(m); return m
                if pos_side=='short' and pct >= MIN_LONG and rsi < 35 and not at_top:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    time.sleep(0.15); set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                    state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="short"; save_state(state)
                    m=f"🔄 INSIDE SHORT->LONG {price:.5f} +{pct:.1f}% RSI {rsi:.0f} 1.2% {pct*11:.1f}% ROE"; _safe_send(m); return m
                if pos_side=='long' and pct >= FULL_HOUSE and (at_top or price >= RANGE_HIGH*0.988):
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    time.sleep(0.15); set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                    state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="long"; save_state(state)
                    m=f"💰 FULL LONG->SHORT {price:.5f} +{pct:.1f}% 2.8% {pct*11:.1f}% ROE"; _safe_send(m); return m
                if pos_side=='short' and pct >= FULL_HOUSE and (at_bottom or price <= RANGE_LOW*1.012):
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    time.sleep(0.15); set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="short"; save_state(state)
                    m=f"💰 FULL SHORT->LONG {price:.5f} +{pct:.1f}% 2.8% {pct*11:.1f}% ROE"; _safe_send(m); return m

            if held_hours >= MAX_HOLD_HOURS and pct <= -MAX_HOLD_LOSS:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": day_id, "house_sent": day_id, "last_flip": now, "last_side": pos_side})
                m=f"🕛 6H CUT {pos_side.upper()} {pct:.1f}% {held_hours:.1f}h"; _safe_send(m); return m

            if pct > 0.5 and held_hours < MAX_HOLD_HOURS:
                if pos_side=='long' and rsi < 75 and trend_up: return f"HOLD 6H TP LONG {pct:.1f}% {held_hours:.1f}h RSI {rsi:.0f} -> HOLD"
                if pos_side=='short' and rsi > 25 and trend_down: return f"HOLD 6H TP SHORT {pct:.1f}% {held_hours:.1f}h RSI {rsi:.0f} -> HOLD"
            return f"HOLD {pos_side.upper()} {pct:.1f}% {held_hours:.1f}h VOL {vr:.1f}x RSI {rsi:.0f} {session}"

        if pos_side is None:
            if (is_cut_high or at_top) and trend_down and vr >= vol_need and rsi >= 35:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="short"; save_state(state)
                m=f"🐋 INSTANT SHORT HIGH {price:.5f} VOL {vr:.1f}x RSI {rsi:.0f} {session}"; _safe_send(m); return m
            if (is_cut_low or at_bottom) and trend_up and vr >= vol_need and rsi <= 65:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                state["pos_time"]=now; state["last_flip"]=now; state["last_side"]="long"; save_state(state)
                m=f"🐋 INSTANT LONG LOW {price:.5f} VOL {vr:.1f}x RSI {rsi:.0f} {session}"; _safe_send(m); return m

        return f"WAIT HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} price {price:.5f} VOL {vr:.1f}x/{vol_need}x RSI {rsi:.0f} {session}"
    except Exception as e:
        return f"ERR {e} price {price if 'price' in locals() else 'N/A'}"
