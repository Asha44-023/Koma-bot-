import os, time
from datetime import datetime

SYM = "KOMA/USDT:USDT"
# === NEW SLEEP LOGIC ===
TP = 8.0 # 8% not 3.5% - KOMA needs room
SL = 5.0
VOL_ENTRY = 1.5
VOL_FLIP = 1.8
MOM_ENTRY = 0.8
MOM_FLIP = 1.0

# 10% OVERRIDE
PUMP_1H = 10.0
DUMP_1H = -10.0
MAX_HOLD_MIN = 240 # 4 hours max - no 3 day bag

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
        if now.day!= 1: return ""
        lines = open(TRADES_FILE).readlines()[-100:]
        total = len(lines)
        prof = sum(float(l.split(",")[1]) for l in lines if "," in l)
        msg = f"📊 KOMA MONTHLY REPORT {now.strftime('%B %Y')}\nTrades: {total}\nTotal PNL: {prof:.2f}%\nBalance Growth: Auto-compounding ON\nNext Target: $60K"
        send_tg(msg)
        return msg
    except: return ""

def scalp_plan(exchange, free_balance, send_tg, can_send):
    try:
        _monthly_report(send_tg)

        ohlcv = exchange.fetch_ohlcv(SYM, '5m', limit=30)
        closes = [c[4] for c in ohlcv]
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        vols = [c[5] for c in ohlcv]

        # === 1H FOR 10% PUMP ===
        ohlcv_1h = exchange.fetch_ohlcv(SYM, '1h', limit=5)
        price_1h_ago = ohlcv_1h[-2][4] if len(ohlcv_1h)>=2 else closes[-2]

        price = closes[-1]
        change_1h = ((price - price_1h_ago) / price_1h_ago * 100) if price_1h_ago else 0

        mom5 = (closes[-1]/closes[-2]-1)*100 if closes[-2]!=0 else 0
        mom15 = (closes[-1]/closes[-4]-1)*100 if len(closes)>4 else 0
        avg_vol = sum(vols[-6:-1])/5 if sum(vols[-6:-1])>0 else 1
        volx = vols[-1] / avg_vol if avg_vol>0 else 0

        wick_up = (highs[-1] - max(closes[-1], ohlcv[-1][1])) / price * 100
        wick_down = (min(closes[-1], ohlcv[-1][1]) - lows[-1]) / price * 100
        liquidity_grab_up = wick_up > 0.6 and mom5 < 0
        liquidity_grab_down = wick_down > 0.6 and mom5 > 0

        gains = sum(max(0, closes[i]-closes[i-1]) for i in range(1, len(closes)))
        losses = sum(max(0, closes[i-1]-closes[i]) for i in range(1, len(closes)))
        rsi = 100 - (100/(1+gains/(losses+0.00001))) if losses!=0 else 50

        positions = exchange.fetch_positions([SYM])
        pos = next((p for p in positions if float(p.get('contracts',0) or p.get('info',{}).get('holdVol',0) or 0)!=0), None)
        side = pos['side'] if pos else None
        contracts = float(pos['contracts'] or pos['info'].get('holdVol',0) or 0) if pos else 0
        entry = float(pos['entryPrice'] or pos['info'].get('openPrice',0) or 0) if pos else price
        # check hold time
        hold_minutes = 0
        if pos:
            try:
                open_time = pos['info'].get('openTime') or pos['info'].get('createTime') or 0
                if open_time:
                    hold_minutes = (time.time()*1000 - float(open_time)) / 60000
            except: hold_minutes = 0

        # === COMPOUND LOGIC FOR $10 -> $60K ===
        free = float(free_balance)
        if free < 100:
            pct = 0.40 # $10 account - 40% to grow fast
        elif free < 1000:
            pct = 0.30 # $100-$1000 - 30%
        else:
            pct = 0.23 # $1000+ - 23% safe
        notional = round(free * pct, 2)
        if notional < 3.0: notional = 3.0
        if notional > free*0.9: notional = round(free*0.9,2)
        amount = notional / price

        # === 1. TIME STOP - NO 3 DAY BAG - SLEEP SAFE ===
        if side and hold_minutes > MAX_HOLD_MIN:
            try:
                exchange.create_market_order(SYM, 'sell' if side=='long' else 'buy', contracts)
                pnl = ((price-entry)/entry*100) * (1 if side=='long' else -1)
                _log_trade(pnl)
                send_tg(f"⏰ TIME STOP 4H KOMA {side.upper()} PNL {pnl:.2f}% @ {price:.5f} - Avoid 3 day bag while sleeping")
                return f"TIME STOP {pnl:.2f}%"
            except Exception as e:
                return f"TIME STOP err {e}"

        # === 2. FLIP LOGIC ===
        if side == 'long':
            if mom5 <= -MOM_FLIP and volx >= VOL_FLIP or liquidity_grab_up or change_1h >= PUMP_1H:
                try:
                    exchange.set_leverage(5, SYM)
                    exchange.create_market_order(SYM, 'sell', contracts)
                    exchange.create_market_order(SYM, 'sell', amount)
                    pnl_flip = (price-entry)/entry*100
                    _log_trade(pnl_flip)
                    msg = f"🔄 FLIP LONG→SHORT KOMA 10%\n1H {change_1h:.2f}% Price {price:.5f} PNL {pnl_flip:.2f}%\nMOM{mom5:.1f}% VOLx{volx:.1f}"
                    send_tg(f"🤖 {msg}")
                    return msg
                except: pass
        if side == 'short':
            if mom5 >= MOM_FLIP and volx >= VOL_FLIP or liquidity_grab_down or change_1h <= DUMP_1H:
                try:
                    exchange.set_leverage(5, SYM)
                    exchange.create_market_order(SYM, 'buy', contracts)
                    exchange.create_market_order(SYM, 'buy', amount)
                    pnl_flip = (entry-price)/entry*100
                    _log_trade(pnl_flip)
                    msg = f"🔄 FLIP SHORT→LONG KOMA 10%\n1H {change_1h:.2f}% Price {price:.5f} PNL {pnl_flip:.2f}%"
                    send_tg(f"🤖 {msg}")
                    return msg

        # === 3. EXIT TP 8% SL 5% ===
        if side:
            pnl = ((price-entry)/entry*100) * (1 if side=='long' else -1)
            if pnl >= TP or pnl <= -SL:
                try:
                    exchange.create_market_order(SYM, 'sell' if side=='long' else 'buy', contracts)
                    _log_trade(pnl)
                    send_tg(f"💰 CLOSE KOMA {side.upper()} PNL {pnl:.2f}% @ {price:.5f} 1H:{change_1h:.1f}% | Bal ${free:.2f} → Next ${free*(1+pnl/100*0.4):.2f}")
                    return f"CLOSE {pnl:.2f}%"
                except Exception as e:
                    return f"CLOSE err {e}"

        # === 4. ENTRY - 10% OVERRIDE WINS ===
        if not side:
            # 10% pump -> SHORT immediately, 10% dump -> LONG
            if change_1h >= PUMP_1H:
                if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                    exchange.set_leverage(5, SYM)
                    exchange.create_market_order(SYM, 'sell', amount)
                    send_tg(f"🔴 AUTO SHORT KOMA 10% PUMP\n1H {change_1h:.2f}% @ {price:.5f} Size ${notional}\nTP {TP}% SL {SL}% Flip ON - Sleeping scalp")
                return f"SHORT PUMP {change_1h:.2f}%"
            if change_1h <= DUMP_1H:
                if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                    exchange.set_leverage(5, SYM)
                    exchange.create_market_order(SYM, 'buy', amount)
                    send_tg(f"🟢 AUTO LONG KOMA 10% DUMP\n1H {change_1h:.2f}% @ {price:.5f} Size ${notional}\nTP {TP}% SL {SL}%")
                return f"LONG DUMP {change_1h:.2f}%"

            whale = volx >= VOL_ENTRY
            small_move = abs(mom5) >= MOM_ENTRY
            if whale and small_move and 25 < rsi < 75:
                if mom5 >= MOM_ENTRY or liquidity_grab_down:
                    if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                        exchange.set_leverage(5, SYM)
                        exchange.create_market_order(SYM, 'buy', amount)
                        send_tg(f"🟢 AUTO LONG KOMA @ {price:.5f}\nMOM{mom5:.1f}% VOLx{volx:.1f} RSI{int(rsi)} 1H{change_1h:.1f}%\nTP {TP}% SL {SL}% Size ${notional}")
                    return f"LONG VOLx{volx:.1f} MOM{mom5:.1f}%"
                if mom5 <= -MOM_ENTRY or liquidity_grab_up:
                    if os.getenv("AUTOPILOT_ENABLED","true")=="true":
                        exchange.set_leverage(5, SYM)
                        exchange.create_market_order(SYM, 'sell', amount)
                        send_tg(f"🔴 AUTO SHORT KOMA @ {price:.5f}\nMOM{mom5:.1f}% VOLx{volx:.1f} RSI{int(rsi)} 1H{change_1h:.1f}%\nTP {TP}% SL {SL}% Size ${notional}")
                    return f"SHORT VOLx{volx:.1f} MOM{mom5:.1f}%"

        return f"⚪ WAIT KOMA @ {price:.5f} 1H:{change_1h:.2f}% VOLx{volx:.1f} MOM{mom5:.1f}% RSI{int(rsi)}"
    except Exception as e:
        return f"KOMA BEAST ERROR {e}"
