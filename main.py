import ccxt, requests, numpy as np, pandas as pd

BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"
symbols = ["GRASS/USDT", "KOMA/USDT", "HEI/USDT", "SIREN/USDT", "LAB/USDT", "VELVET/USDT"]
TEST_MODE = False

# ALL EXCHANGES LIST
exchanges_list = {
    "binance": ccxt.binance(),
    "bybit": ccxt.bybit(),
    "okx": ccxt.okx(),
    "kucoin": ccxt.kucoin(),
    "gate": ccxt.gate(),
    "mexc": ccxt.mexc()
}

def send_telegram(msg):
    try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}", timeout=10)
    except: pass

def get_rsi(prices, period=14):
    deltas = np.diff(prices); ups = deltas.clip(min=0); downs = -1*deltas.clip(max=0)
    ma_up = pd.Series(ups).rolling(period).mean().iloc[-1]
    ma_down = pd.Series(downs).rolling(period).mean().iloc[-1]
    if ma_down == 0: return 50
    rs = ma_up/ma_down; return 100 - (100/(1+rs))

for sym in symbols:
    best_price = 0; best_data = None; best_exchange = ""

    # CHECK ALL EXCHANGES FOR THIS COIN
    for ex_name, ex in exchanges_list.items():
        try:
            ohlcv_15m = ex.fetch_ohlcv(sym, '15m', limit=50)
            if not ohlcv_15m: continue
            price = ohlcv_15m[-1][4]
            if price > best_price: # or use volume to find most active
                best_price = price
                best_data = ohlcv_15m
                best_exchange = ex_name
        except: continue

    if not best_data:
        print(f"{sym} not found on any exchange"); continue

    try:
        # Use best exchange data for analysis
        ex = exchanges_list[best_exchange]
        ohlcv_4h = ex.fetch_ohlcv(sym, '4h', limit=50)
        ohlcv_1h = ex.fetch_ohlcv(sym, '1h', limit=50)
        ohlcv_15m = best_data
        df15 = pd.DataFrame(ohlcv_15m)
        price = df15[4].iloc[-1]; closes_4h = [x[4] for x in ohlcv_4h]; closes_1h = [x[4] for x in ohlcv_1h]

        dir_4h = "UP" if closes_4h[-1] > np.mean(closes_4h[-20:]) else "DOWN"
        struct_1h = "BOS UP" if closes_1h[-1] > max(closes_1h[-20:-1]) else "BOS DOWN" if closes_1h[-1] < min(closes_1h[-20:-1]) else "RANGE"
        rsi_15m = get_rsi(df15[4].values)
        vol = df15[5].values; vol_mult = vol[-1] / np.mean(vol[-20:-1]) if np.mean(vol[-20:-1])>0 else 1
        vol_ok = vol_mult >= 1.2
        lows = df15[3].values[-10:]; highs = df15[2].values[-10:]
        pattern = "W PATTERN" if lows[-1] > lows[-5] else "M PATTERN" if highs[-1] < highs[-5] else "NO PATTERN"

        # ATR MATH
        highs_all = df15[2].values; lows_all = df15[3].values; closes_all = df15[4].values
        tr_list = [max(highs_all[i]-lows_all[i], abs(highs_all[i]-closes_all[i-1]), abs(lows_all[i]-closes_all[i-1])) for i in range(1,len(closes_all))]
        atr = np.mean(tr_list[-14:]); swing_low = np.min(lows_all[-10:]); swing_high = np.max(highs_all[-10:])

        msg = None
        if TEST_MODE and sym == "GRASS/USDT":
            msg = f"✅ TEST {sym} on {best_exchange.upper()} Price:{price:.5f} RSI:{rsi_15m:.1f}"

        elif dir_4h == "UP" and ("BOS UP" in struct_1h or "W" in pattern):
            if rsi_15m > 30 and rsi_15m < 75 and vol_ok:
                sl = swing_low - atr*0.5; risk = price-sl
                if risk<=0: risk=price*0.03
                tp1=price+risk*1.5; tp2=price+risk*3; tp3=price+risk*5
                msg = f"🟢 LONG BUY {sym} [{best_exchange.upper()}]\nPrice:{price:.5f} RSI:{rsi_15m:.1f} Vol x{vol_mult:.1f}\n4H:{dir_4h} 1H:{struct_1h} {pattern}\nSL:{sl:.5f} TP1:{tp1:.5f} TP2:{tp2:.5f} TP3:{tp3:.5f}"

        elif dir_4h == "DOWN" and ("BOS DOWN" in struct_1h or "M" in pattern):
            if rsi_15m > 20 and rsi_15m < 70 and vol_ok:
                sl = swing_high + atr*0.5; risk = sl-price
                if risk<=0: risk=price*0.03
                tp1=price-risk*1.5; tp2=price-risk*3; tp3=price-risk*5
                msg = f"🔴 SHORT SELL {sym} [{best_exchange.upper()}]\nPrice:{price:.5f} RSI:{rsi_15m:.1f} Vol x{vol_mult:.1f}\n4H:{dir_4h} 1H:{struct_1h} {pattern}\nSL:{sl:.5f} TP1:{tp1:.5f} TP2:{tp2:.5f} TP3:{tp3:.5f}"

        if msg: print(msg); send_telegram(msg)
        else: print(f"{sym} NO SIGNAL on {best_exchange} | RSI:{rsi_15m:.0f} Vol:{vol_ok}")

    except Exception as e: print(f"{sym} Error {e}")
