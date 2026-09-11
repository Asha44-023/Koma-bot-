import ccxt, pandas as pd, requests, os, json
from datetime import datetime, timedelta

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
CF = "last_alerts.json"
TF = "trades.json"
SYMBOLS = ["VELVET/USDT:USDT","KOMA/USDT:USDT","GRASS/USDT:USDT","SIREN/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT"]

START_BAL = 14.99
TARGET = 10000.0
LEVERAGE = 10
TP_PCT = 2.0
SL_PCT = 1.2
AUTOPILOT = True

def ge():
    secret = os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET") or os.getenv("API_SECRET")
    ex=ccxt.mexc({'apiKey':os.getenv("MEXC_API_KEY"),'secret':secret,'enableRateLimit':True})
    return ex, ccxt.mexc({'enableRateLimit':True})

def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":m,"parse_mode":"Markdown"},timeout=15)
    except: pass

def fs(ex, sym, tf, lim):
    try:
        o=ex.fetch_ohlcv(sym,tf,limit=lim)
        if not o or len(o)<60: return None
        df=pd.DataFrame(o); df.columns=['ts','open','high','low','close','vol']
        for c in ['close','high','low','open','vol']: df[c]=df[c].astype(float)
        return df
    except: return None

def rsi(c,p=14):
    d=c.diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean()
    return 100-(100/(1+g/l))

def market_direction(df):
    closes=df['close'].tail(10); opens=df['open'].tail(10); vols=df['vol'].tail(10)
    bullish=sum(1 for i in range(-10,0) if closes.iloc[i]>opens.iloc[i])
    buy_vol=sum(vols.iloc[i] for i in range(-10,0) if closes.iloc[i]>opens.iloc[i])
    sell_vol=sum(vols.iloc[i] for i in range(-10,0) if closes.iloc[i]<opens.iloc[i]) or 1
    mom=(closes.iloc[-1]-closes.iloc[-5])/closes.iloc[-5]*100
    ema20=df['close'].ewm(20).mean().iloc[-1]
    if mom>1.5 and buy_vol>sell_vol and closes.iloc[-1]>ema20: return "MARKET_PUMPING", True, bullish, 0, mom
    if bullish>=6 and buy_vol>sell_vol*1.2 and mom>0.5 and closes.iloc[-1]>ema20: return "MARKET_BUYING", True, bullish, 0, mom
    if mom<-1.5 and sell_vol>buy_vol and closes.iloc[-1]<ema20: return "MARKET_DUMPING_HARD", False, bullish, 0, mom
    if bullish<=4 and sell_vol>buy_vol*1.2 and mom<-0.5 and closes.iloc[-1]<ema20: return "MARKET_DUMPING", False, bullish, 0, mom
    return "NEUTRAL", None, bullish, 0, mom

def w_m_pattern(df):
    try:
        l1=df['low'].iloc[-20:-10].min(); l2=df['low'].iloc[-10:].min()
        h1=df['high'].iloc[-20:-10].max(); h2=df['high'].iloc[-10:].max()
        mid_h=df['high'].iloc[-15:-5].max(); mid_l=df['low'].iloc[-15:-5].min()
        w=abs(l1-l2)/l1*100<2.5 and df['close'].iloc[-1]>mid_h
        m=abs(h1-h2)/h1*100<2.5 and df['close'].iloc[-1]<mid_l
        return w,m
    except: return False,False

def breakout(df):
    try:
        price=df['close'].iloc[-1]; high20=df['high'].iloc[-20:-1].max(); low20=df['low'].iloc[-20:-1].min()
        vol_avg=df['vol'].iloc[-20:-1].mean(); vol_now=df['vol'].iloc[-1]
        mom=(price-df['close'].iloc[-5])/df['close'].iloc[-5]*100
        if price>high20 and vol_now>vol_avg*2.0 and mom>1.0: return "LONG_BREAK"
        if price<low20 and vol_now>vol_avg*2.0 and mom<-1.0: return "SHORT_BREAK"
        return None
    except: return None

def score_v8(df):
    bull=bear=0; re=[]; fake=[]
    try:
        closes=df['close']; highs=df['high']; lows=df['low']; vols=df['vol']
        vol_avg=vols.iloc[-20:-1].mean()
        # WHALE ENGINE
        if lows.iloc[-1] < lows.iloc[-20:-1].min() and closes.iloc[-1] > lows.iloc[-20:-1].min() and vols.iloc[-1] > vol_avg*1.8: bull+=35; re.append("LIQ_GRAB_LONG")
        if highs.iloc[-1] > highs.iloc[-20:-1].max() and closes.iloc[-1] < highs.iloc[-20:-1].max() and vols.iloc[-1] > vol_avg*1.8: bear+=35; re.append("LIQ_GRAB_SHORT")
        c1,c2,c3=closes.iloc[-3],closes.iloc[-2],closes.iloc[-1]
        v1,v2,v3=vols.iloc[-3],vols.iloc[-2],vols.iloc[-1]
        if v2>v1*2.5 and v2>v3*2 and c2<c1 and c2<c3: bull+=30; fake.append("WHALE_FAKE_DOWN"); re.append("WHALE_TRAP_LONG")
        if v2>v1*2.5 and v2>v3*2 and c2>c1 and c2>c3: bear+=30; fake.append("WHALE_FAKE_UP"); re.append("WHALE_TRAP_SHORT")
        if vols.iloc[-1] > vol_avg*3 and abs(closes.iloc[-1]-closes.iloc[-2])/closes.iloc[-2]*100 < 0.3:
            fake.append("SPOOFING"); bull+=20 if closes.iloc[-1]<closes.iloc[-2] else 0; bear+=20 if closes.iloc[-1]>closes.iloc[-2] else 0
            re.append("SPOOF_BULL_REV" if closes.iloc[-1]<closes.iloc[-2] else "SPOOF_BEAR_REV")
        pr=highs.iloc[-10:].max()-lows.iloc[-10:].min()
        if pr/closes.iloc[-1]*100 < 1.5 and vols.iloc[-5:].mean() > vol_avg*1.5:
            if closes.iloc[-1] > closes.iloc[-10]: bull+=25; re.append("WHALE_ACCUM_LONG")
            else: bear+=25; re.append("WHALE_DIST_SHORT")
        body=abs(closes.iloc[-1]-df['open'].iloc[-1])
        if body>0:
            up=highs.iloc[-1]-max(closes.iloc[-1],df['open'].iloc[-1]); lo=min(closes.iloc[-1],df['open'].iloc[-1])-lows.iloc[-1]
            if lo>body*2.5 and vols.iloc[-1]>vol_avg*1.5: bull+=20; re.append("STOP_HUNT_LONG")
            if up>body*2.5 and vols.iloc[-1]>vol_avg*1.5: bear+=20; re.append("STOP_HUNT_SHORT")
        if lows.tail(10).min() < lows.iloc[-20:-10].min(): bull+=10; re.append("BULL_OB")
        if highs.tail(10).max() > highs.iloc[-20:-10].max(): bear+=10; re.append("BEAR_OB")
        if lows.iloc[-1] < lows.iloc[-20:-1].min() and closes.iloc[-1] > lows.iloc[-20:-1].min(): bull+=15; re.append("TURTLE_LONG")
        if highs.iloc[-1] > highs.iloc[-20:-1].max() and closes.iloc[-1] < highs.iloc[-20:-1].max(): bear+=15; re.append("TURTLE_SHORT")
        if lows.iloc[-1] > highs.iloc[-3]: bull+=10; re.append("BULL_FVG")
        if highs.iloc[-1] < lows.iloc[-3]: bear+=10; re.append("BEAR_FVG")
        w,m=w_m_pattern(df)
        if w: bull+=25; re.append("W_PATTERN")
        if m: bear+=25; re.append("M_PATTERN")
        bk=breakout(df)
        if bk=="LONG_BREAK": bull+=30; re.append("BREAKOUT_LONG")
        if bk=="SHORT_BREAK": bear+=30; re.append("BREAKOUT_SHORT")
        rs=rsi(df['close']).iloc[-1]
        if rs<30: bull+=15; re.append(f"RSI_{rs:.0f}_OS")
        if rs>70: bear+=15; re.append(f"RSI_{rs:.0f}_OB")
    except: pass
    return bull,bear,re,fake

def get_bal(ex):
    try:
        b=ex.fetch_balance(); return float(b['USDT']['free']) if 'USDT' in b and b['USDT']['free']>0.5 else START_BAL
    except: return START_BAL

def calc_c(price, margin):
    raw=(margin*LEVERAGE)/price
    return int(raw) if raw>10 else round(raw,1) if raw>=1 else 1

def main():
    ex_trade, ex_data = ge()
    bal=get_bal(ex_trade); need=TARGET/bal
    print(f"FINAL WHALE + KOMA PUMP BAL ${bal:.2f} -> ${TARGET} {datetime.utcnow()}")
    try:
        with open(CF,"r") as f: ca={k:datetime.fromisoformat(v) for k,v in json.load(f).items()}
    except: ca={}
    try:
        with open(TF,"r") as f: tr=json.load(f)
    except: tr={}

    for sym in SYMBOLS:
        df=fs(ex_data,sym,"15m",200)
        if df is None: continue
        bull,bear,re,fake=score_v8(df)
        status, is_buying, bull_cnt, vr, mom = market_direction(df)
        re.append(status); total=50+max(bull,bear); typ="LONG" if bull>bear else "SHORT" if bear>bull else None
        if not typ: continue
        if status=="MARKET_PUMPING" and mom>1.5: typ="LONG"; total=max(total,85); re.append("KOMA_PUMP_OVERRIDE")
        if status=="MARKET_DUMPING_HARD" and mom<-1.5: typ="SHORT"; total=max(total,85); re.append("DUMP_OVERRIDE")
        if total<70: continue
        if typ=="SHORT" and is_buying==True and total<90 and "KOMA_PUMP_OVERRIDE" not in re and "WHALE_TRAP_LONG" not in re and "LIQ_GRAB_LONG" not in re: continue
        if typ=="LONG" and is_buying==False and total<90 and "WHALE_TRAP_SHORT" not in re and "LIQ_GRAB_SHORT" not in re: continue
        key=f"{sym}_{typ}"
        if key in ca and (datetime.utcnow()-ca[key])<timedelta(minutes=45): continue
        price=df['close'].iloc[-1]; fmt=".6f" if price<0.10 else ".4f"
        tg(f"📢 SIGNAL: {'BUY' if typ=='LONG' else 'SELL'} {sym} {typ} ({total})\nPrice {price:{fmt}} {status} mom {mom:.1f}%\nReasons {', '.join(re[:5])} Fake:{' '.join(fake)}\nBal ${bal:.2f} -> ${TARGET} Need {need:.0f}x LEV {LEVERAGE}x")
        if AUTOPILOT:
            try:
                amt=bal*0.95;
                try: ex_trade.set_leverage(LEVERAGE, sym)
                except: pass
                c=calc_c(price, amt)
                ex_trade.create_order(sym,'market',"buy" if typ=="LONG" else "sell", c)
                tg(f"🤖 AUTOPILOT EXECUTED: {sym} {typ} {LEVERAGE}x {c} contracts ✅\nEntry {price:{fmt}} Bal ${bal:.2f}")
            except Exception as e: tg(f"⚠️ AUTOPILOT FAILED {sym} {e}")
        ca[key]=datetime.utcnow()
        with open(CF,"w") as f: json.dump({k:v.isoformat() for k,v in ca.items()},f)
        tr[key]={"entry":price,"type":typ,"bal":bal}
        with open(TF,"w") as f: json.dump(tr,f)

    # HOLD / TP / FLIP
    for key,data in list(tr.items()):
        sym=next((s for s in SYMBOLS if s.split("/")[0] in key), None)
        if not sym: continue
        df=fs(ex_data,sym,"15m",200)
        if df is None: continue
        now_p=df['close'].iloc[-1]
        pnl=(now_p-data["entry"])/data["entry"]*100 if data["type"]=="LONG" else (data["entry"]-now_p)/data["entry"]*100
        acct_pnl=pnl*LEVERAGE; new_bal=bal*(1+acct_pnl/100)
        status, is_buying, bull_cnt, vr, mom = market_direction(df)
        vol_now=df['vol'].iloc[-1]; vol_avg=df['vol'].iloc[-20:-1].mean()
        vol_vs_avg=vol_now/vol_avg if vol_avg>0 else 1
        if acct_pnl>=TP_PCT*LEVERAGE:
            tg(f"📢 TAKE PROFIT {sym} {data['type']} +{acct_pnl:.1f}% ${bal:.2f}->{new_bal:.2f}")
            try:
                ex_trade.create_order(sym,'market',"sell" if data["type"]=="LONG" else "buy",None,None,{'reduceOnly':True})
                tr.pop(key,None)
                with open(TF,"w") as f: json.dump(tr,f)
                # flip
                flip="buy" if data["type"]=="SHORT" else "sell"; nt="LONG" if data["type"]=="SHORT" else "SHORT"
                try: ex_trade.set_leverage(LEVERAGE, sym)
                except: pass
                c=calc_c(now_p, bal*0.95)
                ex_trade.create_order(sym,'market',flip,c)
                tg(f"🤖 FLIP {sym} -> {nt} {c}c Bal ${new_bal:.2f} ✅")
                tr[f"{sym}_{nt}"]={"entry":now_p,"type":nt,"bal":new_bal}
                with open(TF,"w") as f: json.dump(tr,f)
            except Exception as e: tg(f"⚠️ FLIP FAILED {e}")
        elif acct_pnl<=-SL_PCT*LEVERAGE:
            tg(f"📢 SL {sym} {acct_pnl:.1f}%")
            try:
                ex_trade.create_order(sym,'market',"sell" if data["type"]=="LONG" else "buy",None,None,{'reduceOnly':True})
                tr.pop(key,None)
                with open(TF,"w") as f: json.dump(tr,f)
                tg(f"🤖 CLOSED SL {sym} ✅")
            except: pass

if __name__=="__main__":
    main()
