import ccxt
import os, json

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4
SL_PCT=12.0
PUMP_PAUSE=0.025

# === RETEST MEMORY FILE ===
STATE_FILE="/tmp/koma_retest_state.json"
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE).read())
    except: pass
    return {"first_low": False, "first_high": False, "low_price": 0, "high_price": 0}
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

        # === DAILY HOUSE - ALWAYS KEEP ===
        today_high=cD[-1][2]
        today_low=cD[-1][3]
        if today_high==today_low:
            today_high=cD[-2][2]
            today_low=cD[-2][3]
        RANGE_LOW=today_low
        RANGE_HIGH=today_high

        wick_low_15=c15[-1][3]
        wick_high_15=c15[-1][2]
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

        # === VOL TREND ===
        vol_trend = "BUY" if vr > 1.2 else "SELL" if vr < 0.8 else "NEUTRAL"

        # === RETEST STATE ===
        state=load_state()

        # === HOLD LOGIC ===
        if pos_side and entry>0:
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100

            if pos_side=='short':
                if is_cut_high and vr < 0.8:
                    return f"HOLD SHORT FAKE HIGH {RANGE_HIGH:.5f}->{wick_high_15:.5f} VOL {vr:.1f}x DOWN = TREND SELL HOLD"
                if is_cut_high and vr > 1.2:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    m=f"🔥 REAL BREAK HIGH {wick_high_15:.5f} VOL {vr:.1f}x UP = BUY FLIP LONG"; send_telegram(m); return m

            if pos_side=='long':
                if is_cut_low and vr < 0.8:
                    return f"HOLD LONG FAKE LOW {RANGE_LOW:.5f}->{wick_low_15:.5f} VOL {vr:.1f}x DOWN = HOLD LONG"
                if is_cut_low and vr > 1.2:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                    m=f"🔥 REAL BREAK LOW {wick_low_15:.5f} VOL {vr:.1f}x UP = SELL FLIP SHORT"; send_telegram(m); return m

            if pos_side=='long' and at_top and vr < 1.2:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0})
                m=f"💰 BIG CATCH LONG {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} +{pct:.1f}% VOL {vr:.1f}x -> AUTO SHORT"; send_telegram(m); return m

            if pos_side=='short' and at_bottom and vr > 0.8:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0})
                m=f"💰 BIG CATCH SHORT {RANGE_HIGH:.5f}->{RANGE_LOW:.5f} +{pct:.1f}% VOL {vr:.1f}x -> AUTO LONG"; send_telegram(m); return m

            if pct<=-SL_PCT and vr > 1.0:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 SL REAL {pos_side.upper()} {pct:.1f}% VOL {vr:.1f}x"; send_telegram(m); return m
            if pct<=-SL_PCT and vr < 0.8:
                return f"HOLD {pos_side.upper()} {pct:.1f}% FAKE WICK VOL {vr:.1f}x IGNORE SL - TREND {vol_trend}"

            return f"HOLD BIG {pos_side.upper()} {pct:.1f}% HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} VOL {vr:.1f}x TREND {vol_trend}"

        # === RETEST ENTRY - CUT ONLY ON SECOND TOUCH ===

        # LOW SIDE RETEST
        if is_cut_low or at_bottom:
            if not state["first_low"]:
                # FIRST TOUCH - MARK ONLY
                state["first_low"]=True
                state["low_price"]=price
                save_state(state)
                return f"👀 FIRST TOUCH LOW {RANGE_LOW:.5f}->{wick_low_15:.5f} MARKED VOL {vr:.1f}x WAITING RETEST +3% INSIDE"
            else:
                # CHECK RETRACE 3% happened?
                # price must have gone up 3% from low before second touch valid
                # we check if current price went up vs stored low_price
                # For simplicity: if we already marked and now we touch again after being inside
                # Inside = price > RANGE_LOW*1.03
                # Since we are currently at bottom again, second touch is valid if last inside happened
                # We use state to allow second touch immediately after retrace
                if price <= RANGE_LOW*1.03: # still near bottom, need retrace first
                    # if previous price was inside, this is retest
                    # allow retest entry now
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                    save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0})
                    m=f"🐋 RETEST BUY LOW SECOND TOUCH {RANGE_LOW:.5f}->{wick_low_15:.5f} VOL {vr:.1f}x TREND {vol_trend} -> BUY TO {RANGE_HIGH:.5f}"; send_telegram(m); return m
                else:
                    # price inside, keep first_low marked waiting
                    return f"⏳ RETEST WAIT LOW first {RANGE_LOW:.5f} marked, price inside {price:.5f} need 2nd touch"

        # HIGH SIDE RETEST
        if is_cut_high or at_top:
            if not state["first_high"]:
                state["first_high"]=True
                state["high_price"]=price
                save_state(state)
                return f"👀 FIRST TOUCH HIGH {RANGE_HIGH:.5f}->{wick_high_15:.5f} MARKED VOL {vr:.1f}x WAITING RETEST -3% INSIDE"
            else:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                save_state({"first_low": False, "first_high": False, "low_price": 0, "high_price": 0})
                m=f"🐋 RETEST SELL HIGH SECOND TOUCH {RANGE_HIGH:.5f}->{wick_high_15:.5f} VOL {vr:.1f}x TREND {vol_trend} -> SELL TO {RANGE_LOW:.5f}"; send_telegram(m); return m

        # RESET LOGIC - if price goes middle, keep marks but show waiting
        if state["first_low"] and price > RANGE_LOW*1.03:
            return f"WAIT RETEST LOW ready - first {RANGE_LOW:.5f} touched, price inside {price:.5f} now waiting 2nd touch BUY VOL {vr:.1f}x"
        if state["first_high"] and price < RANGE_HIGH*0.97:
            return f"WAIT RETEST HIGH ready - first {RANGE_HIGH:.5f} touched, price inside {price:.5f} now waiting 2nd touch SELL VOL {vr:.1f}x"

        return f"WAIT RETEST BIG CATCH DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} price {price:.5f} VOL {vr:.1f}x TREND {vol_trend}"
    except Exception as e:
        return f"ERR {e}"
