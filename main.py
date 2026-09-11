import os
import ccxt
import pandas as pd
import requests
import time
from datetime import datetime, timezone

BALANCE = 14.99
TARGET = 10000.0
NEED_X = TARGET / BALANCE
LEVERAGE = 10
NOTIONAL = 3.0
MAX_QTY_CAP = 50
TRADED_THIS_RUN = False

SYMBOLS = [
    "KOMA/USDT:USDT",
    "GRASS/USDT:USDT",
    "HEI/USDT:USDT",
    "LAB/USDT:USDT",
    "SIREN/USDT:USDT",
    "VELVET/USDT:USDT"
]

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")
MEXC_KEY = os.getenv("MEXC_API_KEY")
MEXC_SECRET = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET") or os.getenv("API_SECRET")

def send_telegram(msg):
    try:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            print(f"TG SKIP: {msg}")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"TG FAIL: {e}")

def get_exchange():
    if not MEXC_KEY or not MEXC_SECRET:
        print("❌ NO API KEYS")
        return None
    ex = ccxt.mexc({'apiKey': MEXC_KEY,'secret': MEXC_SECRET,'options': {'defaultType': 'swap'},'enableRateLimit': True})
    return ex

def close_position(exchange, symbol):
    try:
        positions = exchange.fetch_positions([symbol])
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if abs(contracts) > 0:
                side = p.get('side', '')
                close_side = "sell" if side == "long" else "buy"
                print(f"🔄 CLOSING {symbol} {side} {contracts} -> {close_side}")
                exchange.create_market_order(symbol, close_side, abs(contracts), params={"reduceOnly": True})
                send_telegram(f"🔄 *CLOSED* {symbol} {side.upper()} {contracts} in profit - Flipping!")
                time.sleep(1)
                return True
        return False
    except Exception as e:
        print(f"Close error {symbol}: {e}")
        return False

def get_killzone():
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    if 0 <= hour < 6:
        return "ASIAN", "Low Volatility - Range", hour
    elif 7 <= hour < 12:
        return "LONDON", "High Volatility - Breakout", hour
    elif 12 <= hour < 17:
        return "NEW YORK", "High Volatility - Trend", hour
    elif 17 <= hour < 20:
        return "LONDON CLOSE", "Medium Volatility - Reversal", hour
    else:
        return "DEAD ZONE", "Low Volatility - Avoid", hour

def is_best_time_to_trade():
    session, vol, hour = get_killzone()
    if session in ["LONDON", "NEW YORK"]:
        return True, session
    return False, session

def safe_autopilot_enter(exchange, symbol, side, price, session):
    global TRADED_THIS_RUN
    try:
        positions = exchange.fetch_positions([symbol])
        has_pos = False
        pos_side = ""
        pos_pnl = 0
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if abs(contracts) > 0:
                has_pos = True
                pos_side = p.get('side', '')
                pos_pnl = float(p.get('unrealizedPnl', 0) or 0)
                break

        if has_pos:
            wanted_long = "buy" in side.lower()
            currently_long = pos_side == "long"
            if (wanted_long and currently_long) or (not wanted_long and not currently_long):
                print(f"⚠️ Already same direction {symbol} {pos_side} - SKIP")
                return False
            if pos_pnl > 0:
                print(f"🔄 FLIP {symbol} {pos_side} PnL ${pos_pnl} >0 to {side}")
                send_telegram(f"🔄 *FLIP SIGNAL* {symbol} {pos_side.upper()} profit ${pos_pnl:.2f} -> {side.upper()} | Session {session}")
                close_position(exchange, symbol)
                time.sleep(1)
            else:
                print(f"⚠️ {symbol} opposite but PnL ${pos_pnl} negative - HOLD")
                send_telegram(f"⚠️ HOLD {symbol} {pos_side} PnL ${pos_pnl:.2f} negative - No flip")
                return False

        if TRADED_THIS_RUN and not has_pos:
            print(f"⚠️ SKIP {symbol} - Already traded this run")
            return False

        qty = int(NOTIONAL / price)
        qty = max(1, min(qty, MAX_QTY_CAP))
        print(f"🚀 TRY {symbol} {side} QTY {qty} = ${NOTIONAL} @ {price} LEV {LEVERAGE}x | {session}")
        try:
            exchange.set_leverage(LEVERAGE, symbol)
            exchange.set_margin_mode('isolated', symbol)
        except:
            pass
        order = exchange.create_market_order(symbol, side.lower(), qty)
        TRADED_THIS_RUN = True
        send_telegram(f"✅ *AUTOPILOT ENTERED* {symbol} {side.upper()} {qty} @ {price}\nSession {session} | Lev {LEVERAGE}x {'(FLIP)' if has_pos else '(NEW)'}")
        print(f"✅ ENTERED {symbol} {side} {qty}")
        return True
    except Exception as e:
        err = str(e)
        print(f"❌ FAILED {symbol}: {err}")
        if "2051" in err or "maximum" in err.lower():
            try:
                qty_small = int(1.0 / price)
                qty_small = max(1, min(qty_small, 10))
                order = exchange.create_market_order(symbol, side.lower(), qty_small)
                TRADED_THIS_RUN = True
                send_telegram(f"✅ *ENTERED SMALL* {symbol} {side} {qty_small} @ {price} (Retry) | {session}")
                return True
            except Exception as e2:
                send_telegram(f"⚠️ *FAILED* {symbol} {err} | {e2} | {session}")
                return False
        else:
            send_telegram(f"⚠️ *FAILED* {symbol} {err} | {session}")
            return False

def check_filters(df, symbol):
    reasons = []
    fake = False
    try:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        last_rsi = rsi.iloc[-1]
        if last_rsi > 70:
            reasons.append("RSI71OB" if last_rsi > 71 else f"RSI{int(last_rsi)}OB")
        if last_rsi > 74:
            reasons.append("RSI74OB")
        if last_rsi < 30:
            reasons.append(f"RSI{int(last_rsi)}OS")
        if last_rsi > 47 and "KOMA" in symbol:
            reasons.append(f"RSI47+")
    except:
        last_rsi = 50
    try:
        if df['close'].iloc[-1] > df['open'].iloc[-1]:
            reasons.append("BULLOB")
        else:
            reasons.append("BEAROB")
    except:
        reasons.append("BULLOB")
    try:
        if df['high'].iloc[-2] < df['low'].iloc[-1]:
            reasons.append("BEARFVG")
        if df['low'].iloc[-2] > df['high'].iloc[-1]:
            reasons.append("BULLFVG")
    except:
        pass
    try:
        if df['close'].iloc[-1] < df['close'].iloc[-2]:
            reasons.append("MPATTERN")
        if df['close'].iloc[-1] > df['close'].iloc[-2]:
            reasons.append("WPATTERN")
    except:
        pass
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
    if "KOMA" in symbol:
        try:
            if mom > 1.0:
                reasons.append("KOMAPUMPOVERRIDE")
        except:
            reasons.append("KOMAPUMPOVERRIDE")
    if "NEUTRAL" in reasons and len(reasons) < 3:
        fake = True
    return reasons, mom, last_rsi, fake

def scan():
    global TRADED_THIS_RUN
    TRADED_THIS_RUN = False
    exchange = get_exchange()
    if not exchange:
        send_telegram("❌ Bot failed - No API keys")
        return
    session, vol, hour_utc = get_killzone()
    print(f"🔍 Scan {datetime.now(timezone.utc)} | Session {session} {hour_utc}UTC | Bal ${BALANCE} -> ${TARGET}")
    try:
        bal = exchange.fetch_balance()
        usdt_free = bal['USDT']['free'] if 'USDT' in bal else bal.get('free', {}).get('USDT', 0)
        print(f"💰 Balance: ${usdt_free}")
        send_telegram(f"💰 *BALANCE* ${usdt_free} | Session {session} {hour_utc}UTC {vol}")
        positions = exchange.fetch_positions()
        open_pos = [p for p in positions if float(p.get('contracts', 0) or 0) > 0]
        for p in open_pos:
            sym = p['symbol']
            contracts = p['contracts']
            entry = p['entryPrice']
            pnl = p.get('unrealizedPnl', 0)
            send_telegram(f"📌 *OPEN* {sym} {contracts} @ {entry} PnL ${pnl}")
    except Exception as e:
        print(f"Balance error: {e}")
    for symbol in SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            price = df['close'].iloc[-1]
            reasons, mom, rsi, fake = check_filters(df, symbol)
            session, vol, hour_utc = get_killzone()
            is_killzone, _ = is_best_time_to_trade()
            if session in ["LONDON", "NEW YORK"]:
                reasons.append(f"{session}KILLZONE")
            score = 75
            if "KOMAPUMPOVERRIDE" in reasons:
                score = 85
            if is_killzone:
                score += 5
            side = "BUY LONG" if "BULLOB" in reasons or "WPATTERN" in reasons or "MARKETPUMPING" in reasons or "KOMAPUMPOVERRIDE" in reasons else "SELL SHORT"
            fake_str = "Fake:" if fake else ""
            msg = f"📢 *SIGNAL: {side} {symbol} ({score})*\nPrice {price} mom {mom:.1f}%\nSession: {session} {hour_utc}UTC - {vol}\nReasons {', '.join(reasons)} {fake_str}\nBal ${BALANCE} -> ${TARGET} LEV {LEVERAGE}x"
            print(msg)
            send_telegram(msg)
            time.sleep(1)
            order_side = "buy" if "BUY" in side else "sell"
            safe_autopilot_enter(exchange, symbol, order_side, price, session)
            time.sleep(2)
        except Exception as e:
            print(f"❌ Error {symbol}: {e}")
            continue
    print("\n✅ Scan Complete")

if __name__ == "__main__":
    scan()
