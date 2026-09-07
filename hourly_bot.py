import os, requests
from datetime import datetime, timezone, timedelta

BOT = os.environ['BOT_TOKEN']
CHAT = os.environ['CHAT_ID']
PAIRS = ["KOMAUSDT","HEIUSDT","GRASSUSDT","VELVETUSDT","SIRENUSDT","LABUSDT"]

def get_klines(s, interval, limit=50):
    try:
        r = requests.get(f"https://api.mexc.com/api/v3/klines?symbol={s}&interval={interval}&limit={limit}", timeout=10).json()
        return r
    except: return []

def rsi(closes, p=14):
    if len(closes)<p+1: return 50
    g=l=0
    for i in range(1,p+1):
        d=closes[-i]-closes[-i-1]
        if d>0: g+=d
        else: l+=-d
    if l==0: return 100
    return 100 - (100/(1+g/l))

def ema(closes, per):
    if len(closes)<per: return closes[-1]
    k=2/(per+1); e=closes[0]
    for c in closes: e=c*k+e*(1-k)
    return e

def pattern_detect(k15):
    if len(k15)<15: return "Ranging"
    highs=[float(x[2]) for x in k15[-10:]]; lows=[float(x[3]) for x in k15[-10:]]
    if abs(highs[-1]-highs[-3])<highs[-1]*0.0015 and highs[-1]>=max(highs)*0.998: return "Double Top 🔻"
    if abs(lows[-1]-lows[-3])<lows[-1]*0.0015 and lows[-1]<=min(lows)*1.002: return "Double Bottom 🔺"
    return "Trend"

def bos(k1h):
    if len(k1h)<10: return False,""
    hi=max([float(x[2]) for x in k1h[:-1]]); lo=min([float(x[3]) for x in k1h[:-1]]); cl=float(k1h[-1][4])
    if cl>hi: return True,f"BOS Bullish > {hi:.5f}"
    if cl<lo: return True,f"BOS Bearish < {lo:.5f}"
    return False,"Structure Hold"

EAT = datetime.now(timezone.utc)+timedelta(hours=3)
alerts=[]

for SYM in PAIRS:
    try:
        t24=requests.get(f"https://api.mexc.com/api/v3/ticker/24hr?symbol={SYM}", timeout=10).json()
        price=float(t24['lastPrice']); change=float(t24['priceChangePercent'])*100
        k5=get_klines(SYM,"5m"); k15=get_klines(SYM,"15m"); k1h=get_klines(SYM,"1h"); k4h=get_klines(SYM,"4h")
        if not k15 or not k1h: continue
        c5=[float(x[4]) for x in k5]; c15=[float(x[4]) for x in k15]; c1h=[float(x[4]) for x in k1h]; c4h=[float(x[4]) for x in k4h]
        r15=rsi(c15); r1h=rsi(c1h)
        e9=ema(c15,9); e21=ema(c15,21); e50=ema(c1h,50); e200=ema(c4h,200)
        pat=pattern_detect(k15); bos_ok,bos_txt=bos(k1h)
        dir4h="Bullish" if c4h[-1]>e200 else "Bearish"
        struct1h="Bullish" if c1h[-1]>e50 else "Bearish"
        vol_avg=sum([float(x[5]) for x in k15[-11:-1]])/10; vol_now=float(k15[-1][5])
        vol_spike=vol_now>vol_avg*1.5

        signal="IDLE"; sl=tp1=tp2=0
        if r15>42 and r15<68 and e9>e21 and struct1h=="Bullish" and dir4h=="Bullish" and bos_ok:
            signal="BUY 🟢"; sl=price*0.97; tp1=price*1.04; tp2=price*1.08
        elif r15<32 and vol_spike:
            signal="BUY DIP 🟢"; sl=price*0.96; tp1=price*1.05; tp2=price*1.12
        elif r15>75 or (e9<e21 and struct1h=="Bearish" and bos_ok):
            signal="SELL 🔴"; sl=price*1.03; tp1=price*0.96; tp2=price*0.92

        if signal!="IDLE":
            pct_sl=abs(sl-price)/price*100; pct_tp1=abs(tp1-price)/price*100; pct_tp2=abs(tp2-price)/price*100
            txt=f"#{SYM.replace('USDT','')} {signal}\n💰 ${price:.5f} ({change:+.2f}%)\nRSI 15m:{r15:.0f} 1h:{r1h:.0f} | {pat}\n1H:{struct1h} | {bos_txt}\n4H:{dir4h} | EMA9/21:{'Bull' if e9>e21 else 'Bear'} {'🔥Vol' if vol_spike else ''}\n\n🎯 Entry: ${price:.5f}\n🛑 SL: ${sl:.5f} (-{pct_sl:.1f}%)\n✅ TP1: ${tp1:.5f} (+{pct_tp1:.1f}%)\n🚀 TP2: ${tp2:.5f} (+{pct_tp2:.1f}%)\n"
            alerts.append(txt)
    except: continue

if alerts:
    final=f"🦅 SNIPER ALERT {EAT.strftime('%d %b %H:%M EAT')}\n{'='*24}\n\n" + "\n---\n\n".join(alerts) + "\n\n⚙️ 5m Sniper | 15m Entry | 1H BOS | 4H Dir"
    requests.get(f"https://api.telegram.org/bot{BOT}/sendMessage?chat_id={CHAT}&text={requests.utils.quote(final)}", timeout=15)
