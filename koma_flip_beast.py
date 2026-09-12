import os, time
from datetime import datetime

SYM = "KOMA/USDT:USDT"
TP = 3.5
SL = 2.2
VOL_ENTRY = 1.5 # lowered to catch small moves
VOL_FLIP = 1.8
MOM_ENTRY = 0.8 # catch 0.8% start of 10%
MOM_FLIP = 1.0

# For monthly report
TRADES_FILE = "/tmp/koma_trades.log"

def _log_trade(pnl):
    try:
        with open(TRADES_FILE, "a") as f:
            f.write(f"{datetime.utcnow().isoformat()},{pnl}\n")
    except: pass

def _monthly_report(send_tg):
    try:
        if not os.path.exists(TRADES_FILE): return ""
        now = datetime.utcnow()
        if now.day!= 1: return "" # only 1st of month
        lines = open(TRADES_FILE).readlines()[-100:]
        total = len(lines)
        prof = sum(float(l.split(",")[1]) for l in lines if "," in l)
        msg = f"📊 KOMA MONTHLY REPORT {now.strftime('%B %Y')}\nTrades: {total}\nTotal PNL: {prof:.2f}%\nBalance Growth: Auto-compounding ON\nNext Target: $60K"
        send_tg(msg)
        return msg
    except Exception as e:
        return ""

def scalp_plan(exchange, free_balance, send_tg, can_send):
    try:
        # --- MONTHLY CHECK ---
        _monthly_report(send_tg)

        ohlcv = exchange.fetch_ohlcv(SYM, '5m', limit=30)
        closes = [c[4] for c in ohlcv]
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        vols = [c[5] for c in ohlcv]

        price = closes[-1]
        mom5 = (closes[-1]/closes[-2]-1)*100 if closes[-2]!=0 else 0
        mom15 = (closes[-1]/closes[-4]-1)*100 if len(closes)>4 else 0
        avg_vol = sum(vols[-6:-1])/5 if sum(vols[-6:-1])>0 else 1
        volx = vols[-1] / avg_vol if avg_vol>0 else 0

        # Liquidity grab + whale detection
        wick_up = (highs[-1] - max(closes[-1], ohlcv[-1][1])) / price * 100
        wick_down = (min(closes[-1], ohlcv[-1][1]) - lows[-1]) / price * 100
        liquidity_grab_up = wick_up > 0.6 and mom5 < 0 # fake pump then dump
        liquidity_grab_down = wick_down > 0.6 and mom5 > 0 # fake dump then pump

        gains = sum(max(0, closes[i]-closes[i-1]) for i in range(1, len(closes)))
        losses = sum(max(0, closes[i-1]-closes[i]) for i in range(1, len(closes)))
        rsi = 100 - (100/(1+gains/(losses+0.00001))) if losses!=0 else 50

        positions = exchange.fetch_positions([SYM])
        pos = next((p for p in positions if float(p.get('contracts',0) or 0)!=0), None)
        side = pos['side'] if pos else None
        contracts = float(pos['contracts']) if pos else 0
        entry = float(pos['entryPrice']) if pos else price

        # COMPOUND to $60K: 23% of balance, grows as balance grows
        free = float(free_balance)
        notional = round(free * 0.23, 2)
        if notional < 2.5: notional = 2.5
        if notional > free*0.9: notional = free*0.9
        amount = notional / price

        # --- FLIP LOGIC BUY <-> SELL ---
        if side == 'long':
            if mom5 <= -MOM_FLIP and volx >= VOL_FLIP or liquidity_grab_up:
                exchange.set_leverage(5, SYM)
                exchange.create_market_order(SYM, 'sell', contracts)
                exchange.create_market_order(SYM, 'sell', amount)
                pnl_flip = (price-entry)/entry*100
                _log_trade(pnl_flip)
                msg = f"🔄 FLIP LONG→SHORT KOMA\nPrice {price:.5f} PNL {pnl_flip:.2f}%\nMOM{mom5:.1f}% VOLx{volx:.1f} Grab:{liquidity_grab_up}\n→ Now SHORT TP{TP}% SL{SL}%"
                send_tg(f"🤖 {msg}")
                return msg
        if side == 'short':
            if mom5 >= MOM_FLIP and volx >= VOL_FLIP or liquidity_grab_down:
                exchange.set_leverage(5, SYM)
                exchange.create_market_order(SYM, 'buy', contracts)
                exchange.create_market_order(SYM, 'buy', amount)
                pnl_flip = (entry-price)/entry*100
                _log_trade(pnl_flip)
                msg = f"🔄 FLIP SHORT→LONG KOMA\nPrice {price:.5f} PNL {pnl_flip:.2f}%\nMOM{mom5:.1f}% VOLx{volx:.1f} Grab:{liquidity_grab_down}\n→ Now LONG TP{TP}% SL{SL}%"
                send_tg(f"🤖 {msg}")
                return msg

        # --- EXIT TP/SL + TIME STOP ---
        if side:
            pnl = ((price-entry)/entry*100) * (1 if side=='long' else -1)
            # Trailing: lock profit
            if pnl >= TP or pnl <= -SL:
                exchange.create_market_order(SYM, 'sell' if side=='long' else 'buy', contracts)
                _log_trade(pnl)
                send_tg(f"💰 CLOSE KOMA {side.upper()} PNL {pnl:.2f}% @ {price:.5f} | Balance ${free:.2f} → Next ${free*1.03:.2f}")
                return f"💰 CLOSE KOMA {side} {pnl:.2f}% @ {price:.5f}"

        # --- ENTRY - SHARP EDGE SMALL MOVES ---
        if not side:
            whale = volx >= VOL_ENTRY
            small_move = abs(mom5) >= MOM_ENTRY
            if whale and small_move and 25 < rsi < 75:
                if mom5 >= MOM_ENTRY or liquidity_grab_down:
                    if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                        exchange.set_leverage(5, SYM)
                        exchange.create_market_order(SYM, 'buy', amount)
                        send_tg(f"🟢 AUTO LONG KOMA @ {price:.5f}\nMOM{mom5:.1f}% VOLx{volx:.1f} RSI{int(rsi)} MOM15 {mom15:.1f}%\nTP {TP}% SL {SL}% Size ${notional} | Flip ON")
                    return f"🟢 SCALP LONG KOMA @ {price:.5f} VOLx{volx:.1f} MOM{mom5:.1f}% RSI{int(rsi)} Grab {liquidity_grab_down}\n → AUTO LONG TP{TP}% SL{SL}%"
                if mom5 <= -MOM_ENTRY or liquidity_grab_up:
                    if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                        exchange.set_leverage(5, SYM)
                        exchange.create_market_order(SYM, 'sell', amount)
                        send_tg(f"🔴 AUTO SHORT KOMA @ {price:.5f}\nMOM{mom5:.1f}% VOLx{volx:.1f} RSI{int(rsi)} MOM15 {mom15:.1f}%\nTP {TP}% SL{SL}% Size ${notional} | Flip ON")
                    return f"🔴 SCALP SHORT KOMA @ {price:.5f} VOLx{volx:.1f} MOM{mom5:.1f}% RSI{int(rsi)} Grab {liquidity_grab_up}\n → AUTO SHORT TP{TP}% SL{SL}%"

        return f"⚪ WAIT KOMA @ {price:.5f} VOLx{volx:.1f} MOM{mom5:.1f}% RSI{int(rsi)} | Need VOLx{VOL_ENTRY} MOM{MOM_ENTRY}%"
    except Exception as e:
        return f"KOMA BEAST ERROR {e}"
