import ccxt, os, time, json
from datetime import datetime

# ===== CONFIG =====
USE_MAINNET = False
MEXC_API_KEY = os.getenv("MEXC_API_KEY")
MEXC_API_SECRET = os.getenv("MEXC_API_SECRET")

SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT"]

# SAFE COMPOUNDING CONFIG
COMPOUND_PCT = 0.95  # Use 95% each trade, keep 5% safe
STOP_LOSS_PCT = 0.08  # 8% SL
TRAILING_PCT = 0.12  # 12% trailing to lock big moves
TRAILING_ACTIVATE_PCT = 0.05  # Start trailing after +5%
MAX_LOSS_STREAK = 2  # Stop after 2 losses
TAKE_PROFIT_PCT = 0.25  # Take 25% profit on big pump

MEXC_MAP = {
    "KOMA/USDT:USDT": "KOMA_USDT",
    "GRASS/USDT:USDT": "GRASS_USDT"
}

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
        return {"balance_start": 10, "balance_now": 10, "loss_streak": 0, "total_trades": 0, "wins": 0}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f)

def get_balance_usdt():
    try:
        bal = ex.fetch_balance()
        return bal.get("USDT", {}).get("free", 0) or 0
    except:
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

    # FILTER 1 - Only KOMA/GRASS
    if symbol not in SYMBOLS_ALLOWED:
        print(f"⛔ BLOCKED {symbol}")
        return

    # FILTER 2 - Loss streak protection
    if state["loss_streak"] >= MAX_LOSS_STREAK:
        print(f"⛔ PAUSED - {MAX_LOSS_STREAK} losses in row, cooling down")
        return

    balance = get_balance_usdt()
    if balance < 1:
        print(f"⛔ Balance low ${balance}")
        return

    qty, price = get_qty(symbol, balance)
    if qty <= 0:
        return

    mexc_symbol = MEXC_MAP.get(symbol)
    print(f"🚀 COMPOUND TRADE {state['total_trades']+1}: {side} {mexc_symbol} | Bal ${balance:.2f} | Qty {qty}")

    try:
        order = ex.create_market_order(mexc_symbol, side.lower(), qty)
        print(f"✅ FILLED {order['id']} @ {price}")

        # Update state for compounding
        state["total_trades"] += 1
        state["balance_now"] = balance
        save_state(state)

        print(f"📈 Progress: ${state['balance_start']} -> ${balance:.2f} = {balance/state['balance_start']:.1f}x | Goal $10000 = {balance/10000*100:.2f}%")

    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    s = load_state()
    print(f"💰 COMPOUND BOT: ${s['balance_start']} -> ${s['balance_now']} | {s['total_trades']} trades")
    auto_trade("KOMA/USDT:USDT", "buy")
