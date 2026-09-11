import ccxt, pandas as pd, requests, os, json, time
from datetime import datetime, timedelta

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
CF = "last_alerts.json"
TF = "trades.json"
MIN_SCORE = 75
SYMBOLS = ["VELVET/USDT:USDT","KOMA/USDT:USDT","GRASS/USDT:USDT","SIREN/USDT:USDT","HEI/USDT:USDT","LAB/USDT:USDT"]
last_volume={}; last_monitor_alert={}

def ge():
    ex=ccxt.mexc({'apiKey':os.getenv("MEXC_API_KEY"),'secret':os.getenv("MEXC_SECRET"),'enableRateLimit':True})
    ex2=ccxt.mexc({'enableRateLimit':True})
    return ex, ex2

def gc(s):
    c=s.replace("/","").replace(":USDT","").replace(":","")
    if not c.endswith("USDT"): c+="USDT"
    try:
        r=requests.get(f"https://api.mexc.com/api/v3/ticker/24hr?symbol={c}",timeout=5).json()
        return float(r.get('priceChangePercent',0))
    except: return 0.0

def tg(m):
    try: requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":m,"parse_mode":"Markdown"},timeout=15)
    except: pass

def lc():
    try:
        with open(CF,"r") as f: return {k:datetime.fromisoformat(v) for k,v in json.load(f).items()}
    except: return {}
def sc(d):
    try:
        with open(CF,"w") as f: json.dump({k:v.isoformat() for k,v in d.items()},f)
    except: pass
def lt():
    try:
        with open(TF,"r") as f: return json.load(f)
    except: return {}
def st(d):
    try:
        with open(TF,"w") as f: json.dump(d,f,default=str)
    except: pass

def rsi(c,p=14):
    d=c.diff(); g=d.where(d>0,0).rolling(p).mean(); l=-d.where(d<0,0).rolling(p).mean()
    return 100-(100/(1+g/l))

def fs(ex, sym, tf, lim):
    try:
        o=ex.fetch_ohlcv(sym,tf,limit=lim)
        if not o or len(o)<60: return None
        df=pd.DataFrame(o); df.columns=['ts','open','high','low','close','vol']
        for col in ['close','high','low','open','vol']: df[col]=df[col].astype(float)
        return df
    except: return None

def auto_trade(sym, typ, sl, tp, score):
    try:
        ex,_=ge()
        amt=float(os.getenv("TRADE_AMOUNT","10"))
        # === LIQUIDATION PROTECTION ===
        leverage = 3 # FORCE 3x MAX
        try: ex.set_leverage(leverage, sym)
        except: pass
        side="buy" if typ=="LONG" else "sell"
        ex.create_order(sym,'market',side,None,None,{'quoteOrderQty':amt})
        print(f"💰 MEXC {sym} {typ} ${amt} LEV {leverage}x")
        return True
    except Exception as e:
        print(f"❌ MEXC ERR {e}")
        return False

def btc_t(ex):
    try:
        df=fs(ex,"BTC/USDT","4h",50)
        if df is None: return "BTC_NEUTRAL"
        e50=df['close'].ewm(50).mean().iloc[-1]; e200=df['close'].ewm(200).mean().iloc[-1]; cp=df['close'].iloc[-1]
        if cp>e50>e200: return "BTC_BULL"
        if cp<e50<e200: return "BTC_BEAR"
        return "BTC_NEUTRAL"
    except: return "BTC_NEUTRAL"

def w_pattern_c(df):
    try:
        lows = df['low'].tail(30)
        if len(lows)<20: return "NO_W",0
        l1 = lows.iloc[-20:-10].min()
        l2 = lows.iloc[-10:].min()
        mid_high = df['high'].iloc[-15:-5].max()
        if abs(l1-l2)/l1*100 < 1.5 and df['close'].iloc[-1] > mid_high and df['vol'].iloc[-1] > df['vol'].iloc[-20:-1].mean()*1.3:
            return "W_PATTERN", 30
        if abs(l1-l2)/l1*100 < 2.5: return "W_FORMING", 15
        return "NO_W", 0
    except: return "NO_W", 0

def m_pattern_c(df):
    try:
        highs = df['high'].tail(30)
        if len(highs)<20: return "NO_M",0
        h1 = highs.iloc[-20:-10].max()
        h2 = highs.iloc[-10:].max()
        mid_low = df['low'].iloc[-15:-5].min()
        if abs(h1-h2)/h1*100 < 1.5 and df['close'].iloc[-1] < mid_low and df['vol'].iloc[-1] > df['vol'].iloc[-20:-1].mean()*1.3:
            return "M_PATTERN", 30
        if abs(h1-h2)/h1*100 < 2.5: return "M_FORMING", 15
        return "NO_M", 0
    except: return "NO_M", 0

def score_v8(df, ex):
    bull=bear=0; re=[]; fake=[]
    try:
        if df['low'].tail(10).min() < df['low'].iloc[-20:-10].min(): bull+=10; re.append("BULL_OB")
        if df['high'].tail(10).max() > df['high'].iloc[-20:-10].max(): bear+=10; re.append("BEAR_OB")
        if (df['low'].tail(20).max()-df['low'].tail(20).min())/df['low'].tail(20).min()*100 <0.5: bull+=10; re.append("EQ_LOWS")
        if df['low'].iloc[-1] < df['low'].iloc[-20:-1].min() and df['close'].iloc[-1] > df['low'].iloc[-20:-1].min(): bull+=15; re.append("TURTLE_LONG")
        if df['high'].iloc[-1] > df['high'].iloc[-20:-1].max() and df['close'].iloc[-1] < df['high'].iloc[-20:-1].max(): bear+=15; re.append("TURTLE_SHORT")
        if df['low'].iloc[-1] > df['high'].iloc[-3]: bull+=10; re.append("BULL_FVG")
        if df['high'].iloc[-1] < df['low'].iloc[-3]: bear+=10; re.append("BEAR_FVG")
        if df['low'].iloc[-1] < df['low'].iloc[-10:-1].min() and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5 and df['close'].iloc[-1] > df['low'].iloc[-10:-1].min(): bull+=30; re.append("LIQ_SWEEP_LONG")
        if df['high'].iloc[-1] > df['high'].iloc[-10:-1].max() and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5 and df['close'].iloc[-1] < df['high'].iloc[-10:-1].max(): bear+=30; re.append("LIQ_SWEEP_SHORT")
        w_name, w_pts = w_pattern_c(df)
        if w_pts>0: bull+=w_pts; re.append(w_name)
        m_name, m_pts = m_pattern_c(df)
        if m_pts>0: bear+=m_pts; re.append(m_name)
        rs=rsi(df['close']).iloc[-1]
        if rs<30: bull+=15; re.append(f"RSI_{rs:.0f}_OS")
        if rs>70: bear+=15; re.append(f"RSI_{rs:.0f}_OB")
        bt=btc_t(ex); re.append(bt)
        if bt=="BTC_BULL": bull+=10
        if bt=="BTC_BEAR": bear+=10
        c1=df['close'].iloc[-3]; c2=df['close'].iloc[-2]; c3=df['close'].iloc[-1]
        v1=df['vol'].iloc[-3]; v2=df['vol'].iloc[-2]; v3=df['vol'].iloc[-1]
        if v2>v1*2 and v2>v3*2:
            if c2<c1 and c2<c3: fake.append("WHALE_FAKE_DOWN")
            if c2>c1 and c2>c3: fake.append("WHALE_FAKE_UP")
    except: pass
    return bull,bear,re,fake

def vol_profit_c(df, pnl):
    if pnl<0.8: return "NO_VOL",0,"NONE"
    vp=df['vol'].iloc[-2]; vn=df['vol'].iloc[-1]; va=df['vol'].iloc[-20:-1].mean()
    bull=df['close'].iloc[-1] > df['open'].iloc[-1]
    if vn>vp*1.30 and vn>va: return ("VOLBUYINCREASE",15,"HOLD_LONG") if bull else ("VOLSELLINCREASE",15,"HOLD_SHORT")
    if vn<vp*0.70: return ("VOLBUYDECREASE",0,"TP_LONG") if bull else ("VOLSELLDECREASE",0,"TP_SHORT")
    return "NO_VOL",0,"NONE"

def main():
    print(f"🚀 ANTI-TRAP BOT W+M {datetime.utcnow()}")
    ex_trade, ex_data = ge()
    ca=lc(); tr=lt(); now=datetime.utcnow()
    for sym in SYMBOLS:
        try:
            df=fs(ex_data,sym,"15m",200)
            if df is None: continue
            if df['vol'].iloc[-5:].mean() < df['vol'].rolling(20).mean().iloc[-1]*1.2: continue
            bull,bear,re,fake=score_v8(df, ex_data)
            total=50+max(bull,bear)
            if total<MIN_SCORE: continue
            typ="LONG" if bull>bear else "SHORT" if bear>bull else None
            if not typ: continue
            if len(fake)>0: continue

            # === ANTI PUMP/DUMP TRAP ===
            w_name, w_pts = w_pattern_c(df)
            m_name, m_pts = m_pattern_c(df)
            ema20 = df['close'].ewm(20).mean().iloc[-1]

            if typ=="SHORT" and w_pts>0:
                print(f"🚫 BLOCK SHORT {sym} - {w_name} forming, will pump!")
                continue
            if typ=="LONG" and m_pts>0:
                print(f"🚫 BLOCK LONG {sym} - {m_name} forming, will dump!")
                continue
            if typ=="SHORT" and df['close'].iloc[-1] > ema20:
                print(f"🚫 BLOCK SHORT {sym} - above EMA20, bear trap")
                continue
            if typ=="LONG" and df['close'].iloc[-1] < ema20:
                print(f"🚫 BLOCK LONG {sym} - below EMA20, bull trap")
                continue
            # Confirmation candle
            if typ=="SHORT" and df['close'].iloc[-2] > df['open'].iloc[-2]:
                print(f"⏳ WAIT SHORT {sym} - last candle bullish")
                continue
            if typ=="LONG" and df['close'].iloc[-2] < df['open'].iloc[-2]:
                print(f"⏳ WAIT LONG {sym} - last candle bearish")
                continue

            d=gc(sym)
            if d>8 and typ=="SHORT": continue
            if d<-8 and typ=="LONG": continue
            if abs(d)>15: continue

            key=f"{sym}_{typ}"
            if key in ca and (now-ca[key])<timedelta(hours=2): continue
            price=df['close'].iloc[-1]
            sl_pct=0.04 if price<0.10 else 0.03
            tp_pct=0.08 if price<0.10 else 0.06
            sl=price*(1-sl_pct) if typ=="LONG" else price*(1+sl_pct)
            tp=price*(1+tp_pct) if typ=="LONG" else price*(1-tp_pct)
            fmt=".6f" if price<0.10 else ".5f"
            msg=f"{'BUY' if typ=='LONG' else 'SELL'} {sym} {typ} MAX ({total}/100)\nPrice: {price:{fmt}}\nSL: {sl:{fmt}} TP: {tp:{fmt}}\nReasons: {', '.join(re[:8])}\nLEV 3x ONLY"
            tg(msg)
            if auto_trade(sym, typ, sl, tp, total):
                tg(f"🤖 *MEXC EXECUTED 3x* {sym} {typ} ${os.getenv('TRADE_AMOUNT','10')}")
            ca[key]=now; sc(ca)
            if key not in tr: tr[key]={"entry":price,"type":typ,"time":now.isoformat()}; st(tr)
        except Exception as e:
            print(f"ERR {sym} {e}")

    for key,data in list(tr.items()):
        try:
            sym=next((s for s in SYMBOLS if s.split("/")[0] in key), None)
            if not sym: continue
            df=fs(ex_data,sym,"15m",200)
            if df is None: continue
            typ=data["type"]; entry=data["entry"]
            now_p=df['close'].iloc[-1]
            pnl=(now_p-entry)/entry*100 if typ=="LONG" else (entry-now_p)/entry*100
            v_name,_,v_dir=vol_profit_c(df,pnl)
            vol_now=df['vol'].iloc[-1]; vol_prev=last_volume.get(sym,vol_now)
            vol_chg=((vol_now-vol_prev)/vol_prev*100) if vol_prev>0 else 0
            last_volume[sym]=vol_now
            mk=f"MON_{key}_{v_dir}"
            if mk in last_monitor_alert and (datetime.utcnow()-last_monitor_alert[mk])<timedelta(minutes=15): continue
            if v_dir in ["HOLD_LONG","HOLD_SHORT"] and pnl>0:
                tg(f"📊 *HOLD* {sym} {typ} PnL {pnl:.2f}% Vol {vol_chg:.1f}% UP -> HOLD {v_name}"); last_monitor_alert[mk]=datetime.utcnow()
            elif v_dir in ["TP_LONG","TP_SHORT"] and pnl>0.5:
                tg(f"💰 *TAKE 50%* {sym} {typ} PnL {pnl:.2f}% Vol {vol_chg:.1f}% DOWN -> Book 50% {v_name}"); last_monitor_alert[mk]=datetime.utcnow()
            if abs(vol_chg)>100 and -1<pnl<1:
                tg(f"🚪 *EXIT ALL* {sym} {typ} PnL {pnl:.2f}% Vol EXPLOSION -> CLOSE!"); last_monitor_alert[mk]=datetime.utcnow()
        except: continue

if __name__=="__main__":
    main()
