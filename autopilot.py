import ccxt
import os

MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET")

# === FINAL ALLOWED - ALL 6 COINS FOR $10K JOURNEY ===
SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT", "VELVET/USDT:USDT", "SIREN/USDT:USDT", "HEI/USDT:USDT", "LAB/USDT:USDT"]
MEXC_MAP = {
    "KOMA/USDT:USDT": "KOMA_USDT",
    "GRASS/USDT:USDT": "GRASS_USDT",
    "VELVET/USDT:USDT": "VELVET_USDT",
    "SIREN/USDT:USDT": "SIREN_USDT",
    "HEI/USDT:USDT": "HEI_USDT",
    "LAB/USDT:USDT": "LAB_USDT"
}

ex = ccxt.mexc({
    "apiKey": MEXC_API_KEY,
    "secret": MEXC_API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

LEVERAGE = 10  # For $14.99 -> $10k

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
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        ticker = ex.fetch_ticker(mexc_sym)
        price = ticker["last"]
        # === CONTRACTS FIX FOR QUANTITY ERROR 2011 ===
        contracts = (balance * 0.95 * LEVERAGE) / price
        if contracts < 1: contracts = 1
        # MEXC wants int for low caps
        if price < 1:
            qty = int(contracts) if contracts > 10 else round(contracts, 1)
        else:
            qty = int(contracts)
        return qty, price
    except Exception as e:
        print(f"Qty err {e}")
        return 0, 0

def is_already_in_position(symbol, side):
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        positions = ex.fetch_positions([mexc_sym])
        for p in positions:
            contracts = float(p.get("contracts", 0) or 0)
            if contracts > 0:
                pos_side = p.get("side", "")
                if pos_side == "long" and side.upper() in ["LONG", "BUY"]: return True
                if pos_side == "short" and side.upper() in ["SHORT", "SELL"]: return True
        return False
    except: return False

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
                    return True
                except:
                    try:
                        ex.create_market_order(mexc_sym, close_side, contracts)
                        return True
                    except Exception as e2:
                        print(f"Close err {e2}")
                        return False
        return True
    except Exception as e:
        print(f"close_position error {e}")
        return False

def auto_trade(symbol, side, sl=None, tp=None, score=None):
    if isinstance(sl, (int, float)) and sl > 50 and tp is None and score is None:
        score = sl; sl = None
    print(f"AUTO REQUEST {symbol} {side} Score:{score}")
    if symbol not in SYMBOLS_ALLOWED:
        print(f"BLOCKED {symbol} not allowed - add to SYMBOLS_ALLOWED")
        return False
    if is_already_in_position(symbol, side):
        print(f"SKIP {symbol} already in {side}")
        return False
    bal = get_balance_usdt()
    print(f"Futures Balance: {bal}")
    if bal < 1:
        print("No Futures balance")
        return False
    qty, price = get_qty(symbol, bal)
    if qty == 0: return False
    s = side.upper()
    mexc_side = "buy" if s in ["LONG", "BUY"] else "sell"
    print(f"FIRING {mexc_side} {symbol} Qty {qty} Price {price} LEV {LEVERAGE}x")
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        try:
            ex.set_leverage(LEVERAGE, mexc_sym)
            ex.set_margin_mode("isolated", mexc_sym)
        except: pass
        order = ex.create_market_order(mexc_sym, mexc_side, qty)
        print(f"FILLED {symbol} {side} {qty} contracts - Order {order.get('id')}")
        return True
    except Exception as e:
        print(f"MEXC ERROR {symbol}: {e}")
        return False
