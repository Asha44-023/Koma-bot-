import os, time, ccxt
from datetime import datetime

SYMBOL = "KOMA/USDT"
LEVERAGE = 10
SIZE_PCT = 0.5 # 50% balance
VOL_MULT = 1.4

API_KEY = os.getenv("MEXC_API_KEY")
SECRET = os.getenv("MEXC_SECRET")

def get_ex():
    ex = ccxt.mexc({
        'apiKey': API_KEY,
        'secret': SECRET,
        'options': {'defaultType': 'swap'}
    })
    ex.set_leverage(LEVERAGE, SYMBOL)
    return ex

def get_candles(ex, tf, limit=50):
    return ex.fetch_ohlcv(SYMBOL, tf, limit=limit)

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains = losses = 0
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 80
    rs = gains / losses
    return 100 - (100 / (1+rs))

def scalp_plan():
    try:
        ex = get_ex()
        c5 = get_candles(ex, '5m', 50)
        c30 = get_candles(ex, '30m', 20)

        close5 = [x[4] for x in c5]
        price = close5[-1]

        chg_5 = (c5[-1][4] - c5[-2][4]) / c5[-2][4] * 100
        chg_30 = (c30[-1][4] - c30[-6][4]) / c30[-6][4] * 100 if len(c30)>=6 else 0

        vol_avg = sum([x[5] for x in c5[-11:-1]]) / 10
        vol_now = c5[-1][5]
        vol_prev = c5[-2][5]
        vol_ratio = vol_now / (vol_avg+0.0001)

        vol_spike = vol_now > vol_avg * VOL_MULT and vol_now > vol_prev
        vol_drop = vol_now < vol_prev * 0.9

        rsi = calc_rsi(close5)
        vwap = sum([c5[i][4]*c5[i][5] for i in range(-20,0)]) / sum([c5[i][5] for i in range(-20,0)])

        balance = ex.fetch_balance()['USDT']['free']
        amount = (balance * SIZE_PCT * LEVERAGE) / price
        amount = float(ex.amount_to_precision(SYMBOL, amount))

        positions = ex.fetch_positions([SYMBOL])
        pos_side = None
        for p in positions:
            if float(p['contracts']) > 0:
                pos_side = p['side']
                break

        # --- AUTO CLOSE ON FLIP ---
        if pos_side == 'long' and price < vwap and rsi > 60 and vol_spike:
            ex.create_market_order(SYMBOL, 'sell', float(pos_side and amount), params={'reduceOnly': True})
            return f"CLOSED LONG -> FLIP SHORT SIGNAL VOL {vol_ratio:.1f}x RSI {rsi:.0f} @{price}"

        if pos_side == 'short' and price > vwap and rsi < 40 and vol_spike:
            ex.create_market_order(SYMBOL, 'buy', float(pos_side and amount), params={'reduceOnly': True})
            return f"CLOSED SHORT -> FLIP LONG SIGNAL VOL {vol_ratio:.1f}x RSI {rsi:.0f} @{price}"

        if pos_side:
            return f"HOLD {pos_side.upper()} 5m {chg_5:.1f}% 30m {chg_30:.1f}% RSI {rsi:.0f} VOL {vol_ratio:.1f}x"

        # --- ENTRY BOTH WAYS ---
        # SHORT: Pump + volume spike up
        if chg_30 >= 6 and chg_5 >= 1.2 and rsi >= 62 and vol_spike and price < vwap:
            ex.create_market_order(SYMBOL, 'sell', amount)
            # TP 2% SL 1.5%
            tp = price * 0.98
            sl = price * 1.015
            ex.create_order(SYMBOL, 'limit', 'buy', amount, tp, params={'reduceOnly': True})
            ex.create_order(SYMBOL, 'stop', 'buy', amount, sl, params={'reduceOnly': True, 'stopPrice': sl})
            return f"FAST SAFE SHORT 50% 5m {chg_5:.1f}% 30m {chg_30:.1f}% RSI {rsi:.0f} VOL {vol_ratio:.1f}x @{price} TP {tp} SL {sl}"

        # LONG: Dump + volume dry then spike
        if chg_30 <= -6 and chg_5 >= 0.8 and rsi <= 42 and vol_spike and price > vwap:
            ex.create_market_order(SYMBOL, 'buy', amount)
            tp = price * 1.02
            sl = price * 0.985
            ex.create_order(SYMBOL, 'limit', 'sell', amount, tp, params={'reduceOnly': True})
            ex.create_order(SYMBOL, 'stop', 'sell', amount, sl, params={'reduceOnly': True, 'stopPrice': sl})
            return f"FAST SAFE LONG 50% 5m {chg_5:.1f}% 30m {chg_30:.1f}% RSI {rsi:.0f} VOL {vol_ratio:.1f}x @{price} TP {tp} SL {sl}"

        return f"WAIT 5m {chg_5:.1f}% 30m {chg_30:.1f}% RSI {rsi:.0f} VOL {vol_ratio:.1f}x VWAP {'ABOVE' if price>vwap else 'BELOW'}"

    except Exception as e:
        return f"ERR {e}"

# For GitHub Actions loop
if __name__ == "__main__":
    while True:
        print(datetime.utcnow(), scalp_plan())
        time.sleep(60)
