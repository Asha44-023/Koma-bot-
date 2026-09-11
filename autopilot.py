import os
import ccxt

# --- CONFIG ---
BALANCE = 14.99
LEVERAGE = 10
# MEXC max contracts per order - FIX for error 2051
MAX_QTY = {
    "KOMA/USDT:USDT": 800,
    "GRASS/USDT:USDT": 500,
    "HEI/USDT:USDT": 500,
    "LAB/USDT:USDT": 500,
    "DEFAULT": 300
}

def get_exchange():
    api_key = os.getenv("MEXC_API_KEY")
    secret = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET") or os.getenv("API_SECRET")
    
    if not api_key or not secret:
        print("❌ No API keys found")
        return None
        
    exchange = ccxt.mexc({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'swap'}
    })
    exchange.set_leverage(LEVERAGE)
    return exchange

def is_already_in_position(exchange, symbol):
    try:
        positions = exchange.fetch_positions([symbol])
        for pos in positions:
            if float(pos.get('contracts', 0)) > 0:
                print(f"⚠️ Already in {symbol}: {pos['contracts']} contracts")
                return True
        return False
    except:
        return False

def calculate_safe_quantity(symbol):
    """FINAL FIX for 2051 error"""
    base = MAX_QTY.get(symbol, MAX_QTY["DEFAULT"])
    
    # For $14.99 balance, use small safe qty
    if "KOMA" in symbol:
        return 150  # Was 4000+ causing 2051, now 150 = safe
    elif "GRASS" in symbol:
        return 40   # GRASS price 0.32 = $12.8 notional
    elif "HEI" in symbol:
        return 100
    elif "LAB" in symbol:
        return 150
    else:
        return 80

def autopilot_enter(symbol, side, price=None):
    try:
        exchange = get_exchange()
        if not exchange:
            return {"success": False, "message": "No exchange"}
        
        # 1. Check already in position
        if is_already_in_position(exchange, symbol):
            return {"success": False, "message": f"Already in {symbol}"}
        
        # 2. Safe quantity - FIX 2051
        qty = calculate_safe_quantity(symbol)
        
        print(f"🚀 TRYING {side} {symbol} QTY {qty} LEV {LEVERAGE}x Bal ${BALANCE}")
        
        # 3. Set leverage & margin mode
        try:
            exchange.set_leverage(LEVERAGE, symbol)
            exchange.set_margin_mode('isolated', symbol)
        except Exception as e:
            print(f"Leverage set warning: {e}")
        
        # 4. Place order
        order = exchange.create_market_order(symbol, side.lower(), qty)
        
        print(f"✅ AUTOPILOT ENTERED {symbol} {side} {qty} @ {price}")
        return {"success": True, "order": order, "qty": qty}
        
    except Exception as e:
        err = str(e)
        print(f"❌ AUTOPILOT FAILED {symbol}: {err}")
        
        # If still hits max
