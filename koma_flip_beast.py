import ccxt
SYMBOL="KOMA/USDT:USDT"
LEVERAGE=10
SIZE_PCT=0.4 # 40% base, 90% max after adds - safe for 365 days
SL_PCT=12.0 # wide for MEXC wicks
PUMP_PAUSE=0.025 # pause shorts above this - your I top
TP_MID_OFFSET=0.0

def calc_rsi(c,p=14):
    if len(c)<p+1: return 50
    g=l=0
    for i in range(-p,0):
        d=c[i]-c[i-1]
        if d>0: g+=d
        else: l-=d
    if l==0: return 75
    return 100-(100/(1+g/(l+0.0001)))

def calc_ema(c, p=20):
    if len(c) < p: return sum(c)/len(c)
    k = 2/(p+1)
    ema = sum(c[:p])/p
    for price in c[p:]:
        ema = price * k + ema * (1-k)
    return ema

def scalp_plan(ex, free_bal, send_telegram, can_send):
    try:
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50)
        c30=ex.fetch_ohlcv(SYMBOL,'30m',limit=20)
        c4h=ex.fetch_ohlcv(SYMBOL,'4h',limit=120) # 120*4h = 20 days, enough for wicks
        cl5=[x[4] for x in c5]
        cl4h=[x[4] for x in c4h]
        if len(c4h)<30: return "WAIT loading candles"
        price=cl5[-1]
        rsi=calc_rsi(cl5)
        rsi_4h=calc_rsi(cl4h)
        ema20_4h=calc_ema(cl4h,20)

        ch5=(c5[-1][4]-c5[-2][4])/c5[-2][4]*100 if c5[-2][4]>0 else 0
        va=sum([x[5] for x in c5[-21:-1]])/20 if len(c5)>21 else c5[-1][5]
        vr=c5[-1][5]/(va+0.001)

        wick_low=c5[-1][3]
        wick_high=c5[-1][2]

        # === AUTO WICK RANGE - from last low wicks, last high wicks ===
        lows_90=sorted([x[3] for x in c4h]) # all low wicks
        highs_90=sorted([x[2] for x in c4h]) # all high wicks
        # bottom 15% median = real floor
        bn=int(len(lows_90)*0.15) or 1
        tn=int(len(highs_90)*0.15) or 1
        RANGE_LOW=sum(lows_90[:bn])/bn
        RANGE_HIGH=sum(highs_90[-tn:])/tn
        # Ignore outlier I pump >35% above median
        median_high = highs_90[int(len(highs_90)*0.5)]
        if RANGE_HIGH > median_high*1.35:
            RANGE_HIGH = sum(highs_90[-tn*2:-tn])/tn # take second top
        MID=(RANGE_LOW+RANGE_HIGH)/2

        # safety clamp for MEXC KOMA now
        if RANGE_LOW<0.005: RANGE_LOW=0.0115
        if RANGE_HIGH>0.04: RANGE_HIGH=0.020
        MID=(RANGE_LOW+RANGE_HIGH)/2

        # === POS ===
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

        # === PUMP PAUSE - don't trade breakout I ===
        if price > PUMP_PAUSE and pos_side=='short':
            return f"⏸️ PAUSE SHORT BREAKOUT I price {price:.5f} > {PUMP_PAUSE} - wait new house"
        if price < RANGE_LOW*0.6:
            return f"⏸️ PAUSE LONG BREAKDOWN price {price:.5f} < floor*0.6 - wait new house"

        # === HOLD + TP MID + ADD ===
        if pos_side and entry>0:
            pct = (price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            pnl_pct = pct * LEVERAGE

            # TP to MID - catches every trade
            if pos_side=='long' and price >= MID*0.995:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                m=f"✅ TP MID LONG {RANGE_LOW:.5f}->{MID:.5f} +{pct:.1f}% PnL {pnl_pct:.1f}% @{price:.5f}"; send_telegram(m); return m
            if pos_side=='short' and price <= MID*1.005:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                m=f"✅ TP MID SHORT {RANGE_HIGH:.5f}->{MID:.5f} +{pct:.1f}% PnL {pnl_pct:.1f}% @{price:.5f}"; send_telegram(m); return m

            # ADD to catch every wick - double bottom/top
            if pos_side=='long' and wick_low <= RANGE_LOW*1.05 and vr>1.2 and rsi<40:
                set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.7))
                m=f"➕ ADD LONG double bottom floor {RANGE_LOW:.5f} wick {wick_low:.5f} RSI {rsi:.0f}"; send_telegram(m); return m
            if pos_side=='short' and wick_high >= RANGE_HIGH*0.95 and vr>1.2 and rsi>60:
                set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.7))
                m=f"➕ ADD SHORT double top roof {RANGE_HIGH:.5f} wick {wick_high:.5f} RSI {rsi:.0f}"; send_telegram(m); return m

            # SL
            if pct <= -SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 STRUCTURE SL {pos_side.upper()} {pct:.1f}% ({pnl_pct:.1f}%) floor {RANGE_LOW:.5f} roof {RANGE_HIGH:.5f} @{price:.5f}"; send_telegram(m); return m

            return f"HOLD {pos_side.upper()} {pct:.1f}% -> MID {MID:.5f} range {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} RSI {rsi:.0f} 4H {rsi_4h:.0f} VOL {vr:.1f}x"

        # === ENTRY - CATCH EVERY WICK TIER 1 ===
        if wick_low <= RANGE_LOW*1.12:
            set_iso(); ex.create_market_order(SYMBOL,'buy',get_qty(0.6)) # 24% balance = catches every
            m=f"🟢 EVERY WICK BUY FLOOR {RANGE_LOW:.5f} wick {wick_low:.5f} -> TP MID {MID:.5f} 5m {ch5:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price:.5f}"; send_telegram(m); return m

        if wick_high >= RANGE_HIGH*0.88:
            set_iso(); ex.create_market_order(SYMBOL,'sell',get_qty(0.6))
            m=f"🔴 EVERY WICK SELL ROOF {RANGE_HIGH:.5f} wick {wick_high:.5f} -> TP MID {MID:.5f} 5m {ch5:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price:.5f}"; send_telegram(m); return m

        # === REVERSE ON 4H ===
        last_4h=c4h[-2]
        is_bull_4h = last_4h[4] > ema20_4h and last_4h[4] > last_4h[1]
        is_bear_4h = last_4h[4] < ema20_4h and last_4h[4] < last_4h[1]

        return f"WAIT MEXC HOUSE {RANGE_LOW:.5f}-{RANGE_HIGH:.5f} MID {MID:.5f} price {price:.5f} RSI {rsi:.0f} 4H {rsi_4h:.0f} VOL {vr:.1f}x 4H {'BULL' if is_bull_4h else 'BEAR' if is_bear_4h else 'SIDE'}"
    except Exception as e:
        return f"ERR beast {e}"
