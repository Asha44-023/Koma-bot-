import os, requests, json
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINS = ["KOMAUSDT", "HEIUSDT", "GRASSUSDT", "BTCUSDT", "SOLUSDT", "ETHUSDT"]

def send(t): requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": t, "parse_mode": "Markdown"}, timeout=15)

def get_mexc(s, i):
    try:
        r = requests.get(f"https://api.mexc.com/api/v3/klines?symbol={s}&interval={i}&limit=100", timeout=10).json()
        return [float(x[4]) for x in r], [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[5]) for x in r]
    except: return [],[],[],[]

def get_all_exchanges_price(symbol):
    # Check 3 exchanges for real price
    prices = []
    try:
        # MEXC
        r = requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}", timeout=5).json()
        prices.append(float(r['price']))
    except: pass
    try:
        # Binance
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5).json()
        prices.append(float(r['price']))
    except: pass
    try:
        # Kucoin
        s = symbol.replace("USDT","-USDT")
        r = requests.get(f"https://api.kucoin.com/api/v1/market/stats?symbol={s}", timeout=5).json()
        prices.append(float(r['data']['last']))
    except: pass
    return sum(prices)/len(prices) if prices else 0, prices

def get_rsi(c, p=14):
    if len(c)<p+1: return 50
    g = sum(max(0,c[i]-c[i-1]) for i in range(-p,0))/p
    l = sum(max(0,c[i-1]-c[i]) for i in range(-p,0))/p
    return 100 - (100/(1+g/(l if l!=0 else 0.001)))

def check_news(symbol):
    # NEWS FILTER: If 1H crash > -4% or volume dump = BAD NEWS, skip
    try:
        c1h,_,_,_ = get_mexc(symbol,"60m")
        if len(c1h)<2: return True
        chg = (c1h[-1]-c1h[-2])/c1h[-2]*100
        return chg > -4.0 # True = OK, False = BAD NEWS
    except: return True

def detect_w_m(lows, highs):
    if len(lows)<20: return "NONE"
    l1,l2 = min(lows[-20:-10]), min(lows[-10:])
    h1,h2 = max(highs[-20:-10]), max(highs[-10:])
    if abs(l1-l2)/l1<0.015: return "W PATTERN 🟢"
    if abs(h1-h2)/h1<0.015: return "M PATTERN 🔴"
    return "NONE"

for coin in COINS:
    c5,h5,l5,v5 = get_mexc(coin,"5m")
    c15,h15,l15,v15 = get_mexc(coin,"15m")
    c1h,h1h,l1h,v1h = get_mexc(coin,"1H")
    c4h,h4h,l4h,v4h = get_mexc(coin,"4H")
    if not c15: continue

    avg_price, all_prices = get_all_exchanges_price(coin)
    price = avg_price if avg_price!=0 else c15[-1]
    rsi5, rsi15 = get_rsi(c5), get_rsi(c15)
    pattern = detect_w_m(l15,h15)

    # 4H DIRECTION
    dir4h = "UP" if c4h[-1] > c4h[-25] else "DOWN"
    # 1H STRUCTURE / BOS
    bos_up = price > max(h1h[-20:-1]) if h1h else False
    bos_down = price < min(l1h[-20:-1]) if l1h else False
    struct = "BOS UP" if bos_up else "BOS DOWN" if bos_down else "RANGE"
    # VOLUME
    avg_v = sum(v15[-20:])/20 if v15 else 1
    vol_ok = v15[-1] > avg_v*1.8 if v15 else False
    # NEWS
    news_ok = check_news(coin)

    # 5/15m ENTRY LOGIC
    signal = None
    if dir4h=="UP" and bos_up and 40<=rsi15<=62 and 40<=rsi5<=65 and vol_ok and news_ok and "W" in pattern:
        signal = f"🟢 *LONG {coin}*\n💰 All Exchanges: {', '.join([f'{p:.5f}' for p in all_prices])}\nAvg: {price}\n4H Dir: {dir4h} | 1H Struct: {struct}\n5m RSI:{rsi5:.0f} 15m RSI:{rsi15:.0f} | Vol:x{v15[-1]/avg_v:.1f} ✅\nNews: {'✅ OK' if news_ok else '❌ BAD'}\nPattern: {pattern}\nEntry: 5/15m ✅\nTP1 +1.5% TP2 +3.5% TP3 +6% SL -3%"

    elif dir4h=="DOWN" and bos_down and 38<=rsi15<=60 and vol_ok and news_ok and "M" in pattern:
        signal = f"🔴 *SHORT {coin}*\n💰 All Exchanges: {', '.join([f'{p:.5f}' for p in all_prices])}\nAvg: {price}\n4H Dir: {dir4h} | 1H Struct: {struct}\n5m RSI:{rsi5:.0f} 15m RSI:{rsi15:.0f} | Vol:x{v15[-1]/avg_v:.1f} ✅\nNews: {'✅ OK' if news_ok else '❌ BAD'}\nPattern: {pattern}\nEntry: 5/15m ✅\nTP1 -1.5% TP2 -3.5% TP3 -6% SL +3%"

    if signal: send(signal)
    print(f"{coin} | 4H:{dir4h} 1H:{struct} 5/15m:{rsi5:.0f}/{rsi15:.0f} Vol:{vol_ok} News:{news_ok} {pattern} PriceAvg:{price}")
