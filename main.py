import os
import ccxt
import pandas as pd
import requests
import time
from datetime import datetime

# ========== CONFIG - YOUR $14.99 TO $10K ==========
BALANCE = 14.99
TARGET = 10000.0
NEED_X = TARGET / BALANCE
LEVERAGE = 10
NOTIONAL = 3.0  # $3 per trade = FIX for 2051 error
MAX_QTY_CAP = 50  # Never exceed 50 contracts

SYMBOLS = [
    "KOMA/USDT:USDT",
    "GRASS/USDT:USDT", 
    "HEI/USDT:USDT",
    "LAB/USDT:USDT",
    "SIREN/USDT:USDT",
    "ANIME/USDT:USDT"
]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")
MEXC_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET") or os.getenv("API_SECRET")

# ========== TELEGRAM ==========
def send_telegram(msg):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            print(f"TG SKIP: {msg}")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print(f"TG SENT: {msg[:80]}")
    except Exception as e:
        print(f"TG FAIL: {e}")

# ========== EXCHANGE ==========
def get_exchange():
    if not MEXC_KEY or not MEXC_SECRET:
        print("❌ NO API KEYS")
        return None
    ex = ccxt.mexc({
        'apiKey': MEXC_KEY,
        'secret': MEXC_SECRET,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
    return ex

def is_already_in_position(exchange, symbol):
    try:
        positions = exchange.fetch_positions([symbol])
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if contracts > 0:
                print(f"⚠️ Already in {symbol} {contracts}")
                return True
        return False
    except Exception as e:
        print(f"Pos check error {symbol}: {e}")
        return False

# ========== SAFE AUTOPILOT - FIX 2051 ==========
def safe_autopilot_enter(exchange, symbol, side, price):
    try:
        if is_already_in_position(exchange, symbol):
            send_telegram(f"⚠️ SKIP {symbol} Already in position")
            return False

        # Calculate qty from $3 notional - NEVER 2051
        qty = int(NOTIONAL / price)
        qty = max(1, min(qty, MAX_QTY_CAP))  # 1 to 50 only
        
        print(f"🚀 TRY {symbol} {side} QTY {qty} = ${NOTIONAL} @ {price} LEV {LEVERAGE}x")
        
        try:
            exchange.set_leverage(LEVERAGE, symbol)
            exchange.set_margin_mode('isolated', symbol)
        except Exception as e:
            print(f"Lev warning: {e}")

        order = exchange.create_market_order(symbol, side.lower(), qty)
        send_telegram(f"✅ *AUTOPILOT ENTERED* {symbol} {side.upper()} {qty} @ {price}\nLev {LEVERAGE}x Bal ${BALANCE} -> ${TARGET}")
        print(f"✅ ENTERED {symbol} {side} {qty}")
        return True

    except Exception as e:
        err = str(e)
        print(f"❌ FAILED {symbol}: {err}")
        
        # If still 2051, retry with $1 notional
        if "2051" in err or "maximum" in err.lower():
            try:
                qty_small = int(1.0 / price)
                qty_small = max(1, min(qty_small, 10))
                print(f"🔄 RETRY SMALL {symbol} qty {qty_small} $1")
                order = exchange.create_market_order(symbol, side.lower(), qty_small)
                send_telegram(f"✅ *ENTERED SMALL* {symbol} {side} {qty_small} @ {price} (Retry after 2051)")
                return True
            except Exception as e2:
                msg = f"⚠️ *AUTOPILOT FAILED* {symbol} {err} | Retry: {e2}"
                send_telegram(msg)
                return False
        else:
            send_telegram(f"⚠️ *AUTOPILOT FAILED* {symbol} {err}")
            return False

# ========== FILTERS - ALL INCLUDED ==========
def check_filters(df, symbol):
    reasons = []
    fake = False
    
    # RSI
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        last_rsi = rsi.iloc[-1]
        
        if last_rsi > 70:
            reasons.append("RSI71OB" if last_rsi > 71 else f"RSI{int(last_rsi)}OB")
        if last_rsi < 30:
            reasons.append(f"RSI{int(last_rsi)}OS")
    except:
        last_rsi = 50
    
    # Order Blocks - BULL/BEAR OB
    try:
        if df['close'].iloc[-1] > df['open'].iloc[-1]:
            reasons.append("BULLOB")
        else:
            reasons.append("BEAROB")
    except:
        reasons.append("BULLOB")
    
    # FVG
    try:
        if df['high'].iloc[-2] < df['low'].iloc[-1]:
            reasons.append("BEARFVG")
        if df['low'].iloc[-2] > df['high'].iloc[-1]:
            reasons.append("BULLFVG")
    except:
        pass
    
    # Patterns
    try:
        # M Pattern
        if df['close'].iloc[-1] < df['close'].iloc[-2]:
            reasons.append("MPATTERN")
        # W Pattern
        if df['close'].iloc[-1] > df['close'].iloc[-2]:
            reasons.append("WPATTERN")
    except:
        pass
    
    # Market Dumping/Pumping
    try:
        mom = ((df['close'].iloc[-1] - df['close'].iloc[-3]) / df['close'].iloc[-3]) * 100
        if mom < -0.5:
            reasons.append("MARKETDUMPING")
        elif mom > 0.5:
            reasons.append("MARKETPUMPING")
        else:
            reasons.append("NEUTRAL")
    except:
        mom = 0
        reasons.append("NEUTRAL")
    
    # KOMA PUMP OVERRIDE - ALWAYS INCLUDED
    if "KOMA" in symbol:
        try:
            if mom > 1.0:
                reasons.append("KOMAPUMPOVERRIDE")
            if last_rsi > 40:  # KOMA special - 47 bot
                reasons.append("RSI47+")
        except:
            reasons.append("KOMAPUMPOVERRIDE")
    
    # Fake check
    if "NEUTRAL" in reasons and len(reasons) < 3:
        fake = True
    
    return reasons, mom, last_rsi, fake

# ========== MAIN SCAN ==========
def scan():
    exchange = get_exchange()
    if not exchange:
        send_telegram("❌ Bot failed - No API keys")
        return
    
    print(f"🔍 Starting Whale Killer Scan {datetime.now()} Bal ${BALANCE} -> ${TARGET} Need {NEED_X:.0f}x")
    
    for symbol in SYMBOLS:
        try:
            print(f"\n--- Scanning {symbol} ---")
            # Fetch 15m candles
            ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            price = df['close'].iloc[-1]
            reasons, mom, rsi, fake = check_filters(df, symbol)
            
            # Score
            score = 75
            if "KOMAPUMPOVERRIDE" in reasons:
                score = 85
            if "RSI71OB" in reasons or "RSI74OB" in str(reasons):
                score = 85
            if "MARKETPUMPING" in reasons:
                score = 85
            if "MARKETDUMPING" in reasons:
                score = 75
            
            # Determine BUY/SELL
            side = None
            if "BULLOB" in reasons or "WPATTERN" in reasons or "MARKETPUMPING" in reasons or "KOMAPUMPOVERRIDE" in reasons:
                side = "BUY LONG"
            elif "BEAROB" in reasons or "MPATTERN" in reasons or "MARKETDUMPING" in reasons:
                side = "SELL SHORT"
            else:
                side = "BUY LONG" if rsi < 50 else "SELL SHORT"
            
            fake_str = "Fake:" if fake else ""
            
            # Telegram Signal
            msg = f"📢 *SIGNAL: {side} {symbol} ({score})*\nPrice {price} {reasons[-1] if reasons else 'NEUTRAL'} mom {mom:.1f}%\nReasons {', '.join(reasons)} {fake_str}\nBal ${BALANCE} -> ${TARGET} Need {NEED_X:.0f}x LEV {LEVERAGE}x"
            
            print(msg)
            send_telegram(msg)
            
            # AUTOPILOT ENTRY - With $3 fix
            time.sleep(1)
            order_side = "buy" if "BUY" in side else "sell"
            safe_autopilot_enter(exchange, symbol, order_side, price)
            
            time.sleep(2)  # Rate limit
            
        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")
            continue
    
    print("\n✅ Scan Complete")

if __name__ == "__main__":
    scan()
