# autopilot.py - KOMA + GRASS - $10 to $100k challenge - FIXED
import ccxt
import os

SIZE_START = 10
LEVERAGE = 5
SYMBOLS_ALLOWED = ["KOMA/USDT:USDT", "GRASS/USDT:USDT"]

def get_balance_usdt(ex):
    try:
        bal = ex.fetch_balance()
        # Try futures balance
        if 'USDT' in bal:
            return bal['USDT'].get('free', 0) or bal['USDT'].get('total', 0) or SIZE_START
        return bal.get('USDT', {}).get('free', SIZE_START)
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
            
        balance = get_balance_usdt(ex)
        trade_size = max(SIZE_START, balance * 0.5)
        
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (trade_size * LEVERAGE) / price
        
        # round amount to 3 decimals for KOMA/GRASS
        amount = round(amount, 1)
        if amount < 1:
            amount = 1
        
        order_side = 'buy' if side == 'LONG' else 'sell'
        opposite = 'sell' if side == 'LONG' else 'buy'
        
        print(f"🚀 {symbol} {side} ${trade_size:.2f} ({amount} coins) Bal ${balance:.2f}")
        
        ex.create_market_order(symbol, order_side, amount)
        
        # SL - STOP MARKET
        try:
            ex.create_order(symbol, 'STOP_MARKET', opposite, amount, None, params={
                'stopPrice': sl,
                'reduceOnly': True
            })
        except Exception as e:
            print(f"SL fail {e}")

        # TP - LIMIT
        try:
            ex.create_order(symbol, 'limit', opposite, amount, tp, params={
                'reduceOnly': True
            })
        except Exception as e:
            print(f"TP fail {e}")
        
        print(f"✅ {symbol} {side} FILLED")
        return True
        
    except Exception as e:
        print(f"❌ AUTO ERROR {symbol}: {e}")
        return False
