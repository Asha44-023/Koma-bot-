import ccxt, requests, os, json, pandas as pd, numpy as np
from datetime import datetime, timedelta
import time

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
MIN_SCORE = 40
COOLDOWN_FILE = "last_alerts.json"
COOLDOWN_HOURS = 1
SYMBOLS = ["VELVET/USDT", "KOMA/USDT", "GRASS/USDT", "SIREN/USDT", "HEI/USDT", "LAB/USDT"]

def tg(m):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id": CHAT, "text": m, "parse_mode": "Markdown"}, timeout=15)
    except:
        pass

def load_cooldown():
    try:
        with open(COOLDOWN_FILE, "r") as f:
            return {k: datetime.fromisoformat(v) for k,v in json.load(f).items()}
    except:
        return {}

def save_cooldown(d):
    try:
        with open(COOLDOWN_FILE, "w") as f:
            json.dump({k: v.isoformat() for k,v in d.items()}, f)
    except:
        pass

def rsi(c, p=14):
    d = c.diff()
    g = d.where(d>0,0).rolling(p).mean()
    l = -d.where(d<0,0).rolling(p).mean()
    return 100 - (100 / (1 + g/l))

def fetch_safe(ex, sym, tf, lim):
    try:
        o = ex.fetch_ohlcv(sym, tf, limit=lim)
        if not o or len(o)<60:
            return None
        df = pd.DataFrame(o, columns=['ts','open','high','low','close','vol'])
        for col in ['close','high','low','open','vol']:
            df[col]=df[col].astype(float)
        return df
    except:
        return None

def get_exchange():
    try:
        ex = ccxt.mexc({'enableRateLimit': True})
        ex.fetch_ticker("BTC/USDT")
        print("Using MEXC")
        return ex, "MEXC"
    except:
        try:
            ex = ccxt.kucoin({'enableRateLimit': True})
            ex.fetch_ticker("BTC/USDT")
            print("Using KuCoin")
            return ex, "KUCOIN"
        except:
            return ccxt.mexc({'enableRateLimit': True}), "MEXC"

def check_btc(ex):
    try:
        df = fetch_safe(ex, "BTC/USDT", "4h", 50)
        if df is None:
            return "BTC_NEUTRAL"
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]
        if df['close'].iloc[-1] > ema50 > ema200:
            return "BTC_BULL"
        if df['close'].iloc[-1] < ema50 < ema200:
            return "BTC_BEAR"
        return "BTC_NEUTRAL"
    except:
        return "BTC_NEUTRAL"

def check_liq(df):
    try:
        rh = df['high'].iloc[-20:-1].max()
        rl = df['low'].iloc[-20:-1].min()
        curr = df.iloc[-1]
        if curr['high'] > rh*1.005 and curr['close'] < rh:
            return "LIQ_HUNT_SELL", 20
        if curr['low'] < rl*0.995 and curr['close'] > rl:
            return "LIQ_HUNT_BUY", 20
        return "NO_HUNT", 0
    except:
        return "NO_HUNT", 0

def check_whale(df):
    try:
        avg = df['vol'].iloc[-20:-1].mean()
        curr = df.iloc[-1]
        body = abs(curr['close']-curr['open'])+0.000001
        wu = curr['high'] - max(curr['open'], curr['close'])
        wd = min(curr['open'], curr['close']) - curr['low']
        if curr['vol'] > avg*2.5 and wd > body*1.5:
            return "WHALE_BUY_WICK", 15
        if curr['vol'] > avg*2.5 and wu > body*1.5:
            return "WHALE_SELL_WICK", 15
        return "NO_WHALE", 0
    except:
        return "NO_WHALE", 0

def check_cvd(df):
    try:
        mid = (df['high'].iloc[-1]+df['low'].iloc[-1])/2
        avgv = df['vol'].iloc[-10:-1].mean()
        if df['close'].iloc[-1] < df['close'].iloc[-3] and df['close'].iloc[-1] > mid and df['vol'].iloc[-1] > avgv:
            return "CVD_BULL_DIV", 15
        if df['close'].iloc[-1] > df['close'].iloc[-3] and df['close'].iloc[-1] < mid and df['vol'].iloc[-1] > avgv:
            return "CVD_BEAR_DIV", 15
        return "CVD_NEUTRAL", 0
    except:
        return "CVD_NEUTRAL", 0

def check_hs(df):
    try:
        c = df['close'].iloc[-1]
        neck_high = df['high'].iloc[-15:].max()
        neck_low = df['low'].iloc[-15:].min()
        for i in range(-20, -5):
            ls = df['low'].iloc[i-5:i].min()
            head = df['low'].iloc[i:i+5].min()
            rs = df['low'].iloc[-10:-5].min()
            if head < ls*0.99 and head < rs*0.99 and c > neck_high:
                return "INV_H&S_BULL", 25
            ls2 = df['high'].iloc[i-5:i].max()
            head2 = df['high'].iloc[i:i+5].max()
            rs2 = df['high'].iloc[-10:-5].max()
            if head2 > ls2*1.01 and head2 > rs2*1.01 and c < neck_low:
                return "H&S_BEAR", 25
        return "NO_H&S", 0
    except:
        return "NO_H&S", 0

def check_patterns(df15, df1h):
    score=0
    sigs=[]
    try:
        h = df15['high'].iloc[-15:]
        l = df15['low'].iloc[-15:]
        c = df15['close']
        if l.iloc[2] < l.iloc[5]*0.99 and c.iloc[-1] > c.iloc[-5:-1].max():
            sigs.append("W_PATTERN")
            score+=15
        if h.iloc[2] > h.iloc[5]*0.99 and c.iloc[-1] < c.iloc[-5:-1].min():
            sigs.append("M_PATTERN")
            score+=15
    except:
        pass
    try:
        if df1h['close'].iloc[-1] > df1h['high'].iloc[-20:-1].max():
            sigs.append("BOS_UP")
            score+=15
        if df1h['close'].iloc[-1] < df1h['low'].iloc[-20:-1].min():
            sigs.append("BOS_DOWN")
            score+=15
    except:
        pass
    try:
        if df15['low'].iloc[-1] > df15['high'].iloc[-3]:
            sigs.append("FVG_BULL")
            score+=10
        if df15['high'].iloc[-1] < df15['low'].iloc[-3]:
            sigs.append("FVG_BEAR")
            score+=10
    except:
        pass
    return sigs, score

def calc_sl_tp(entry, sig, df1h):
    try:
        atr = (df1h['high']-df1h['low']).rolling(14).mean().iloc[-1]
        if atr!= atr or atr==0:
            atr=entry*0.02
        if sig=="BUY":
            sl=df1h['low'].iloc[-10:].min()*0.998
            if sl>=entry:
                sl=entry-atr*1.5
            risk=entry-sl
            return sl, entry+risk*1.5, entry+risk*3, entry+risk*5
        else:
            sl=df1h['high'].iloc[-10:].max()*1.002
            if sl<=entry:
                sl=entry+atr*1.5
            risk=sl-entry
            return sl, entry-risk*1.5, entry-risk*3, entry-risk*5
    except:
        return entry*0.98, entry*1.03, entry*1.06, entry*1.10

def main():
    print("=== KILLER FIXED V3 START ===")
    last = load_cooldown()
    ex, ex_name = get_exchange()
    btc_trend = check_btc(ex)
    print(f"Exchange: {ex_name} BTC: {btc_trend}")

    for sym in SYMBOLS:
        if sym in last:
            if datetime.now()-last[sym] < timedelta(hours=COOLDOWN_HOURS):
                continue

        df1h = fetch_safe(ex, sym, "1h", 150)
        if df1h is None:
            try:
                alt = ccxt.kucoin() if ex_name=="MEXC" else ccxt.mexc()
                df1h = fetch_safe(alt, sym, "1h", 150)
                if df1h is not None:
                    ex=alt
                    ex_name="KUCOIN" if ex_name=="MEXC" else "MEXC"
            except:
                pass
        if df1h is None:
            continue

        df15 = fetch_safe(ex, sym, "15m", 150)
        if df15 is None:
            df15 = df1h

        df5 = fetch_safe(ex, sym, "5m", 100)
        if df5 is None:
            df5 = df15

        entry = df5['close'].iloc[-1]
        total=0
        triggers=[]
        sig=None

        triggers.append(ex_name)
        triggers.append(btc_trend)

        hs, hs_s = check_hs(df1h)
        if hs_s>0:
            triggers.append(hs)
            total+=hs_s
            if "BULL" in hs:
                sig="BUY"
            if "BEAR" in hs:
                sig="SELL"

        liq, liq_s = check_liq(df15)
        if liq_s>0:
            triggers.append(liq)
            total+=liq_s
            if "BUY" in liq:
                sig="BUY"
            else:
                sig="SELL"

        whale, whale_s = check_whale(df15)
        if whale_s>0:
            triggers.append(whale)
            total+=whale_s
            if "BUY" in whale:
                sig="BUY"
            else:
                sig="SELL"

        cvd, cvd_s = check_cvd(df15)
        if cvd_s>0:
            triggers.append(cvd)
            total+=cvd_s
            if "BULL" in cvd:
                sig="BUY"
            else:
                sig="SELL"

        mw_sigs, mw_sc = check_patterns(df15, df1h)
        for s in mw_sigs:
            triggers.append(s)
        total+=mw_sc

        if sig is None:
            if "W_PATTERN" in mw_sigs or "BOS_UP" in mw_sigs or "FVG_BULL" in mw_sigs:
                sig="BUY"
            if "M_PATTERN" in mw_sigs or "BOS_DOWN" in mw_sigs or "FVG_BEAR" in mw_sigs:
                sig="SELL"

        r = rsi(df15['close']).iloc[-1]
        if r<30:
            triggers.append("RSI_OS")
            total+=15
            if sig is None:
                sig="BUY"
        if r>70:
            triggers.append("RSI_OB")
            total+=15
            if sig is None:
                sig="SELL"

        if total>100:
            total=100

        print(f"{sym} {total}/100 {sig} {triggers}")

        if total >= MIN_SCORE and sig is not None:
            if btc_trend=="BTC_BEAR" and sig=="BUY" and total<60:
                continue
            sl,tp1,tp2,tp3 = calc_sl_tp(entry, sig, df1h)
            msg = f"🔥 *{sym} {sig} - {total}/100 KILLER ({ex_name})* 🔥\n\nTriggers: {', '.join(triggers[:8])}\nEntry: `{entry:.6f}`\nSL: `{sl:.6f}`\nTP1: `{tp1:.6f}`\nTP2: `{tp2:.6f}`\nTP3: `{tp3:.6f}`\n\n1H Cooldown"
            tg(msg)
            last[sym]=datetime.now()
            save_cooldown(last)

        time.sleep(1.5)

    print("=== SCAN SUCCESS ===")

if __name__ == "__main__":
    main()
