import ccxt
SYMBOL="KOMA/USDT:USDT"; LEVERAGE=10; SIZE_PCT=0.5; VOL_MULT=1.4
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
        va=sum([x[5] for x in c5[-11:-1]])/10; vn=c5[-1][5]; vp=c5[-2][5]
        vr=vn/(va+0.001); spike=vn>va*VOL_MULT and vn>vp
        rsi=calc_rsi(cl5); vwap=sum([c5[i][4]*c5[i][5] for i in range(-20,0)])/sum([c5[i][5] for i in range(-20,0)])
        pos_side=None; amt=0
        for p in ex.fetch_positions([SYMBOL]):
            c=float(p.get('contracts',0) or p.get('info',{}).get('holdVol',0) or 0)
            if abs(c)>0:
                pos_side=(p.get('side') or '').lower()
                if 'long' in str(p).lower() and not pos_side: pos_side='long'
                if 'short' in str(p).lower() and not pos_side: pos_side='short'
                amt=abs(c); break
        if pos_side=='long' and price<vwap and rsi>60 and spike:
            ex.create_market_order(SYMBOL,'sell',amt,params={"reduceOnly":True})
            m=f"🔄 CLOSED LONG -> READY SHORT VOL {vr:.1f}x RSI {rsi:.0f} @{price}"; send_telegram(m); return m
        if pos_side=='short' and price>vwap and rsi<40 and spike:
            ex.create_market_order(SYMBOL,'buy',amt,params={"reduceOnly":True})
            m=f"🔄 CLOSED SHORT -> READY LONG VOL {vr:.1f}x RSI {rsi:.0f} @{price}"; send_telegram(m); return m
        if pos_side: return f"HOLD {pos_side.upper()} 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x"
        try: bal=float(free_bal)
        except: bal=12.91
        notional=bal*SIZE_PCT
        if notional<3: notional=3
        qty=notional*LEVERAGE/price
        qty=float(ex.amount_to_precision(SYMBOL,qty))
        if ch30>=6 and ch5>=1.2 and rsi>=62 and spike and price<vwap:
            try: ex.set_leverage(LEVERAGE,SYMBOL); ex.set_margin_mode('isolated',SYMBOL)
            except: pass
            ex.create_market_order(SYMBOL,'sell',qty)
            m=f"🔴 FAST SAFE SHORT 50% 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price}"; send_telegram(m); return m
        if ch30<=-6 and ch5>=0.8 and rsi<=42 and spike and price>vwap:
            try: ex.set_leverage(LEVERAGE,SYMBOL); ex.set_margin_mode('isolated',SYMBOL)
            except: pass
            ex.create_market_order(SYMBOL,'buy',qty)
            m=f"🟢 FAST SAFE LONG 50% 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x @{price}"; send_telegram(m); return m
        return f"WAIT 5m {ch5:.1f}% 30m {ch30:.1f}% RSI {rsi:.0f} VOL {vr:.1f}x {'ABOVE' if price>vwap else 'BELOW'} VWAP"
    except Exception as e:
        return f"ERR beast {e}"
