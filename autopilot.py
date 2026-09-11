import ccxt, os, json

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

# FIXED TO ACCEPT 4 ARGS FROM main.py
def auto_trade(symbol, side, amount=None, score=None):
    if score is not None:
        print(f"Signal score: {score}")
    if symbol not in SYMBOLS_ALLOWED:
        print(f"⛔ BLOCKED {symbol}")
        return
    bal = get_balance_usdt()
    print(f"💰 Futures Balance: ${bal}")
    if bal < 1:
        print("⛔ No balance in Futures! Transfer from Spot to Futures!")
        return
    qty, price = get_qty(symbol, bal)
    print(f"🚀 FIRING {side} {symbol} Qty {qty} @ {price}")
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        order = ex.create_market_order(mexc_sym, side.lower(), qty)
        print(f"✅ FILLED on MEXC! {order['id']}")
    except Exception as e:
        print(f"❌ MEXC ERROR: {e}")

if __name__ == "__main__":
    print("TEST")
    auto_trade("KOMA/USDT:USDT", "buy", None, 100)
