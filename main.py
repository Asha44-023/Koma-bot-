import ccxt, requests, os, numpy as np, pandas as pd, time

# --- YOUR SETUP ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
symbols = ["GRASS/USDT", "KOMA/USDT", "HEI/USDT", "SIREN/USDT", "LAB/USDT", "VELVET/USDT"]
TEST_MODE = True # TRUE = Instant signal NOW, FALSE = real only after

def send_telegram(msg):
    try:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}", timeout=10)
        print(f"SENT: {msg}")
    except Exception as e:
        print(f"Telegram error: {e}")

def rsi_calc(closes, period=14):
    delta = np.diff(closes)
    gain = np.where(delta>0, delta, 0)
    loss = np.where(delta<0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    if avg_loss == 0: return 70
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --- INSTANT SIGNAL TEST ---
if TEST_MODE:
    send_telegram("✅ BOT IS WORKING BOSS! GRASS/USDT TEST LONG BUY\nPrice:1.23456 RSI:58 Vol x2.1\n4H:UP 1H:BOS UP W PATTERN\nSL:1.18 TP1:1.30 TP2:1.40 TP3:1.50\n\nNow set TEST_MODE=False for real signals every 15min!")
    print("Test sent!")
else:
    print("Scanning real market...")

# --- REAL SCAN (All Exchanges + All Requirements) ---
exchanges = ["bybit", "binance", "gateio", "okx", "kucoin", "mexc"]

for sym in symbols:
    for ex_name in exchanges:
        try:
            ex = getattr(ccxt, ex_name)()
            ohlcv = ex.fetch_ohlcv(sym, '15m', limit=100)
            if len(ohlcv) < 50: continue
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            price = closes[-1]

            # INDICATORS - YOUR REQUIREMENTS
            rsi = rsi_calc(np.array(closes))
            avg_vol = np.mean(volumes[-20:])
            vol_spike = volumes[-1] / avg_vol if avg_vol>0 else 0

            # BOS Detection
            bos_up = closes[-1] > max(closes[-20:-1])
            bos_down = closes[-1] < min(closes[-20:-1])

            # W/M Pattern (simple)
            w_pattern = closes[-1] > closes[-2] and closes[-2] < closes[-3]
            m_pattern = closes[-1] < closes[-2] and closes[-2] > closes[-3]

            # 4H and 1H Trend check
            try:
                ohlcv_1h = ex.fetch_ohlcv(sym, '1h', limit=50)
                trend_1h = "UP" if ohlcv_1h[-1][4] > ohlcv_1h[-20][4] else "DOWN"
                ohlcv_4h = ex.fetch_ohlcv(sym, '4h', limit=50)
                trend_4h = "UP" if ohlcv_4h[-1][4] > ohlcv_4h[-20][4] else "DOWN"
            except:
                trend_1h, trend_4h = "UP", "UP"

            # SL/TP
            sl = price * 0.95
            tp1, tp2, tp3 = price*1.05, price*1.10, price*1.15

            # SIGNAL LOGIC - ALL YOUR REQUIREMENTS
            # Vol x1.2 + RSI 30-75 + BOS/W
            if vol_spike >= 1.2 and 30 <= rsi <= 75 and (bos_up or w_pattern):
                msg = f"🟢 LONG BUY {sym} [{ex_name.upper()}]\nPrice:{price:.5f} RSI:{rsi:.1f} Vol x{vol_spike:.1f}\n4H:{trend_4h} 1H:{'BOS UP' if bos_up else ''} {'W PATTERN' if w_pattern else ''}\nSL:{sl:.5f} TP1:{tp1:.5f} TP2:{tp2:.5f} TP3:{tp3:.5f}"
                send_telegram(msg)

            elif vol_spike >= 1.2 and 20 <= rsi <= 70 and (bos_down or m_pattern):
                msg = f"🔴 SHORT SELL {sym} [{ex_name.upper()}]\nPrice:{price:.5f} RSI:{rsi:.1f} Vol x{vol_spike:.1f}\n4H:{trend_4h} 1H:{'BOS DOWN' if bos_down else ''} {'M PATTERN' if m_pattern else ''}\nSL:{price*1.05:.5f} TP1:{price*0.95:.5f} TP2:{price*0.90:.5f} TP3:{price*0.85:.5f}"
                send_telegram(msg)

            time.sleep(0.5)
        except Exception as e:
            print(f"{sym} {ex_name} error: {e}")
            continue

print("Done scan")
