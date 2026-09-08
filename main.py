import os, requests
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINS = ["KOMAUSDT", "HEIUSDT", "GRASSUSDT", "BTCUSDT", "SOLUSDT", "ETHUSDT"]

def send(t):
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": t, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def get_mexc(s, interval):
    try:
        # MEXC interval must be lowercase: 5m,15m,60m,4h
        r = requests.get(f"https://api.mexc.com/api/v3/klines?symbol={s}&interval={interval}&limit=80", timeout=10).json()
        if not r or len(r) < 20: return [],[],[],[]
        return [float(x[4]) for x in r], [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[5]) for x in r]
    except: return [],[],[],[]

def get_all_exchanges_price(symbol):
    prices=[]
    try:
        r=requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}", timeout=5).json()
        prices.append(float(r['price']))
    except: pass
    return sum(prices)/len(prices) if prices else 0, prices

def get_rsi(c, p=14):
    if len(c)<p+1: return 50
    g=sum(max(0,c[i]-c[i-1]) for i in range(-p,0))/p
    l=sum(max(0,c[i-1]-c[i]) for i in range(-p,0))/p
    return 100-(100/(1+g/(l if l!=0 else 0.001)))

def detect_w_m(lows, highs):
    if len(lows)<20: return "NONE"
    l1,l2=min(lows[-20:-10]), min(lows[-10:])
    h1,h2=max(highs[-20:-10]), max(highs[-10:])
    if abs(l1-l2)/l1<0.02: return "W PATTERN 🟢"
    if abs(h1-h2)/h1<0.02: return "M PATTERN 🔴"
    return "NONE"

for coin in COINS:
    # FIXED INTERVALS HERE!
    c5,h5,l5,v5 = get_mexc(coin,"5m")
    c15,h15,l15,v15 = get_mexc(coin,"15m")
    c1h,h1h,l1h,v1h = get_mexc(coin,"60m") # FIXED WAS 1H
    c4h,h4h,l4h,v4h = get_mexc(coin,"4h") # FIXED WAS 4H

    if len(c15)<25 or len(c1h)<25 or len(c4h)<25:
        print(f"{coin} SKIP {len(c15)}/{len(c1h)}/{len(c4h)} data short")
        continue

    price, all_prices = get_all_exchanges_price(coin)
    if price==0: price=c15[-1]
    rsi5, rsi15 = get_rsi(c5), get_rsi(c15)
    pattern = detect_w_m(l15,h15)
    dir4h = "UP" if c4h[-1] > c4h[-25] else "DOWN"
    bos_up = price > max(h1h[-20:-1])
    bos_down = price < min(l1h[-20:-1])
    struct = "BOS UP" if bos_up else "BOS DOWN" if bos_down else "RANGE"
    avg_v = sum(v15[-20:])/20
    vol_ok = v15[-1] > avg_v*1.5
    news_ok = (c1h[-1]-c1h[-2])/c1h[-2]*100 > -4

    print(f"{coin} OK | 4H:{dir4h} 1H:{struct} RSI:{rsi15:.0f} Vol:{vol_ok} {pattern} Price:{price}")

    signal=None
    if dir4h=="UP" and bos_up and 40<=rsi15<=65 and vol_ok and "W" in pattern:
        signal=f"🟢 *LONG SNIPER {coin}*\nPrice: {price}\n4H Dir: {dir4h} | 1H Struct: {struct}\nRSI 5m:{rsi5:.0f} 15m:{rsi15:.0f} | Vol x{v15[-1]/avg_v:.1f}\nPattern: {pattern}\nTP1 +1.5% TP2 +3.5% TP3 +6% SL -3%"
    elif dir4h=="DOWN" and bos_down and 35<=rsi15<=62 and vol_ok and "M" in pattern:
        signal=f"🔴 *SHORT SNIPER {coin}*\nPrice: {price}\n4H Dir: {dir4h} | 1H Struct: {struct}\nRSI 5m:{rsi5:.0f} 15m:{rsi15:.0f} | Vol x{v15[-1]/avg_v:.1f}\nPattern: {pattern}\nTP1 -1.5% TP2 -3.5% TP3 -6% SL +3%"

    if signal:
        send(signal)
