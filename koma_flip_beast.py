import ccxt
import os, json, time
from datetime import datetime, timezone

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=11
SIZE_PCT=0.5
SL_PCT=8.0
MAX_HOLD_HOURS=6
MAX_HOLD_LOSS=8.0
PUMP_PAUSE=0.025
MIN_NOTIONAL=7
COMPOUND=True

STATE_FILE="koma_retest_state.json"
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE).read())
    except: pass
    return {"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": 0, "house_sent": 0}
def save_state(s):
    try: open(STATE_FILE,'w').write(json.dumps(s))
    except: pass

def scalp_plan(ex, free_bal, send_telegram, can_send):
    def _safe_send(msg):
        IMPORTANT = ["💰 BIG CATCH", "🐋 RETEST", "🔥 REAL BREAK", "🛑 SL", "🎯 MID", "📅 NEW DAILY", "🕛 6H CUT"]
        if not any(x in msg for x in IMPORTANT):
            return
        try:
            if "NEW DAILY" in msg:
                if not can_send("KOMA", f"HOUSE_{msg[:30]}", 1440):
                    return
            else:
                if not can_send("KOMA", msg[:30], 15):
                    return
            send_telegram(msg)
        except:
            send_telegram(msg)

    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl5=[x[4] for x in c5]
        if len(cD)<2: return "WAIT daily"
        price=cl5[-1]

        pump = abs(cl5[-1]-cl5[-2])/cl5[-2] if len(cl5)>2 else 0
        if pump > PUMP_PAUSE:
            return f"⏸️ PUMP PAUSE {pump*100:.2f}% > {PUMP_PAUSE*100}% - skip"

        today_high=max(cD[-1][2], cD[-1][1], cD[-1][4])
        today_low=min(cD[-1][3], cD[-1][1], cD[-1][4])
        if today_high==today_low or today_high-today_low < 0.0001:
            today_high=cD[-2][2]
            today_low=cD[-2][3]
        RANGE_LOW=today_low * 0.999
        RANGE_HIGH=today_high * 1.001
        MID_HOUSE=(RANGE_HIGH+RANGE_LOW)/2
        RANGE_SIZE=RANGE_HIGH-RANGE_LOW+0.00001

        wick_low_15=c15[-1][3]
        wick_high_15=c15[-1][2]
        close_15=c15[-1][4]
        open_15=c15[-1][1]
        body_15=abs(close_15-open_15) + 0.00001

        va=sum([float(x[5] or 0) for x in c5[-21:-1]])/20 if len(c5)>21 else float(c5[-1][5] or 1)
        if va < 1: va = float(c5[-1][5] or 1) or 1
        vr=float(c5[-1][5] or 0)/(va+0.001)
        if vr < 0.1: vr = 1.0
        if vr > 3.0: vr = 3.0

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
            try: ex.set_margin_mode('ISOLATED', SYMBOL, {'leverage': LEVERAGE})
            except: pass
            try: ex.set_leverage(LEVERAGE, SYMBOL, {'marginMode': 'ISOLATED'})
            except:
                try: ex.set_leverage(LEVERAGE, SYMBOL)
                except: pass
            try: ex.set_margin_mode('isolated', SYMBOL)
            except: pass
            time.sleep(0.2)

        def get_qty(pct=1.0):
            try: bal=float(free_bal)
            except: bal=10.0
            if COMPOUND:
                notional = bal * SIZE_PCT * pct
            else:
                notional = MIN_NOTIONAL * pct
            if notional < MIN_NOTIONAL:
                notional = MIN_NOTIONAL
            if notional > bal * 0.9:
                notional = bal * 0.9
            if bal < MIN_NOTIONAL:
                notional = bal * 0.9
            q=notional/price
            return float(ex.amount_to_precision(SYMBOL,q))

        state=load_state()
        now=time.time()
        day_id = int(cD[-1][0]/86400000)

        # FINAL FIX - HOUSE ONLY 1X PER DAY
        if state.get("day_id",0)!= day_id:
            prev_sent = state.get("house_sent",0)
            state = {"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": state.get("pos_time",0), "day_id": day_id, "house_sent": prev_sent}
            save_state(state)

        if state.get("house_sent",0)!= day_id:
            _safe_send(f"📅 NEW DAILY HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID_HOUSE:.5f} old retest cleared")
            state["house_sent"] = day_id
            save_state(state)

        is_cut_low = wick_low_15 < RANGE_LOW
        is_cut_high = wick_high_15 > RANGE_HIGH
        at_bottom = wick_low_15 <= RANGE_LOW*1.01
        at_top = wick_high_15 >= RANGE_HIGH*0.99

        sweep_low_reclaim = wick_low_15 < RANGE_LOW and close_15 > RANGE_LOW
        sweep_high_reclaim = wick_high_15 > RANGE_HIGH and close_15 < RANGE_HIGH
        wick_low_size = min(open_15, close_15) - wick_low_15
        wick_high_size = wick_high_15 - max(open_15, close_15)
        is_stop_hunt_low = sweep_low_reclaim and wick_low_size > body_15*1.2
        is_stop_hunt_high = sweep_high_reclaim and wick_high_size > body_15*1.2
        real_break_low = close_15 < RANGE_LOW and vr >= 1.1
        real_break_high = close_15 > RANGE_HIGH and vr >= 1.1
        shoot_out_low = wick_low_15 < RANGE_LOW*0.985
        shoot_out_high = wick_high_15 > RANGE_HIGH*1.015

        at_mid = abs(price - MID_HOUSE)/RANGE_SIZE < 0.25
        mid_bull_rev = wick_low_size > body_15*1.2 and close_15 > open_15 and at_mid and vr >= 0.7
        mid_bear_rev = wick_high_size > body_15*1.2 and close_15 < open_15 and at_mid and vr >= 0.7

        if pos_side and entry>0:
            if state.get("pos_time",0)==0:
                state["pos_time"]=now; save_state(state)
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            held_hours=(now-state.get("pos_time",now))/3600

            if held_hours >= MAX_HOLD_HOURS and pct <= -MAX_HOLD_LOSS:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": day_id, "house_sent": day_id})
                m=f"🕛 6H CUT {pos_side.upper()} {pct:.1f}% {held_hours:.1f}h HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID_HOUSE:.5f}"; _safe_send(m); return m

            if pos_side=='short' and is_stop_hunt_high:
                return f"HOLD STOP-HUNT HIGH"
            if pos_side=='long' and is_stop_hunt_low:
                return f"HOLD STOP-HUNT LOW"

            if pos_side=='short':
                if is_cut_high and vr < 0.9 and not real_break_high:
                    return f"HOLD SHORT FAKE HIGH"
                if real_break_high or shoot_out_high and vr >= 1.1:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    state["pos_time"]=now; save_state(state)
                    m=f"🔥 REAL BREAK SHOOT HIGH {wick_high_15:.5f} close {close_15:.5f}>{RANGE_HIGH:.5f} VOL {vr:.1f}x FLIP LONG"; _safe_send(m); return m

            if pos_side=='long':
                if is_cut_low and vr < 0.9 and not real_break_low:
                    return f"HOLD LONG FAKE LOW"
                if real_break_low or shoot_out_low and vr >= 1.1:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                    state["pos_time"]=now; save_state(state)
                    m=f"🔥 REAL BREAK SHOOT LOW {wick_low_15:.5f} close {close_15:.5f}<{RANGE_LOW:.5f} VOL {vr:.1f}x FLIP SHORT"; _safe_send(m); return m

            if pos_side=='long' and at_top:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": day_id, "house_sent": day_id})
                m=f"💰 BIG CATCH LONG {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} +{pct:.1f}% VOL {vr:.1f}x -> SHORT"; _safe_send(m); return m

            if pos_side=='short' and at_bottom:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": day_id, "house_sent": day_id})
                m=f"💰 BIG CATCH SHORT {RANGE_HIGH:.5f}->{RANGE_LOW:.5f} +{pct:.1f}% VOL {vr:.1f}x -> LONG"; _safe_send(m); return m

            if pct<=-SL_PCT and vr >= 1.1:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0, "low_time": 0, "high_time": 0, "pos_time": 0, "day_id": day_id, "house_sent": day_id})
                m=f"🛑 SL REAL {pos_side.upper()} {pct:.1f}% VOL {vr:.1f}x"; _safe_send(m); return m
            if pct<=-SL_PCT and vr < 0.9:
                return f"HOLD {pos_side.upper()} {pct:.1f}% FAKE WICK IGNORE"

            return f"HOLD {pos_side.upper()} {pct:.1f}% {held_hours:.1f}h MID {MID_HOUSE:.5f} VOL {vr:.1f}x"

        if state.get("pos_time",0)!=0:
            state["pos_time"]=0; save_state(state)

        if pos_side is None:
            if mid_bull_rev:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.5))
                state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                m=f"🎯 MID BULL REV 25% {MID_HOUSE:.5f} price {price:.5f} VOL {vr:.1f}x -> TO {RANGE_HIGH:.5f}"; _safe_send(m); return m
            if mid_bear_rev:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.5))
                state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                m=f"🎯 MID BEAR REV 25% {MID_HOUSE:.5f} price {price:.5f} VOL {vr:.1f}x -> TO {RANGE_LOW:.5f}"; _safe_send(m); return m

            if is_cut_low or at_bottom or shoot_out_low:
                if not state["first_low"]:
                    state["first_low"]=True; state["low_time"]=now; state["low_price"]=price; save_state(state)
                    return f"👀 FIRST TOUCH LOW WAITING RETEST"
                else:
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                    m=f"🐋 RETEST BUY LOW 2ND TOUCH {RANGE_LOW:.5f} VOL {vr:.1f}x MID {MID_HOUSE:.5f} -> TO {RANGE_HIGH:.5f}"; _safe_send(m); return m

            if is_cut_high or at_top or shoot_out_high:
                if not state["first_high"]:
                    state["first_high"]=True; state["high_time"]=now; state["high_price"]=price; save_state(state)
                    return f"👀 FIRST TOUCH HIGH WAITING RETEST"
                else:
                    set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                    state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                    m=f"🐋 RETEST SELL HIGH 2ND TOUCH {RANGE_HIGH:.5f} VOL {vr:.1f}x MID {MID_HOUSE:.5f} -> TO {RANGE_LOW:.5f}"; _safe_send(m); return m

            if state["first_low"] and (now - state["low_time"]) > 7200 and vr >= 1.0:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.4))
                state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                m=f"⏰ FALLBACK BUY LOW {RANGE_LOW:.5f} 2H no retest"; _safe_send(m); return m

            if state["first_high"] and (now - state["high_time"]) > 7200 and vr >= 1.0:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.4))
                state["pos_time"]=now; state["first_low"]=False; state["first_high"]=False; save_state(state)
                m=f"⏰ FALLBACK SELL HIGH {RANGE_HIGH:.5f} 2H no retest"; _safe_send(m); return m

        if state["first_low"] and price > RANGE_LOW*1.03:
            return f"WAIT RETEST LOW ready"
        if state["first_high"] and price < RANGE_HIGH*0.97:
            return f"WAIT RETEST HIGH ready"

        return f"WAIT RETEST WICK HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID_HOUSE:.5f} price {price:.5f} VOL {vr:.1f}x"
    except Exception as e:
        return f"ERR {e}"
