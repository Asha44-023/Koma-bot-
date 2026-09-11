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
AUTOPILOT = True # BOTH signals + autopilot ON

def ge():
    ex=ccxt.mexc({'apiKey':os.getenv("MEXC_API_KEY"),'secret':os.getenv("MEXC_API_SECRET") or os.getenv("MEXC_SECRET"),'enableRateLimit':True})
    ex2=ccxt.mexc({'enableRateLimit':True})
    return ex, ex2

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
    vol_ratio=buy_vol/sell_vol if buy_vol>sell_vol else sell_vol/buy_vol
    if bullish>=7 and buy_vol>sell_vol*1.3 and mom>0.8 and closes.iloc[-1]>ema20:
        return "MARKET_BUYING", True, bullish, vol_ratio, mom
    if bullish<=3 and sell_vol>buy_vol*1.3 and mom<-0.8 and closes.iloc[-1]<ema20:
        return "MARKET_DUMPING", False, bullish, vol_ratio, mom
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
        if df['low'].tail(10).min() < df['low'].iloc[-20:-10].min(): bull+=10; re.append("BULL_OB")
        if df['high'].tail(10).max() > df['high'].iloc[-20:-10].max(): bear+=10; re.append("BEAR_OB")
        if df['low'].iloc[-1] < df['low'].iloc[-20:-1].min() and df['close'].iloc[-1] > df['low'].iloc[-20:-1].min(): bull+=15; re.append("TURTLE_LONG")
        if df['high'].iloc[-1] > df['high'].iloc[-20:-1].max() and df['close'].iloc[-1] < df['high'].iloc[-20:-1].max(): bear+=15; re.append("TURTLE_SHORT")
        if df['low'].iloc[-1] > df['high'].iloc[-3]: bull+=10; re.append("BULL_FVG")
        if df['high'].iloc[-1] < df['low'].iloc[-3]: bear+=10; re.append("BEAR_FVG")
        if df['low'].iloc[-1] < df['low'].iloc[-10:-1].min() and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5 and df['close'].iloc[-1] > df['low'].iloc[-10:-1].min(): bull+=30; re.append("LIQ_SWEEP_LONG")
        if df['high'].iloc[-1] > df['high'].iloc[-10:-1].max() and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5 and df['close'].iloc[-1] < df['high'].iloc[-10:-1].max(): bear+=30; re.append("LIQ_SWEEP_SHORT")
        w,m=w_m_pattern(df)
        if w: bull+=25; re.append("W_PATTERN")
        if m: bear+=25; re.append("M_PATTERN")
        bk=breakout(df)
        if bk=="LONG_BREAK": bull+=30; re.append("BREAKOUT_LONG")
        if bk=="SHORT_BREAK": bear+=30; re.append("BREAKOUT_SHORT")
        rs=rsi(df['close']).iloc[-1]
        if rs<30: bull+=15; re.append(f"RSI_{rs:.0f}_OS")
        if rs>70: bear+=15; re.append(f"RSI_{rs:.0f}_OB")
        c1=df['close'].iloc[-3]; c2=df['close'].iloc[-2]; c3=df['close'].iloc[-1]
        v1=df['vol'].iloc[-3]; v2=df['vol'].iloc[-2]; v3=df['vol'].iloc[-1]
        if v2>v1*2 and v2>v3*2:
            if c2<c1 and c2<c3: fake.append("WHALE_FAKE_DOWN")
            if c2>c1 and c2>c3: fake.append("WHALE_FAKE_UP")
    except: pass
    return bull,bear,re,fake

def get_bal(ex):
    try:
        bal=ex.fetch_balance()
        usdt=bal['USDT']['free'] if 'USDT' in bal else START_BAL
        return float(usdt) if usdt>0.5 else START_BAL
    except: return START_BAL

def main():
    ex_trade, ex_data = ge()
    bal=get_bal(ex_trade)
    need=TARGET/bal
    print(f"BOTH SIGNALS + AUTOPILOT BAL ${bal:.2f} -> ${TARGET} {datetime.utcnow()}")
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
        status, is_buying, bull_cnt, vol_ratio, mom = market_direction(df)
        re.append(status)
        total=50+max(bull,bear)
        if total<70: continue
        typ="LONG" if bull>bear else "SHORT" if bear>bull else None
        if not typ: continue
        if typ=="SHORT" and is_buying==True: continue
        if typ=="LONG" and is_buying==False: continue
        key=f"{sym}_{typ}"
        if key in ca and (datetime.utcnow()-ca[key])<timedelta(minutes=60): continue
        price=df['close'].iloc[-1]
        fmt=".6f" if price<0.10 else ".4f"
        # === SIGNAL ===
        tg(f"📢 SIGNAL: {'BUY' if typ=='LONG' else 'SELL'} {sym} {typ} ({total})\nPrice {price:{fmt}} {status}\nReasons {', '.join(re[:5])} {' '.join(fake)}\nBal ${bal:.2f} -> ${TARGET} Need {need:.0f}x LEV {LEVERAGE}x")
        if AUTOPILOT:
            try:
                amt=bal*0.95
                try: ex_trade.set_leverage(LEVERAGE, sym)
                except: pass
                ex_trade.create_order(sym,'market',"buy" if typ=="LONG" else "sell",None,None,{'quoteOrderQty':amt})
                tg(f"🤖 AUTOPILOT EXECUTED: {sym} {typ} {LEVERAGE}x ${amt:.2f} ✅")
            except Exception as e: tg(f"⚠️ AUTOPILOT FAILED {sym} {e}")
        ca[key]=datetime.utcnow()
        with open(CF,"w") as f: json.dump({k:v.isoformat() for k,v in ca.items()},f)
        if key not in tr:
            tr[key]={"entry":price,"type":typ,"bal":bal}
            with open(TF,"w") as f: json.dump(tr,f)

    for key,data in list(tr.items()):
        sym=next((s for s in SYMBOLS if s.split("/")[0] in key), None)
        if not sym: continue
        df=fs(ex_data,sym,"15m",200)
        if df is None: continue
        now_p=df['close'].iloc[-1]
        pnl=(now_p-data["entry"])/data["entry"]*100 if data["type"]=="LONG" else (data["entry"]-now_p)/data["entry"]*100
        acct_pnl=pnl*LEVERAGE
        new_bal=bal*(1+acct_pnl/100)
        status, is_buying, bull_cnt, vol_ratio, mom = market_direction(df)
        vol_now=df['vol'].iloc[-1]; vol_prev=df['vol'].iloc[-2]; vol_avg=df['vol'].iloc[-20:-1].mean()
        vol_chg=(vol_now-vol_prev)/vol_prev*100 if vol_prev>0 else 0
        vol_vs_avg=vol_now/vol_avg if vol_avg>0 else 1
        amt=bal*0.95

        signal_msg=None
        should_flip=False

        if acct_pnl>=TP_PCT*LEVERAGE:
            signal_msg=f"📢 SIGNAL: TAKE PROFIT {sym} {data['type']}\nPrice {pnl:.1f}% Acct +{acct_pnl:.1f}% ${bal:.2f}->{new_bal:.2f}\n{status} Vol {vol_chg:.0f}%"
            should_flip=True
        elif acct_pnl<=-SL_PCT*LEVERAGE:
            signal_msg=f"📢 SIGNAL: EXIT MARKET SL {sym} Acct {acct_pnl:.1f}%"
            tg(signal_msg)
            if AUTOPILOT:
                try:
                    ex_trade.create_order(sym,'market',"sell" if data["type"]=="LONG" else "buy",None,None,{'quoteOrderQty':amt})
                    tg(f"🤖 AUTOPILOT CLOSED SL {sym} ✅")
                    tr.pop(key,None)
                except: pass
            continue
        elif data["type"]=="LONG":
            if is_buying==True and vol_chg>20 and vol_vs_avg>1.3 and pnl>0:
                signal_msg=f"📢 SIGNAL: HOLD {sym} LONG\n{status} {bull_cnt}/10 Vol UP {vol_chg:.0f}% x{vol_vs_avg:.1f} Acct +{acct_pnl:.1f}% ${new_bal:.2f} => STAY"
            elif is_buying==False and vol_chg<-25 and pnl>0.8:
                signal_msg=f"📢 SIGNAL: TAKE PROFIT 50% {sym} LONG\n{status} Vol DOWN {vol_chg:.0f}% Acct +{acct_pnl:.1f}% => BOOK 50%"
            elif is_buying==False and vol_vs_avg>2.2:
                signal_msg=f"📢 SIGNAL: EXIT + FLIP {sym} LONG -> SHORT\n{status} DUMPING Vol SPIKE x{vol_vs_avg:.1f} Acct {acct_pnl:.1f}%"
                should_flip=True
        else:
            if is_buying==False and vol_chg>20 and vol_vs_avg>1.3 and pnl>0:
                signal_msg=f"📢 SIGNAL: HOLD {sym} SHORT\n{status} {bull_cnt}/10 Vol UP {vol_chg:.0f}% x{vol_vs_avg:.1f} Acct +{acct_pnl:.1f}% => STAY"
            elif is_buying==True and vol_chg<-25 and pnl>0.8:
                signal_msg=f"📢 SIGNAL: TAKE PROFIT 50% {sym} SHORT\n{status} Vol DOWN {vol_chg:.0f}% Acct +{acct_pnl:.1f}% => BOOK 50%"
            elif is_buying==True and vol_vs_avg>2.2:
                signal_msg=f"📢 SIGNAL: EXIT + FLIP {sym} SHORT -> LONG\n{status} PUMPING Vol SPIKE x{vol_vs_avg:.1f} Acct {acct_pnl:.1f}%"
                should_flip=True

        if signal_msg:
            tg(signal_msg)
            if AUTOPILOT and should_flip:
                tg(f"🤖 AUTOPILOT: Closing {sym} {data['type']} and flipping at junction...")
                try:
                    ex_trade.create_order(sym,'market',"sell" if data["type"]=="LONG" else "buy",None,None,{'quoteOrderQty':amt})
                    flip_side="buy" if data["type"]=="SHORT" else "sell"
                    new_type="LONG" if data["type"]=="SHORT" else "SHORT"
                    try: ex_trade.set_leverage(LEVERAGE, sym)
                    except: pass
                    ex_trade.create_order(sym,'market',flip_side,None,None,{'quoteOrderQty':amt})
                    tg(f"🤖 AUTOPILOT EXECUTED FLIP {sym} {data['type']}->{new_type} {LEVERAGE}x New Bal ~${new_bal:.2f} ✅")
                    tr.pop(key,None)
                    new_key=f"{sym}_{new_type}"
                    tr[new_key]={"entry":now_p,"type":new_type,"bal":new_bal}
                    with open(TF,"w") as f: json.dump(tr,f)
                    ca[new_key]=datetime.utcnow()
                    with open(CF,"w") as f: json.dump({k:v.isoformat() for k,v in ca.items()},f)
                except Exception as e: tg(f"⚠️ FLIP FAILED {e}")
            elif AUTOPILOT and "HOLD" in signal_msg:
                tg(f"🤖 AUTOPILOT: Holding position, no action ✅ Bal ${new_bal:.2f}")

if __name__=="__main__":
    main()
