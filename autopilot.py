import ccxt, os, time, json
from datetime import datetime

MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET")

SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT"]
COMPOUND_PCT = 0.95
STOP_LOSS_PCT = 0.08
TRAILING_PCT = 0.12
TRAILING_ACTIVATE_PCT = 0.05
MAX_LOSS_STREAK = 2

MEXC_MAP = {"KOMA/USDT:USDT": "KOMA_USDT", "GRASS/USDT:USDT": "GRASS_USDT"}
STATE_FILE = "compound_state.json"

ex = ccxt.mexc({
    "apiKey": MEXC_API_KEY,
    "secret": MEXC_API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"balance_start": 10, "balance_now": 10, "loss_streak": 0, "total_trades": 0}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def get_balance_usdt():
    try:
        bal = ex.fetch_balance()
        return bal.get("USDT", {}).get("free", 0) or 0
    except Exception as e:
        print(f"Balance error: {e}")
        return 0

def get_qty(symbol, balance):
    try:
        price = ex.fetch_ticker(symbol)["last"]
        qty = (balance * COMPOUND_PCT) / price
        return float(ex.amount_to_precision(symbol, qty)), price
    except:
        return 0, 0

def auto_trade(symbol, side, amount=None):
    state = load_state()
    if symbol not in SYMBOLS_ALLOWED:
        print(f"⛔ BLOCKED {symbol}")
        return
    if state["loss_streak"] >= MAX_LOSS_STREAK:
        print(f"⛔ PAUSED - loss streak")
        return
    balance = get_balance_usdt()
    if balance < 1:
        print(f"⛔ Balance low ${balance} - Move USDT from Spot to Futures in MEXC!")
        return
    qty, price = get_qty(symbol, balance)
    if qty <= 0:
        return
    mexc_symbol = MEXC_MAP.get(symbol)
    print(f"🚀 TRADE: {side} {mexc_symbol} | Bal ${balance:.2f} | Qty {qty}")
    try:
        order = ex.create_market_order(mexc_symbol, side.lower(), qty)
        print(f"✅ FILLED {order['id']} @ {price}")
        state["total_trades"] += 1
        state["balance_now"] = balance
        save_state(state)
        print(f"📈 Progress: ${state['balance_start']} -> ${balance:.2f}")
    except Exception as e:
        print(f"❌ MEXC ERROR: {e}")

# ===== TEST MODE =====
if __name__ == "__main__":
    print("🔥 ===== MEXC TEST START =====")
    print(f"🔑 API Key exists: {bool(MEXC_API_KEY)}")
    print(f"🔑 Secret exists: {bool(MEXC_API_SECRET)}")
    bal = get_balance_usdt()
    print(f"💰 MEXC Futures Balance: ${bal}")
    if bal > 1:
        print("✅ Balance OK - Trying test buy...")
        auto_trade("KOMA/USDT:USDT", "buy")
    else:
        print("⛔ No Futures balance! Go MEXC App -> Wallet -> Transfer Spot -> Futures")
    print("🔥 ===== TEST END =====")
