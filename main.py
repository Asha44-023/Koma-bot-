import os, requests, math

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
print(f"TOKEN SET? {bool(TOKEN)}")

def send(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(e)

# === CONFIG - YOUR EXACT REQUIREMENTS ===
SYMBOLS = ["HEIUSDT", "LABUSDT", "SIRENUSDT", "GRASSUSDT", "KOMAUSDT", "VELVETUSDT"]

def get_mexc_klines(symbol, interval, limit=100):
    # MEXC API - works for your coins
    try:
        url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        # MEXC returns [openTime, open, high, low, close, volume...]
        return r
    except:
        # Fallback to KuCoin
        ku_interval = {"5m":"5min","15m":"15min","1h":"1hour","4h":"4hour"}[interval]
        url = f"https://api.kucoin.com/api/v1/market/candles?symbol={symbol.replace('USDT','-USDT')}&type={ku_interval}"
        r = requests.get(url, timeout=10).json()
        data = r.get('data', [])
        data.reverse()
        # Convert to MEXC format
        return [[float(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in data]

def ema(prices, period):
    k = 2/(period+1)
    ema_vals = [sum(prices[:period])/period]
    for p in prices[period:]:
        ema_vals.append(p*k + ema_vals[-1]*(1-k))
    return ema_vals

def rsi(prices, period=14):
    deltas = [prices[i]-prices[i-1] for i in range(1,len(prices))]
    gains = [d if d>0 else 0 for d in deltas]
    losses = [-d if d<0 else 0 for d in deltas]
    avg_gain = sum(gains[:period])/period
    avg_loss = sum(losses[:period])/period
    if avg_loss==0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def detect_patterns(highs, lows, closes):
    patterns = []
    # Double Top
    if highs[-1] < highs[-2] and highs[-3] < highs[-2] and abs(highs[-2]-highs[-4]) < highs[-2]*0.01:
        patterns.append("DOUBLE TOP 🔴")
    # Double Bottom
    if lows[-1] > lows[-2] and lows[-3] > lows[-2] and abs(lows[-2]-lows[-4]) < lows[-2]*0.01:
        patterns.append("DOUBLE BOTTOM 🟢")
    # Triple Top/Bottom
    if abs(highs[-1]-highs[-3])<highs[-1]*0.008 and abs(highs[-3]-highs[-5])<highs[-1]*0.008 and highs[-2]<highs[-1]:
        patterns.append("TRIPLE TOP 🔴")
    if abs(lows[-1]-lows[-3])<lows[-1]*0.008 and abs(lows[-3]-lows[-5])<lows[-1]*0.008 and lows[-2]>lows[-1]:
        patterns.append("TRIPLE BOTTOM 🟢")
    return patterns

def check_bos(highs, lows):
    # Break of Structure
    if highs[-1] > max(highs[-10:-1]):
        return "BOS BULLISH 🟢 - Breaks last High"
    if lows[-1] < min(lows[-10:-1]):
        return "BOS BEARISH 🔴 - Breaks last Low"
    return None

# === MAIN SCAN ===
send("🤖 *KOMA SNIPER v2 Started*\nScanning HEI,LAB,SIREN,GRASS,KOMA,VELVET\n5m/15m Entry + 1H Structure + 4H Direction")

for symbol in SYMBOLS:
    try:
        k_5m = get_mexc_klines(symbol, "5m", 100)
        k_15m = get_mexc_klines(symbol, "15m", 100)
        k_1h = get_mexc_klines(symbol, "1h", 100)
        k_4h = get_mexc_klines(symbol, "4h", 100)

        if not k_5m or len(k_5m)<50: continue

        c_5m = [float(x[4]) for x in k_5m]
        h_5m = [float(x[2]) for x in k_5m]
        l_5m = [float(x[3]) for x in k_5m]
        v_5m = [float(x[5]) for x in k_5m]

        c_15m = [float(x[4]) for x in k_15m]
        c_1h = [float(x[4]) for x in k_1h]
        c_4h = [float(x[4]) for x in k_4h]

        # Indicators
        ema9_15 = ema(c_15m, 9)[-1]
        ema21_15 = ema(c_15m, 21)[-1]
        ema50_1h = ema(c_1h, 50)[-1]
        ema200_4h = ema(c_4h, 200)[-1] if len(c_4h)>=200 else ema(c_4h, 50)[-1]
        rsi_15 = rsi(c_15m)
        rsi_1h = rsi(c_1h)

        price = c_5m[-1]
        avg_vol = sum(v_5m[-20:-1])/19
        curr_vol = v_5m[-1]
        vol_spike = curr_vol / avg_vol if avg_vol>0 else 1

        # Structure
        bos = check_bos(h_5m, l_5m)
        patterns = detect_patterns(h_5m, l_5m, c_5m)

        # 4H Direction
        direction_4h = "BULLISH" if c_4h[-1] > ema200_4h else "BEARISH"
        # 1H Structure
        structure_1h = "BULLISH" if c_1h[-1] > ema50_1h else "BEARISH"

        # === SNIPER ENTRY LOGIC ===
        buy_cond = 0
        sell_cond = 0

        # Conditions for BUY
        if ema9_15 > ema21_15: buy_cond+=1
        if rsi_15 > 45 and rsi_15 < 68: buy_cond+=1
        if structure_1h=="BULLISH": buy_cond+=1
        if direction_4h=="BULLISH": buy_cond+=1
        if vol_spike > 1.2: buy_cond+=1
        if bos and "BULLISH" in bos: buy_cond+=1
        if any("BOTTOM" in p for p in patterns): buy_cond+=1

        # Conditions for SELL
        if ema9_15 < ema21_15: sell_cond+=1
        if rsi_15 < 55 and rsi_15 > 32: sell_cond+=1
        if structure_1h=="BEARISH": sell_cond+=1
        if direction_4h=="BEARISH": sell_cond+=1
        if vol_spike > 1.2: sell_cond+=1
        if bos and "BEARISH" in bos: sell_cond+=1
        if any("TOP" in p for p in patterns): sell_cond+=1

        # PRECISE TP/SL MATH
        atr = sum([h_5m[i]-l_5m[i] for i in range(-14,0)])/14
        if buy_cond >=5: # High precision entry
            sl = price - atr*1.5
            tp1 = price + atr*1.5
            tp2 = price + atr*3
            tp3 = price + atr*4.5
            profit_pct = ((tp2-price)/price)*100
            risk_pct = ((price-sl)/price)*100
            msg = f"🟢 *BUY SIGNAL - {symbol}* 🟢\n\n"
            msg+= f"💰 Entry: `{price:.6f}`\n"
            msg+= f"📉 SL: `{sl:.6f}` (-{risk_pct:.2f}%)\n"
            msg+= f"🎯 TP1: `{tp1:.6f}`\n🎯 TP2: `{tp2:.6f}` (+{profit_pct:.2f}%)\n🎯 TP3: `{tp3:.6f}`\n\n"
            msg+= f"📊 *Analysis:*\n5m/15m: EMA9 {ema9_15:.4f} > EMA21 {ema21_15:.4f} ✅\n"
            msg+= f"1H Structure: {structure_1h} {ema50_1h:.4f}\n"
            msg+= f"4H Direction: {direction_4h} ✅\n"
            msg+= f"RSI 15m: {rsi_15:.1f} | 1H: {rsi_1h:.1f}\n"
            msg+= f"BOS: {bos if bos else 'Consolidation'}\n"
            msg+= f"Pattern: {', '.join(patterns) if patterns else 'EMA Cross + Volume'}\n"
            msg+= f"Volume: {vol_spike:.2f}x {'Spike 🟢' if vol_spike>1.2 else 'Normal'}\n"
            msg+= f"R/R: 1:{(profit_pct/risk_pct):.1f} | Score: {buy_cond}/7 🔥"
            send(msg)

        elif sell_cond >=5:
            sl = price + atr*1.5
            tp1 = price - atr*1.5
            tp2 = price - atr*3
            tp3 = price - atr*4.5
            profit_pct = ((price-tp2)/price)*100
            risk_pct = ((sl-price)/price)*100
            msg = f"🔴 *SELL SIGNAL - {symbol}* 🔴\n\n"
            msg+= f"💰 Entry: `{price:.6f}`\n"
            msg+= f"📈 SL: `{sl:.6f}` (-{risk_pct:.2f}%)\n"
            msg+= f"🎯 TP1: `{tp1:.6f}`\n🎯 TP2: `{tp2:.6f}` (+{profit_pct:.2f}%)\n🎯 TP3: `{tp3:.6f}`\n\n"
            msg+= f"📊 *Analysis:*\n5m/15m: EMA9 {ema9_15:.4f} < EMA21 {ema21_15:.4f} ✅\n"
            msg+= f"1H Structure: {structure_1h}\n4H Direction: {direction_4h}\n"
            msg+= f"RSI 15m: {rsi_15:.1f}\nBOS: {bos}\nPattern: {', '.join(patterns)}\nVolume: {vol_spike:.2f}x\nR/R: 1:{(profit_pct/risk_pct):.1f} | Score: {sell_cond}/7"
            send(msg)

        print(f"{symbol} {price} - B:{buy_cond} S:{sell_cond} - {patterns}")

    except Exception as e:
        print(f"{symbol} error: {e}")

send("✅ Scan Complete Boss!")
