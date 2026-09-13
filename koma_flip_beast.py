import ccxt

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4
SL_PCT=12.0
PUMP_PAUSE=0.025

def scalp_plan(ex, free_bal, send_telegram, can_send):
    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl5=[x[4] for x in c5]
        if len(cD)<2: return "WAIT daily"
        price=cl5[-1]

        # === DAILY HOUSE ===
        today_high=cD[-1][2]
        today_low=cD[-1][3]
        if today_high==today_low:
            today_high=cD[-2][2]
            today_low=cD[-2][3]

        RANGE_LOW=today_low
        RANGE_HIGH=today_high
        MID=(RANGE_LOW+RANGE_HIGH)/2

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

        # === MANIPULATION CUT HANDLER ===
        is_cut_low = wick_low_15 < RANGE_LOW
        is_cut_high = wick_high_15 > RANGE_HIGH

        # FAKE CUT low vol = whale stop hunt = BUY BIG CATCH
        if is_cut_low and vr < 0.7:
            if not pos_side or pos_side=='short':
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.8))
                m=f"🐋 FAKE CUT LOW {RANGE_LOW:.5f}->{wick_low_15:.5f} VOL {vr:.1f}x = MANIPULATION -> BUY BIG to {RANGE_HIGH:.5f}"; send_telegram(m); return m

        if is_cut_high and vr < 0.7:
            if not pos_side or pos_side=='long':
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.8))
                m=f"🐋 FAKE CUT HIGH {RANGE_HIGH:.5f}->{wick_high_15:.5f} VOL {vr:.1f}x = MANIPULATION -> SELL BIG to {RANGE_LOW:.5f}"; send_telegram(m); return m

        # REAL BREAK high vol = update house
        if is_cut_low and vr > 1.8:
            RANGE_LOW = wick_low_15
            return f"⚠️ REAL BREAK cut LOW {wick_low_15:.5f} VOL {vr:.1f}x - NEW HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} wait bottom"
        if is_cut_high and vr > 1.8:
            RANGE_HIGH = wick_high_15
            return f"⚠️ REAL BREAK cut HIGH {wick_high_15:.5f} VOL {vr:.1f}x - NEW HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} wait top"

        # === HOLD BIG CATCH ONLY ===
        if pos_side and entry>0:
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100

            if pos_side=='long' and wick_high_15 >= RANGE_HIGH*0.99:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                m=f"💰 BIG CATCH LONG {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} +{pct:.1f}% -> AUTO SHORT"; send_telegram(m); return m

            if pos_side=='short' and wick_low_15 <= RANGE_LOW*1.01:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                m=f"💰 BIG CATCH SHORT {RANGE_HIGH:.5f}->{RANGE_LOW:.5f} +{pct:.1f}% -> AUTO LONG"; send_telegram(m); return m

            if pct<=-SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 SL {pos_side.upper()} {pct:.1f}% CUT {wick_low_15:.5f}/{wick_high_15:.5f}"; send_telegram(m); return m

            return f"HOLD BIG {pos_side.upper()} {pct:.1f}% HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} VOL {vr:.1f}x"

        # === ENTRY ONLY MOST WICK ===
        if wick_low_15 <= RANGE_LOW*1.01 and vr>0.15:
            set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
            m=f"🟢 BUY BOTTOM MOST {RANGE_LOW:.5f} wick {wick_low_15:.5f} TARGET {RANGE_HIGH:.5f} VOL {vr:.1f}x"; send_telegram(m); return m

        if wick_high_15 >= RANGE_HIGH*0.99 and vr>0.15:
            set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
            m=f"🔴 SELL TOP MOST {RANGE_HIGH:.5f} wick {wick_high_15:.5f} TARGET {RANGE_LOW:.5f} VOL {vr:.1f}x"; send_telegram(m); return m

        return f"WAIT BIG CATCH DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} price {price:.5f} VOL {vr:.1f}x"
    except Exception as e:
        return f"ERR {e}"
