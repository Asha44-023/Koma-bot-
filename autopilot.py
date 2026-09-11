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
        # MEXC futures balance sometimes in total
        usdt = bal.get("USDT", {})
        free = usdt.get("free", 0) or usdt.get("total", 0) or 0
        if free == 0:
            # Try fetch from other field
            free = bal.get("free", {}).get("USDT", 0) or 0
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
        return 0,0

def close_position(symbol):
    """Close full position for symbol on MEXC Futures"""
    try:
        mexc_sym = MEXC_MAP.get(symbol, symbol)
        # Fetch open positions
        positions = ex.fetch_positions([mexc_sym])
        found = False
        for p in positions:
            # p = dict with symbol, contracts, side
            if mexc_sym in p['symbol'] or symbol.split("/")[0] in p['symbol']:
                contracts = float(p.get('contracts', 0) or p.get('contractSize
