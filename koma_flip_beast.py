import ccxt
SYMBOL="KOMA/USDT:USDT"; LEVERAGE=10; SIZE_PCT=0.9
TP_PCT=999 # DISABLED for KOMA cycle - beyond 0.012 / beyond wick
SL_PCT=8.0 # Structure SL - not 2.5% trap

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
        c4h=ex.fetch_ohlcv(SYMBOL,'4h',limit=50)
        cl5=[x[4] for x in c5]
        cl4h=[x[4] for x in c4h]
        price=cl5[-1]
        ch5=(c5[-1][4]-c5[-2][4])/c5[-2][4]*100
        ch30=(c30[-1][4]-c30[-6][4])/c30[-6][4]*100 if len(c30)>=6 else ch5*6
        va=sum([x[5] for x in c5[-21:-1]])/20
        vr=c5[-1][5]/(va+0.001)
        rsi=calc_rsi(cl5)

        # 4H data for reverse
        rsi_4h = calc_rsi(cl4h)
        ema20_4h = calc_ema(cl4h, 20)
        vol4h_avg = sum([x[5] for x in c4h[-21:-1]])/20 if len(c4h)>21 else c4h[-1][5]
        vol4h_now = c4h[-2][5]
        last_4h = c4h[-2]

        pos_side=None; amt=0; entry=0
        for p in ex.fetch_positions([SYMBOL]):
            c=float(p.get('contracts',0) or p.get('info',{}).get('holdVol',0) or 0)
            if abs(c)>0:
                pos_side=(p.get('side') or '').lower()
                if 'long' in str(p).lower() and not pos_side: pos_side='long'
                if 'short' in str(p).lower() and not pos_side: pos_side='short'
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

        def get_qty():
            try: bal=float(free_bal)
            except: bal=10.0
            notional=bal*SIZE_PCT
            if notional<3: notional=3
            if notional>bal*0.9: notional=bal*0.9
            q=notional/price
            return float(ex.amount_to_precision(SYMBOL,q))

        if pos_side and entry>0:
            price_pct = (price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            pnl_pct = price_pct * LEVERAGE

            # === REVERSE TP - SHORT -> LONG when long opportunity ===
            if pos_side == 'short':
                is_bullish_4h = last_4h[4] > ema20_4h and last_4h[4] > last_4h[1]
                if is_bullish_4h and rsi_4h > 60 and vol4h_now > vol4h_avg*1.1:
                    ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                    set_iso()
                    ex.create_market_order(SYMBOL,'buy',get_qty())
                    m=f"🔄 REVERSE TP SHORT->LONG 4H CONFIRMED +{price_pct:.1f}% RSI4H {rsi_4h:.0f} beyond wick @{price}"; send_telegram(m); return m
                # HOLD through London traps (your last log: VOLUP x2.1)
                if price_pct > -SL_PCT:
                    return f"🔴 HOLD SHORT PROFIT {price_pct:.1f}%/TP BEYOND 0.012 RSI {rsi:.0f} 4H_RSI {rsi_4h:.0f} VOL {vr:.1f}x HOLD TO BEYOND"

            # === REVERSE TP - LONG -> SHORT ===
            if pos_side == 'long':
                is_bearish_4h = last_4h[4] < ema20_4h and last_4h[4] < last_4h[1]
                if is_bearish_4h and rsi_4h < 40 and vol4h_now > vol4h_avg*1.1:
                    ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                    set_iso()
                    ex.create_market_order(SYMBOL,'sell',get_qty())
                    m=f"🔄 REVERSE TP LONG->SHORT 4H CONFIRMED +{price_pct:.1f}% RSI4H {rsi_4h:.0f} beyond 0.012 @{price}"; send_telegram(m); return m

            if price_pct <= -SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 STRUCTURE SL {pos_side.upper()} {price_pct:.1f}% (+{pnl_pct:.1f}% PnL) @{price} 8% max"; send_telegram(m); return m

            return f"HOLD {pos_side.upper()} {price_pct:.1f}%/BEYOND RSI {rsi:.0f} 4H {rsi_4h:.0f} VOL {vr:.1f}x"

        # ENTRY
        if ch5 <= -0.8 or ch30 <= -0.8:
            set_iso()
            ex.create_market_order(SYMBOL,'sell',get_qty())
            m=f"🔴 AUTO KOMA SELL ISOLATED 10x 5m {ch5:.2f}% 30m {ch30:.2f}% RSI {rsi:.0f} 4H_RSI {rsi_4h:.0f} VOL {vr:.1f}x @{price}"; send_telegram(m); return m

        if ch5 >= 0.8 or ch30 >= 0.8:
            set_iso()
            ex.create_market_order(SYMBOL,'buy',get_qty())
            m=f"🟢 AUTO KOMA BUY ISOLATED 10x 5m {ch5:.2f}% 30m {ch30:.2f}% RSI {rsi:.0f} 4H_RSI {rsi_4h:.0f} VOL {vr:.1f}x @{price}"; send_telegram(m); return m

        return f"WAIT 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} 4H {rsi_4h:.0f} VOL {vr:.1f}x"
    except Exception as e:
        return f"ERR beast {e}"
