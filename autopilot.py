# autopilot.py - KOMA + GRASS - $10 to $100k challenge
import ccxt
import os

SIZE_START = 10  # start $10
LEVERAGE = 5
SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT"]

def get_balance_usdt(ex):
    try:
        bal = ex.fetch_balance()
        return bal['USDT']['free']
    except:
        return SIZE_START

def auto_trade(symbol, side, sl, tp):
    if symbol not in SYMBOLS_ALLOWED:
        print(f"Skip {symbol} - not KOMA/GRASS")
        return False
        
    ex = ccxt.mexc({
        'apiKey': os.getenv("MEXC_API_KEY"),
        'secret': os.getenv("MEXC_SECRET"),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    try:
        try:
            ex.set_leverage(LEVERAGE, symbol)
        except:
            pass
            
        # COMPOUNDING: use 50% of balance each trade to grow fast
        balance = get_balance_usdt(ex)
        trade_size = max(SIZE_START, balance * 0.5)
        
        price = ex.fetch_ticker(symbol)['last']
        amount = (trade_size * LEVERAGE) / price
        
        order_side = 'buy' if side == 'LONG' else 'sell'
        opposite = 'sell' if side == 'LONG' else 'buy'
        
        print(f"🚀 {symbol} {side} ${trade_size:.2f} ({amount} coins)")
        
        ex.create_market_order(symbol, order_side, amount)
        
        # SL/TP
        ex.create_order(symbol, 'stop', opposite, amount, None, params={
            'stopPrice': sl,
            'reduceOnly': True
        })
        ex.create_order(symbol, 'limit', opposite, amount, tp, params={
            'reduceOnly': True
        })
        
        print(f"✅ {symbol} {side} FILLED - Bal now ${balance:.2f} -> target $100k")
        return True
        
    except Exception as e:
        print(f"❌ AUTO ERROR {symbol}: {e}")
        return False

# alias for old code
def auto_koma(side, sl, tp):
    return auto_trade("KOMA/USDT:USDT", side, sl, tp)

def auto_grass(side, sl, tp):
    return auto_trade("GRASS/USDT:USDT", side, sl, tp)
