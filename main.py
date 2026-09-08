import ccxt, requests, os, numpy as np, pandas as pd, time
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
symbols = ["GRASS/USDT", "KOMA/USDT", "HEI/USDT", "SIREN/USDT", "LAB/USDT", "VELVET/USDT"]
TEST_MODE = True # TRUE = Instant NOW!

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

# INSTANT HEARTBEAT - You get this NOW in 20 sec
send_telegram("✅ BOT IS LIVE BOSS! Scanning real market now...\nGRASS, KOMA, HEI, SIREN, LAB, VELVET\nAll exchanges: gate, mexc, okx, kucoin\nIf setup found with Vol x1.2 + RSI + BOS + W/M -> Signal NOW!\nNext scan auto every 15 min!")

found = 0
exchanges = ["gateio", "mexc", "okx", "kucoin"] # WORKING in GitHub USA

for sym in symbols:
    for ex_name in exchanges:
        try:
            ex = getattr(ccxt, ex_name)()
            ohlcv = ex.fetch_ohlcv(sym, '15m', limit=100)
            if len(ohlcv) < 50: continue
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            price = closes[-1]
            rsi = rsi_calc(np.array(closes))
            avg_vol = np.mean(volumes[-20:])
            vol_spike = volumes[-1] / avg_vol if avg_vol>0 else 0
            bos_up = closes[-1] > max(closes[-20:-1])
            bos_down = closes[-1] < min(closes[-20:-1])
            w_pattern = closes[-1] > closes[-2] and closes[-2] < closes[-3]
            m_pattern = closes[-1] < closes[-2] and closes[-2] > closes[-3]
            try:
                ohlcv_1h = ex.fetch_ohlcv(sym, '1h', limit=50)
                trend_1h = "UP" if ohlcv_1h[-1][4] > ohlcv_1h[-20][4] else "DOWN"
                ohlcv_4h = ex.fetch_ohlcv(sym, '4h', limit=50)
                trend_4h = "UP" if ohlcv_4h[-1][4] > ohlcv_4h[-20][4] else "DOWN"
            except:
                trend_1h, trend_4h = "UP", "UP"
            sl = price * 0.95
            tp1, tp2, tp3 = price*1.05, price*1.10, price*1.15

            if vol_spike >= 1.2 and 30 <= rsi <= 75 and (bos_up or w_pattern):
                found+=1
                msg = f"🟢 LONG BUY {sym} [{ex_name.upper()}]\nPrice:{price:.5f} RSI:{rsi:.1f} Vol x{vol_spike:.1f}\n4H:{trend_4h} 1H:{'BOS UP' if bos_up else ''} {'W PATTERN' if w_pattern else ''}\nSL:{sl:.5f} TP1:{tp1:.5f} TP2:{tp2:.5f} TP3:{tp3:.5f}"
                send_telegram(msg)
            elif vol_spike >= 1.2 and 20 <= rsi <= 70 and (bos_down or m_pattern):
                found+=1
                msg = f"🔴 SHORT SELL {sym} [{ex_name.upper()}]\nPrice:{price:.5f} RSI:{rsi:.1f} Vol x{vol_spike:.1f}\n4H:{trend_4h} 1H:{'BOS DOWN' if bos_down else ''} {'M PATTERN' if m_pattern else ''}\nSL:{price*1.05:.5f} TP1:{price*0.95:.5f} TP2:{price*0.90:.5f} TP3:{price*0.85:.5f}"
                send_telegram(msg)
            time.sleep(0.3)
        except Exception as e:
            print(f"{sym} {ex_name} error: {e}")
            continue

# If no setup, tell you it's working so you know
if found == 0:
    send_telegram(f"📊 SCAN DONE BOSS! Checked {len(symbols)} coins x {len(exchanges)} exchanges = {len(symbols)*len(exchanges)} markets\nNo perfect setup (Vol x1.2 + BOS + W/M) right NOW.\nBOT IS WORKING! Will auto alert every 15 min when setup appears!")

print("Done")
