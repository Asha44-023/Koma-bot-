import ccxt
import os

MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET")

SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT"]
MEXC_MAP = {"KOMA/USDT:USDT": "KOMA_USDT", "GRASS/USDT:USDT": "GRASS_USDT"}

ex = ccxt.mexc({
    "apiKey": MEXC_API_KEY,
    "secret": MEXC_API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

def get_balance_usdt():
    try:
        bal = ex.fetch_balance()
        usdt = bal.get("USDT", {})
        free = usdt.get("free", 0) or usdt.get("total", 0) or 0
        return float(free)
    except Exception as e:
        print(f"Balance err {e}")
        return 0

def get_qty(symbol, balance):
    try:
        price = ex.fetch_ticker(symbol)["last"]
        qty = (balance * 0.95) / price
        return float(ex.amount_to_precision(symbol, qty)), price
    except Exception as e:
        print(f"Qty err {e}")
        return 0, 0

def close_position(symbol):
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        positions = ex.fetch_positions([mexc_sym])
        for p in positions:
            contracts = float(p.get("contracts", 0) or 0)
            if contracts > 0:
                side = p.get("side", "")
                close_side = "sell" if side == "long" else "buy"
                print(f"Closing {symbol} {side} {contracts}")
                try:
                    ex.create_market_order(mexc_sym, close_side, contracts, None, {"reduceOnly": True})
                    print(f"CLOSED {symbol}")
                    return True
                except Exception as e:
                    try:
                        ex.create_market_order(mexc_sym, close_side, contracts)
                        print(f"CLOSED fallback {symbol}")
                        return True
                    except Exception as e2:
                        print(f"Close err {e2}")
                        return False
        print(f"No position for {symbol}")
        return True
    except Exception as e:
        print(f"close_position error {e}")
        return False

def close_partial(symbol, percent=50):
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        positions = ex.fetch_positions([mexc_sym])
        for p in positions:
            contracts = float(p.get("contracts", 0) or 0)
            if contracts > 0:
                side = p.get("side", "")
                close_qty = contracts * (percent / 100)
                close_qty = float(ex.amount_to_precision(symbol, close_qty))
                close_side = "sell" if side == "long" else "buy"
                ex.create_market_order(mexc_sym, close_side, close_qty, None, {"reduceOnly": True})
                print(f"PARTIAL CLOSED {percent}% {symbol}")
                return True
        return False
    except Exception as e:
        print(f"partial close err {e}")
        return False

def auto_trade(symbol, side, sl=None, tp=None, score=None):
    if isinstance(sl, (int, float)) and sl > 50 and tp is None and score is None:
        score = sl
        sl = None
    print(f"AUTO REQUEST {symbol} {side} Score:{score}")
    if symbol not in SYMBOLS_ALLOWED:
        print(f"BLOCKED {symbol} not allowed")
        return False
    bal = get_balance_usdt()
    print(f"Futures Balance: {bal}")
    if bal < 1:
        print("No Futures balance")
        return False
    qty, price = get_qty(symbol, bal)
    if qty == 0:
        print("Qty 0")
        return False
    s = side.upper()
    mexc_side = "buy" if s in ["LONG", "BUY"] else "sell"
    print(f"FIRING {mexc_side} {symbol} Qty {qty}")
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        try:
            ex.set_leverage(5, mexc_sym)
            ex.set_margin_mode("isolated", mexc_sym)
        except:
            pass
        order = ex.create_market_order(mexc_sym, mexc_side, qty)
        print(f"FILLED Order {order.get('id')}")
        return True
    except Exception as e:
        print(f"MEXC ERROR: {e}")
        return False
