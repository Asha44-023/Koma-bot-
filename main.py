import ccxt, requests, os, numpy as np, pandas as pd

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

def tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id":CHAT,"text":m}, timeout=10)
    except:
        pass

def rsi(c,p=14):
    d=np.diff(c); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[-p:]); al=np.mean(l[-p:])
    return 70 if al==0 else 100-(100/(1+ag/al))

def ema(c,p):
    return pd.Series(c).ewm(span=p).mean().iloc[-1]

def atr(o,p=14):
    trs=[]
    for i in range(1,len(o)):
        h=o[i][2]; l=o[i][3]; pc=o[i-1][4]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return np.mean(trs[-p:])

def detect_mw(c):
    last=c[-20:]
    # W Pattern - Double Bottom
    low1=min(last[0:8]); low2=min(last[10:18])
    if last[-1] > last[-3] and abs(low1-low2)/last[-1] < 0.012 and low1 < np.mean(last) and low2 < np.mean(last):
        return "W PATTERN BULLISH"
    # M Pattern - Double Top
    high1=max(last[0:8]); high2=max(last[10:18])
    if last[-1] < last[-3] and abs(high1-high2)/last[-1] < 0.012 and high1 > np.mean(last) and high2 > np.mean(last):
        return "M PATTERN BEARISH"
    return "NO M/W"

# MEXC EXCHANGE
ex = ccxt.mexc()
syms = ["HEI/USDT","LAB/USDT","SIREN/USDT","GRASS/USDT","KOMA/USDT","VELVET/USDT"]

tg("🚀 BOSS MEXC 15M AUTO SCAN START")

for sym in syms:
    try:
        o5=ex.fetch_ohlcv(sym,'5m',limit=100)
        o15=ex.fetch_ohlcv(sym,'15m',limit=100)
        o1h=ex.fetch_ohlcv(sym,'1h',limit=100)
        o4h=ex.fetch_ohlcv(sym,'4h',limit=100)

        c5=[x[4] for x in o5]
        c15=[x[4] for x in o15]
        v15=[x[5] for x in o15]
        price=c15[-1]

        rsi5=rsi(np.array(c5))
        rsi15=rsi(np.array(c15))
        e9=ema(c15,9)
        e21=ema(c15,21)
        a=atr(o15)
        vol=v15[-1]/np.mean(v15[-20:]) if np.mean(v15[-20:])>0 else 1

        # 4H Direction
        trend4h="UP" if o4h[-1][4] > o4h[-20][4] else "DOWN"
        # 1H Structure + BOS
        h1=max([x[4] for x in o1h[-20:-1]])
        l1=min([x[4] for x in o1h[-20:-1]])
        if o1h[-1][4] > h1:
            bos="BOS UP"; struct1h="BULLISH"
        elif o1h[-1][4] < l1:
            bos="BOS DOWN"; struct1h="BEARISH"
        else:
            bos="RANGE"; struct1h="RANGE"

        pattern=detect_mw(c15)

        # SCORE SYSTEM
        buy_score=0; sell_score=0
        if e9>e21: buy_score+=20
        else: sell_score+=20
        if 45<rsi15<68: buy_score+=15
        if 32<rsi15<55: sell_score+=15
        if rsi5>52: buy_score+=10
        if
