import ccxt

SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4 # 40% compound
SL_PCT=12.0
PUMP_PAUSE=0.025

def scalp_plan(ex, free_bal, send_telegram, can_send):
    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl5=[x[4] for x in c5]
        cl15=[x[4] for x in c15]
        if len(cD)<2: return "WAIT daily loading"
        price=cl5[-1]

        # === DAILY MOST WICK - BIG CATCH HOUSE ===
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

        # PAUSE on pump
        if price>PUMP_PAUSE and pos_side=='short':
            return f"⏸️ PAUSE SHORT pump {price:.5f} > {PUMP_PAUSE} - wait dump to catch big"
        if price<RANGE_LOW*0.6:
            return f"⏸️ PAUSE breakdown {price:.5f} wait new daily"

        # === HOLD - BIG CATCH ONLY ===
        if pos_side and entry>0:
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100

            # BIG CATCH TP - ONLY at opposite most wick
            if pos_side=='long' and wick_high_15>=RANGE_HIGH*0.99:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                set_iso()
                ex.create_market_order(SYMBOL,'sell',get_qty(0.6)) # AUTO SWITCH SHORT FOR NEXT BIG CATCH
                m=f"💰 BIG CATCH LONG WIN {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} +{pct:.1f}% bal {free_bal} -> AUTO SHORT TOP"; send_telegram(m); return m

            if pos_side=='short' and wick_low_15<=RANGE_LOW*1.01:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                set_iso()
                ex.create_market_order(SYMBOL,'buy',get_qty(0.6)) # AUTO SWITCH LONG FOR NEXT BIG CATCH
                m=f"💰 BIG CATCH SHORT WIN {RANGE_HIGH:.5f}->{RANGE_LOW:.5f} +{pct:.1f}% bal {free_bal} -> AUTO LONG BOTTOM"; send_telegram(m); return m

            # MID = ADD only, NOT TP - to make big catch bigger
            in_mid_low = price < MID*1.03 and price > MID*0.97
            if pos_side=='long' and in_mid_low and vr>1.3 and pct>-3:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.5))
                return f"➕ ADD LONG mid {MID:.5f} to boost BIG CATCH to {RANGE_HIGH:.5f} {pct:.1f}%"

            if pos_side=='short' and in_mid_low and vr>1.3 and pct>-3:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.5))
                return f"➕ ADD SHORT mid {MID:.5f} to boost BIG CATCH to {RANGE_LOW:.5f} {pct:.1f}%"

            if pct<=-SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 SL BIG CATCH {pos_side.upper()} {pct:.1f}% DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f}"; send_telegram(m); return m

            return f"HOLD BIG CATCH {pos_side.upper()} {pct:.1f}% {RANGE_LOW:.5f}->{RANGE_HIGH:.5f} -> target {RANGE_HIGH if pos_side=='long' else RANGE_LOW:.5f}"

        # === ENTRY - ONLY AT MOST WICKS ===
        if wick_low_15<=RANGE_LOW*1.01:
            set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
            m=f"🟢 BIG CATCH BUY BOTTOM MOST {RANGE_LOW:.5f} wick {wick_low_15:.5f} TARGET TOP {RANGE_HIGH:.5f} @{price:.5f} VOL {vr:.1f}x"; send_telegram(m); return m

        if wick_high_15>=RANGE_HIGH*0.99:
            set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
            m=f"🔴 BIG CATCH SELL TOP MOST {RANGE_HIGH:.5f} wick {wick_high_15:.5f} TARGET BOTTOM {RANGE_LOW:.5f} @{price:.5f} VOL {vr:.1f}x"; send_telegram(m); return m

        return f"WAIT BIG CATCH DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} price {price:.5f} VOL {vr:.1f}x - waiting for most wick"
    except Exception as e:
        return f"ERR {e}"
