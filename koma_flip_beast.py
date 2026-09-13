import ccxt
import os, json, time

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4
SL_PCT=12.0
MAX_HOLD_HOURS=6
MAX_HOLD_LOSS=8.0
PUMP_PAUSE=0.025

STATE_FILE="/tmp/koma_retest_state.json"
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE).read())
    except: pass
    return {"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0}
def save_state(s):
    try: open(STATE_FILE,'w').write(json.dumps(s))
    except: pass

def scalp_plan(ex, free_bal, send_telegram, can_send):
    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl5=[x[4] for x in c5]
        if len(cD)<2: return "WAIT daily"
        price=cl5[-1]

        # === WICK BASED DAILY HOUSE - TRUE WHALE WALL ===
        today_high=max(cD[-1][2], cD[-1][1], cD[-1][4])
        today_low=min(cD[-1][3], cD[-1][1], cD[-1][4])
        if today_high==today_low or today_high-today_low < 0.0001:
            today_high=cD[-2][2]
            today_low=cD[-2][3]
        RANGE_LOW=today_low * 0.999
        RANGE_HIGH=today_high * 1.001

        # === CANDLE DATA FOR WHALE ===
        wick_low_15=c15[-1][3]
        wick_high_15=c15[-1][2]
        close_15=c15[-1][4]
        open_15=c15[-1][1]
        body_15=abs(close_15-open_15) + 0.00001

        va=sum([x[5] for x in c5[-21:-1]])/20 if len(c5)>21 else c5[-1][5]
        vr=c5[-1][5]/(va+0.001)

        pos_side=None; amt=0; entry=0
        for p in ex.fetch_positions([SYMBOL]):
            c=float(p.get('contracts',0) or p.get('info',{}).get('holdVol',0) or 0)
            if abs(c)>0:
                pos_side=(p.get('side') or '').lower()
                txt=str(p).lower()
                if 'long' in txt and not pos_side: pos_side='long'
                if 'short' in txt and not pos_side: pos_side='short'
                amt=abs(c)
                entry=float(p.get('entryPrice') or p.get('info',{}).get('averageOpenPrice') or 0)
                break

        def set_iso():
            try:
                ex.set_leverage(LEVERAGE,SYMBOL)
                ex.set_margin_mode('ISOLATED', SYMBOL, {'leverage': LEVERAGE})
            except:
                try: ex.set_margin_mode('isolated', SYMBOL)
                except: pass

        def get_qty(pct=1.0):
            try: bal=float(free_bal)
            except: bal=10.0
            notional=bal*SIZE_PCT*pct
            if notional<5: notional=5
            if notional>bal*0.9: notional=bal*0.9
            q=notional/price
            return float(ex.amount_to_precision(SYMBOL,q))

        is_cut_low = wick_low_15 < RANGE_LOW
        is_cut_high = wick_high_15 > RANGE_HIGH
        at_bottom = wick_low_15 <= RANGE_LOW*1.01
        at_top = wick_high_15 >= RANGE_HIGH*0.99

        # === WHALE MANIPULATION LOGIC ===
        sweep_low_reclaim = wick_low_15 < RANGE_LOW and close_15 > RANGE_LOW
        sweep_high_reclaim = wick_high_15 > RANGE_HIGH and close_15 < RANGE_HIGH
        wick_low_size = min(open_15, close_15) - wick_low_15
        wick_high_size = wick_high_15 - max(open_15, close_15)
        is_stop_hunt_low = sweep_low_reclaim and wick_low_size > body_15*1.2 and vr < 0.9
        is_stop_hunt_high = sweep_high_reclaim and wick_high_size > body_15*1.2 and vr < 0.9
        real_break_low = close_15 < RANGE_LOW and vr > 1.3
        real_break_high = close_15 > RANGE_HIGH and vr > 1.3
        # Liquidity pools yesterday
        y_low=cD[-2][3]
        y_high=cD[-2][2]
        near_y_liq = abs(price-y_low)/y_low < 0.02 or abs(price-y_high)/y_high < 0.02

        vol_trend = "BUY" if vr > 1.2 else "SELL" if vr < 0.8 else "NEUTRAL"
        state=load_state()
        now=time.time()

        # === HOLD LOGIC WITH WHALE ===
        if pos_side and entry>0:
            if state.get("pos_time",0)==0:
                state["pos_time"]=now
                save_state(state)
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            held_hours=(now-state.get("pos_time",now))/3600

            # 6H MAX HOLD SAFETY
            if held_hours >= MAX_HOLD_HOURS and pct <= -MAX_HOLD_LOSS:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0})
                m=f"🕛 6H MAX HOLD CUT {pos_side.upper()} {pct:.1f}% held {held_hours:.1f}h WICK {RANGE_LOW:.5f}-{RANGE_HIGH:.5f}"; send_telegram(m); return m

            if pos_side=='short' and is_stop_hunt_high:
                return f"🐋 WHALE STOP HUNT HIGH {RANGE_HIGH:.5f}->{wick_high_15:.5f} reclaim {close_15:.5f} VOL {vr:.1f}x HOLD SHORT - LIQ GRAB"
            if pos_side=='long' and is_stop_hunt_low:
                return f"🐋 WHALE STOP HUNT LOW {RANGE_LOW:.5f}->{wick_low_15:.5f} reclaim {close_15:.5f} VOL {vr:.1f}x HOLD LONG - LIQ GRAB"

            if pos_side=='short':
                if is_cut_high and vr < 0.8:
                    return f"HOLD SHORT FAKE HIGH WICK {RANGE_HIGH:.5f}->{wick_high_15:.5f} VOL {vr:.1f}x {held_hours:.1f}h"
                if real_break_high:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    state["pos_time"]=now; save_state(state)
                    m=f"🔥 REAL BREAK HIGH WICK CLOSE {close_15:.5f}>{RANGE_HIGH:.5f} VOL {vr:.1f}x = BUY FLIP LONG"; send_telegram(m); return m

            if pos_side=='long':
                if is_cut_low and vr < 0.8:
                    return f"HOLD LONG FAKE LOW WICK {RANGE_LOW:.5f}->{wick_low_15:.5f} VOL {vr:.1f}x {held_hours:.1f}h"
                if real_break_low:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                    state["pos_time"]=now; save_state(state)
                    m=f"🔥 REAL BREAK LOW WICK CLOSE {close_15:.5f}<{RANGE_LOW:.5f} VOL {vr:.1f}x = SELL FLIP SHORT"; send_telegram(m); return m

            if pos_side=='long' and at_top and vr < 1.2:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0})
                m=f"💰 BIG CATCH WICK LONG {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} +{pct:.1f}% VOL {vr:.1f}x {held_hours:.1f}h -> AUTO SHORT"; send_telegram(m); return m

            if pos_side=='short' and at_bottom and vr > 0.8:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0})
                m=f"💰 BIG CATCH WICK SHORT {RANGE_HIGH:.5f}->{RANGE_LOW:.5f} +{pct:.1f}% VOL {vr:.1f}x {held_hours:.1f}h -> AUTO LONG"; send_telegram(m); return m

            if pct<=-SL_PCT and vr > 1.0:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0})
                m=f"🛑 SL REAL {pos_side.upper()} {pct:.1f}% VOL {vr:.1f}x {held_hours:.1f}h"; send_telegram(m); return m
            if pct<=-SL_PCT and vr < 0.8:
                return f"HOLD {pos_side.upper()} {pct:.1f}% FAKE WICK IGNORE SL {held_hours:.1f}h/{MAX_HOLD_HOURS}h LIQ {'Y-LOW/HIGH' if near_y_liq else ''}"

            return f"HOLD BIG WICK {pos_side.upper()} {pct:.1f}% {held_hours:.1f}h HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} VOL {vr:.1f}x {vol_trend} {'STOP-HUNT' if is_stop_hunt_low or is_stop_hunt_high else ''}"

        # === NO POSITION ===
        if state.get("pos_time",0)!=0:
            state["pos_time"]=0
            save_state(state)

        # === RETEST ENTRY WHALE LOGIC ===

        if is_cut_low or at_bottom:
            if not state["first_low"]:
                state["first_low"]=True
                state["low_time"]=now
                state["low_price"]=price
                save_state(state)
                return f"👀 FIRST TOUCH LOW WICK {RANGE_LOW:.5f}->{wick_low_15:.5f} close {close_15:.5f} {'STOP-HUNT' if is_stop_hunt_low else ''} VOL {vr:.1f}x WAITING RETEST"
            else:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                state["pos_time"]=now
                state["first_low"]=False
                state["first_high"]=False
                save_state(state)
                m=f"🐋 RETEST BUY LOW WICK 2ND TOUCH {RANGE_LOW:.5f}->{wick_low_15:.5f} VOL {vr:.1f}x reclaim {close_15:.5f} -> TO {RANGE_HIGH:.5f}"; send_telegram(m); return m

        if is_cut_high or at_top:
            if not state["first_high"]:
                state["first_high"]=True
                state["high_time"]=now
                state["high_price"]=price
                save_state(state)
                return f"👀 FIRST TOUCH HIGH WICK {RANGE_HIGH:.5f}->{wick_high_15:.5f} close {close_15:.5f} {'STOP-HUNT' if is_stop_hunt_high else ''} VOL {vr:.1f}x WAITING RETEST"
            else:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                state["pos_time"]=now
                state["first_low"]=False
                state["first_high"]=False
                save_state(state)
                m=f"🐋 RETEST SELL HIGH WICK 2ND TOUCH {RANGE_HIGH:.5f}->{wick_high_15:.5f} VOL {vr:.1f}x reclaim {close_15:.5f} -> TO {RANGE_LOW:.5f}"; send_telegram(m); return m

        # === 2H TIMEOUT FALLBACK V-SHAPE ===
        if state["first_low"] and (now - state["low_time"]) > 7200 and vr >= 1.0:
            set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.4))
            state["pos_time"]=now
            state["first_low"]=False
            state["first_high"]=False
            save_state(state)
            m=f"⏰ TIMEOUT FALLBACK BUY WICK LOW {RANGE_LOW:.5f} 2H no retest VOL {vr:.1f}x 0.4 V-SHAPE"; send_telegram(m); return m

        if state["first_high"] and (now - state["high_time"]) > 7200 and vr >= 1.0:
            set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.4))
            state["pos_time"]=now
            state["first_low"]=False
            state["first_high"]=False
            save_state(state)
            m=f"⏰ TIMEOUT FALLBACK SELL WICK HIGH {RANGE_HIGH:.5f} 2H no retest VOL {vr:.1f}x 0.4 V-SHAPE"; send_telegram(m); return m

        if state["first_low"] and price > RANGE_LOW*1.03:
            return f"WAIT RETEST LOW WICK ready {RANGE_LOW:.5f} {(now-state['low_time'])/60:.0f}m ago inside {price:.5f} VOL {vr:.1f}x {'Y-LIQ' if near_y_liq else ''}"
        if state["first_high"] and price < RANGE_HIGH*0.97:
            return f"WAIT RETEST HIGH WICK ready {RANGE_HIGH:.5f} {(now-state['high_time'])/60:.0f}m ago inside {price:.5f} VOL {vr:.1f}x {'Y-LIQ' if near_y_liq else ''}"

        return f"WAIT RETEST WICK HOUSE DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} price {price:.5f} VOL {vr:.1f}x TREND {vol_trend} {'STOP-HUNT' if is_stop_hunt_low or is_stop_hunt_high else ''}"
    except Exception as e:
        return f"ERR {e}"
