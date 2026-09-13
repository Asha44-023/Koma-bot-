import ccxt
SYMBOL="KOMA/USDT:USDT"; LEVERAGE=10; SIZE_PCT=0.5; VOL_MULT=1.4
TP_PCT=3.0; SL_PCT=2.5

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
        c5=ex.fetch_ohlcv(SYMBOL,'5m',limit=50); c30=ex.fetch_ohlcv(SYMBOL,'30m',limit=20)
        cl5=[x[4] for x in c5]; price=cl5[-1]
        ch5=(c5[-1][4]-c5[-2][4])/c5[-2][4]*100
        ch30=(c30[-1][4]-c30[-6][4])/c30[-6][4]*100 if len(c30)>=6 else 0
        va=sum([x[5] for x in c5[-21:-1]])/20; vn=c5[-1][5]; vp=c5[-2][5]
        vr=vn/(va+0.001)
        # FIXED: KOMA PUMP OVERRIDE - if 30m pumps >1.5%, trade even if VOL low
        pump_override = abs(ch30) >= 1.5
        spike = (vn>va*VOL_MULT and vn>vp) or pump_override
        rsi=calc_rsi(cl5); vwap=sum([c5[i][4]*c5[i][5] for i in range(-20,0)])/sum([c5[i][5] for i in range(-20,0)])

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

        if pos_side and entry>0:
            pnl_pct = (price-entry)/entry*100*LEVERAGE if pos_side=='long' else (entry-price)/entry*100*LEVERAGE
            price_pct = (price-entry)/entry*100 if pos_side=='long' else (entry-price)/entry*100
            if price_pct >= TP_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"✅ TP HIT {pos_side.upper()} +{price_pct:.1f}% (+{pnl_pct:.1f}% BAL) @{price}"; send_telegram(m); return m
            if price_pct <= -SL_PCT:
                ex.create_market_order(SYMBOL,'sell' if pos_side=='long' else 'buy',amt,params={"reduceOnly":True})
                m=f"🛑 SL HIT {pos_side.upper()} {price_pct:.1f}% @{price}"; send_telegram(m); return m
            if pos_side=='long' and price<vwap and rsi>60 and spike:
                ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
                m=f"🔄 FLIP LONG->SHORT VOL {vr:.1f}x RSI {rsi:.0f} @{price}"; send_telegram(m); return m
            if pos_side=='short' and price>vwap and rsi<40 and spike:
                ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
                m=f"🔄 FLIP SHORT->LONG VOL {vr:.1f}x RSI {rsi:.0f} @{price}"; send_telegram(m); return m
            return f"HOLD {pos_side.upper()} {price_pct:.1f}%/TP{TP_PCT}% RSI {rsi:.0f} VOL {vr:.1f}x"

        try: bal=float(free_bal)
        except: bal=10.0
        notional=bal*SIZE_PCT
        if notional<3: notional=3
        qty=notional*LEVERAGE/price
        qty=float(ex.amount_to_precision(SYMBOL,qty))

        if ch30>=3 and ch5>=-0.5 and rsi>=58 and spike and price>vwap*1.01:
            try: ex.set_leverage(LEVERAGE,SYMBOL); ex.set_margin_mode('isolated',SYMBOL)
            except: pass
            ex.create_market_order(SYMBOL,'sell',qty)
            m=f"🔴 EXCH SHORT 50% 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price} TP+{TP_PCT}% SL-{SL_PCT}%"; send_telegram(m); return m

        if ch30<=-3 and ch5>=-1 and rsi<=42 and spike and price<vwap*0.99:
            try: ex.set_leverage(LEVERAGE,SYMBOL); ex.set_margin_mode('isolated',SYMBOL)
            except: pass
            ex.create_market_order(SYMBOL,'buy',qty)
            m=f"🟢 EXCH LONG 50% 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price} TP+{TP_PCT}% SL-{SL_PCT}%"; send_telegram(m); return m

        return f"WAIT 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x {'ABOVE' if price>vwap else 'BELOW'} VWAP"
    except Exception as e:
        return f"ERR beast {e}"
