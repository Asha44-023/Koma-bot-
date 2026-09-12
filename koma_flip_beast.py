import ccxt, time, requests, os, json
from datetime import datetime
import pandas as pd

# === CONFIG ===
SYMBOL = "KOMA/USDT:USDT"
LEVERAGE = 10
RISK_PCT = 0.5  # FAST SAFE: 50% per trade, survive 1 loss
TP_PCT = 10.0   # 10% price = 100% x leverage = double risked part
SL_PCT = 6.0    # 6% price = 60% loss of risked part
TRAIL_TRIGGER = 4.0
TRAIL_OFFSET = 1.0
TIME_STOP_MIN = 30
COOLDOWN_MIN = 5

# KOMA TOP FILTER - only real 20% tops
PUMP_5M_MIN = 1.5
PUMP_30M_MIN = 8.0
RSI_TOP = 68
VWAP_DIST = 2.5

TELEGRAM_BOT = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")

def send_tg(msg):
    if not TELEGRAM_BOT: return
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except: pass

ex = ccxt.mexc({
    'apiKey': os.getenv("MEXC_API_KEY"),
    'secret': os.getenv("MEXC_SECRET"),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def add_filters(df):
    df['ema9'] = df['c'].ewm(span=9).mean()
    df['ema21'] = df['c'].ewm(span=21).mean()
    df['vwap'] = (df['c'] * df['v']).cumsum() / df['v'].cumsum()
    delta = df['c'].diff()
    gain = delta.where(delta>0,0).ewm(alpha=1/14).mean()
    loss = -delta.where(delta<0,0).ewm(alpha=1/14).mean()
    df['rsi'] = 100 - (100 / (1 + gain/loss))
    df['vol_ma10'] = df['v'].rolling(10).mean()
    df['close_pos'] = (df['c']-df['l'])/(df['h']-df['l']+1e-9)
    df['bb_upper'] = df['c'].rolling(20).mean() + 2*df['c'].rolling(20).std()
    return df

def scalp_plan():
    try:
        ohlcv = ex.fetch_ohlcv(SYMBOL, '5m', limit=100)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
        df = add_filters(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = last['c']
        change_5m = (last['c']-prev['c'])/prev['c']*100
        change_30m = (last['c']-df.iloc[-7]['c'])/df.iloc[-7]['c']*100 if len(df)>=7 else 0
        rsi = last['rsi']
        vwap_dist = (price - last['vwap'])/last['vwap']*100
        vol_ratio = last['v']/last['vol_ma10'] if last['vol_ma10']>0 else 1

        bal = ex.fetch_balance()
        free = float(bal['USDT']['free'] if 'USDT' in bal else bal['free']['USDT'] if 'free' in bal else 12)
        if free < 3: free = 12.91

        # --- CHECK OPEN POSITION ---
        positions = ex.fetch_positions([SYMBOL])
        for p in positions:
            if float(p['contracts']) > 0:
                entry = float(p['entryPrice'])
                side = p['side']
                pnl_pct = (price-entry)/entry*100 * (1 if side=='long' else -1)
                # TRAIL
                if pnl_pct >= TRAIL_TRIGGER:
                    if side=='long' and price < df['c'].rolling(5).max().iloc[-1]*(1-TRAIL_OFFSET/100):
                        ex.create_market_order(SYMBOL, 'sell', float(p['contracts']), params={'reduceOnly':True})
                        send_tg(f"✅ TRAIL CLOSE LONG +{pnl_pct:.1f}% ${free:.2f}")
                        return f"TRAIL LONG +{pnl_pct:.1f}%"
                    if side=='short' and price > df['c'].rolling(5).min().iloc[-1]*(1+TRAIL_OFFSET/100):
                        ex.create_market_order(SYMBOL, 'buy', float(p['contracts']), params={'reduceOnly':True})
                        send_tg(f"✅ TRAIL CLOSE SHORT +{pnl_pct:.1f}% ${free:.2f}")
                        return f"TRAIL SHORT +{pnl_pct:.1f}%"
                # TP/SL
                if pnl_pct >= TP_PCT:
                    ex.create_market_order(SYMBOL, 'sell' if side=='long' else 'buy', float(p['contracts']), params={'reduceOnly':True})
                    send_tg(f"💰 TP {TP_PCT}% {side} ${free:.2f} → ${free*(1+RISK_PCT):.2f}")
                    return f"TP {pnl_pct:.1f}%"
                if pnl_pct <= -SL_PCT:
                    ex.create_market_order(SYMBOL, 'sell' if side=='long' else 'buy', float(p['contracts']), params={'reduceOnly':True})
                    send_tg(f"❌ SL -{SL_PCT}% {side} ${free:.2f}")
                    return f"SL {pnl_pct:.1f}%"
                return f"HOLD {side} {pnl_pct:.1f}%"

        # --- NO POSITION - LOOK FOR FAST SAFE ENTRY ---
        # ONLY SHORT TOP - FAST SAFE
        if change_5m >= PUMP_5M_MIN and change_30m >= PUMP_30M_MIN:
            if rsi < RSI_TOP: return f"WAIT RSI {rsi:.0f} need {RSI_TOP}+"
            if vwap_dist < VWAP_DIST: return f"WAIT VWAP {vwap_dist:.1f}% need {VWAP_DIST}%"
            if last['close_pos'] < 0.65: return f"WAIT close {last['close_pos']:.2f} need 0.65+"
            # TOP CONFIRMED - ALL IN 50%
            notional = free * RISK_PCT * LEVERAGE  # 50% risk * 10x
            qty = notional / price
            if qty * price < 5: qty = 5/price
            ex.set_leverage(LEVERAGE, SYMBOL)
            ex.set_margin_mode('isolated', SYMBOL)
            ex.create_market_order(SYMBOL, 'sell', qty)
            send_tg(f"🔴 *FAST SAFE SHORT* 5m {change_5m:.1f}% 30m {change_30m:.1f}% RSI {rsi:.0f} @ {price:.5f}\nBal ${free:.2f} Risk 50% Lev {LEVERAGE}x\nTP {TP_PCT}% SL {SL_PCT}%")
            return f"SHORT {change_5m:.1f}% {change_30m:.1f}%"

        return f"WAIT 5m {change_5m:.1f}% 30m {change_30m:.1f}% RSI {rsi:.0f} need 30m {PUMP_30M_MIN}% RSI {RSI_TOP}"

    except Exception as e:
        return f"ERR {e}"

# === LOOP ===
if __name__ == "__main__":
    while True:
        print(f"{datetime.utcnow().strftime('%H:%M:%S')} {scalp_plan()}")
        time.sleep(60)
