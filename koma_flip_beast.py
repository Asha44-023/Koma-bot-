import ccxt
SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4
SL_PCT=12.0
PUMP_PAUSE=0.025

def calc_rsi(c,p=14):
    if len(c)<p+1: return 50
    g=l=0
    for i in range(-p,0):
        d=c[i]-c[i-1]
        if d>0: g+=d
        else: l-=d
    if l==0: return 75
    return 100-(100/(1+g/(l+0.0001)))

def scalp_plan(ex, free_bal, send_telegram, can_send):
    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c15=ex.fetch_ohlcv(SYMBOL,'15m',limit=80)
        cD=ex.fetch_ohlcv(SYMBOL,'1d',limit=10)
        cl5=[x[4] for x in c5]
        cl15=[x[4] for x in c15]
        if len(cD)<2: return "WAIT loading daily"
        price=cl5[-1]

        # DAILY MOST WICK
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

        up_c=sum(1 for i in range(-5,0) if cl15[i] > c15[i][1])
        direction_up=up_c>=3
        in_mid_zone=MID*0.96 < price < MID*1.04

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

        if price>PUMP_PAUSE and pos_side=='short':
            return f"⏸️ PAUSE SHORT I breakout {price:.5f} > {PUMP_PAUSE}"
        if price<RANGE_LOW*0.6:
            return f"⏸️ PAUSE LONG breakdown {price:.5f} wait new daily"

        if pos_side and entry>0:
            pct=(price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100

            if in_mid_zone:
                if pos_side=='long' and direction_up:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    m=f"✅ FADE MID TP LONG UP {up_c}/5 mid {MID:.5f} +{pct:.1f}%"; send_telegram(m); return m
                if pos_side=='short' and not direction_up:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    m=f"✅ FADE MID TP SHORT DOWN {5-up_c}/5 mid {MID:.5f} +{pct:.1f}%"; send_telegram(m); return m

            if pos_side=='long' and price>=MID*0.995:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                if wick_high_15>=RANGE_HIGH*0.99:
                    set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
                    m=f"✅ TP MID LONG + 🔄 AUTO SELL TOP MOST {RANGE_HIGH:.5f} +{pct:.1f}%"; send_telegram(m); return m
                m=f"✅ TP MID LONG {RANGE_LOW:.5f}->{MID:.5f} +{pct:.1f}%"; send_telegram(m); return m

            if pos_side=='short' and price<=MID*1.005:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                if wick_low_15<=RANGE_LOW*1.01:
                    set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
                    m=f"✅ TP MID SHORT + 🔄 AUTO BUY BOTTOM MOST {RANGE_LOW:.5f} +{pct:.1f}%"; send_telegram(m); return m
                m=f"✅ TP MID SHORT {RANGE_HIGH:.5f}->{MID:.5f} +{pct:.1f}%"; send_telegram(m); return m

            if pos_side=='long' and wick_low_15<=RANGE_LOW*1.01 and vr>1.2:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.7))
                return f"➕ ADD LONG bottom most {RANGE_LOW:.5f}"
            if pos_side=='short' and wick_high_15>=RANGE_HIGH*0.99 and vr>1.2:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.7))
                return f"➕ ADD SHORT top most {RANGE_HIGH:.5f}"

            if pct<=-SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 SL {pos_side.upper()} {pct:.1f}% DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f}"; send_telegram(m); return m

            return f"HOLD {pos_side.upper()} {pct:.1f}% -> MID {MID:.5f} DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} {'UP' if direction_up else 'DOWN'}"

        if in_mid_zone:
            return f"WAIT FADE MID {'UP' if direction_up else 'DOWN'} {up_c}/5 mid {MID:.5f} BLOCK price {price:.5f} DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f}"

        if wick_low_15<=RANGE_LOW*1.01:
            set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6))
            m=f"🟢 BUY BOTTOM MOST {RANGE_LOW:.5f} wick {wick_low_15:.5f} -> MID {MID:.5f} @{price:.5f}"; send_telegram(m); return m
        if wick_high_15>=RANGE_HIGH*0.99:
            set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
            m=f"🔴 SELL TOP MOST {RANGE_HIGH:.5f} wick {wick_high_15:.5f} -> MID {MID:.5f} @{price:.5f}"; send_telegram(m); return m

        return f"WAIT DAILY {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID:.5f} price {price:.5f} DIR {'UP' if direction_up else 'DOWN'}"
    except Exception as e:
        return f"ERR {e}"
