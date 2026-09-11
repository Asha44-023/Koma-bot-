import ccxt, os

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
        return float(bal.get("USDT", {}).get("free", 0))
    except Exception as e:
        print(f"Balance err {e}")
        return 0

def get_qty(symbol, balance):
    try:
        price = ex.fetch_ticker(symbol)["last"]
        qty = (balance * 0.95) / price
        return float(ex.amount_to_precision(symbol, qty)), price
    except:
        return 0,0

# FIXED - NOW ACCEPTS 5 ARGS FROM YOUR NEW MAIN.PY
def auto_trade(symbol, side, sl=None, tp=None, score=None):
    # side = LONG/SHORT from main.py, convert to buy/sell
    if isinstance(sl, (int,float)) and sl > 50 and tp is None and score is None:
        # Called as old style: symbol, side, None, score
        score = sl
        sl = None
    
    print(f"🤖 AUTO REQUEST {symbol} {side} SL:{sl} TP:{tp} Score:{score}")
    
    if symbol not in SYMBOLS_ALLOWED:
        print(f"⛔ BLOCKED {symbol} not in allowed")
        return False
    
    bal = get_balance_usdt()
    print(f"💰 Futures Balance: ${bal}")
    if bal < 1:
        print("⛔ No balance in Futures! Transfer Spot -> Futures in MEXC app!")
        return False
    
    qty, price = get_qty(symbol, bal)
    if qty == 0:
        print("⛔ Qty 0 - balance too low")
        return False
        
    # Convert LONG/SHORT or buy/sell to MEXC side
    if isinstance(side, str):
        s = side.upper()
        if s == "LONG" or s == "BUY":
            mexc_side = "buy"
        elif s == "SHORT" or s == "SELL":
            mexc_side = "sell"
        else:
            mexc_side = side.lower()
    else:
        mexc_side = "buy"
    
    print(f"🚀 FIRING {mexc_side} {symbol} Qty {qty} @ {price}")
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        order = ex.create_market_order(mexc_sym, mexc_side, qty)
        print(f"✅ FILLED on MEXC! Order ID {order.get('id')} Qty {qty}")
        return True
    except Exception as e:
        print(f"❌ MEXC ERROR: {e}")
        return False

if __name__ == "__main__":
    print("TEST")
    auto_trade("KOMA/USDT:USDT", "LONG", 0.01, 0.02, 100)
