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
    try: requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id": CHAT, "text": m, "parse_mode": "Markdown"}, timeout=15)
    except: pass

def load_cooldown():
    try:
        with open(COOLDOWN_FILE, "r") as f: return {k: datetime.fromisoformat(v) for k,v in json.load(f).items()}
    except: return {}
def save_cooldown(d):
    try:
        with open(COOLDOWN_FILE, "w") as f: json.dump({k: v.isoformat() for k,v in d.items()}, f)
    except: pass

def rsi(c, p=14):
    d = c.diff(); g = d.where(d>0,0).rolling(p).mean(); l = -d.where(d<0,0).rolling(p).mean()
    return 100 - (100 / (1 + g/l))

def fetch_safe(ex, sym, tf='1h', lim=150):
    try:
        o = ex.fetch_ohlcv(sym, tf, limit=lim)
        if not o or len(o)<60: return None
        df = pd.DataFrame(o, columns=['ts','open','high','low','close','vol'])
        for col in ['close','high','low','open','vol']: df[col]=df[col].astype(float)
        return df
    except: return None

def get_exchange():
    try:
        ex_mexc = ccxt.mexc({'enableRateLimit': True})
        ex_mexc.fetch_ticker("BTC/USDT")
        print("Using MEXC")
        return ex_mexc, "MEXC"
    except:
        try:
            ex_ku = ccxt.kucoin({'enableRateLimit': True})
            ex_ku.fetch_ticker("BTC/USDT")
            print("Using KuCoin")
            return ex_ku, "KUCOIN"
        except:
            return ccxt.mexc({'enableRateLimit': True}), "MEXC"

def check_btc_filter(ex):
    try:
        df = fetch_safe(ex, "BTC/USDT", "4h", 50)
        if df is None: return "BTC_NEUTRAL", 0
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]
        if df['close'].iloc[-1] > ema50 > ema200: return "BTC_BULL", 5
        if df['close'].iloc[-1] < ema50 < ema200: return "BTC_BEAR", 5
        return "BTC_NEUTRAL", 0
    except: return "BTC_NEUTRAL", 0

def check_liquidity_hunt(df):
    try:
        rh = df['high'].iloc[-20:-1].max(); rl = df['low'].iloc[-20:-1].min(); curr = df.iloc[-1]
        if curr['high'] > rh*1.005 and curr['close'] < rh: return "LIQ_HUNT_SELL", 20
        if curr['low'] < rl*0.995 and curr['close'] > rl: return "LIQ_HUNT_BUY", 20
        return "NO_HUNT", 0
    except: return "NO_HUNT", 0

def check_whale(df):
    try:
        avg = df['vol'].iloc[-20:-1].mean(); curr = df.iloc[-1]
        body = abs(curr['close']-curr['open'])+0.000001
        wu = curr['high'] - max(curr['open'], curr['close']); wd = min(curr['open'], curr['close']) - curr['low']
        if curr['vol'] > avg*2.5 and wd > body*1.5: return "WHALE_BUY_WICK", 15
        if curr['vol'] > avg*2.5 and wu > body*1.5: return "WHALE_SELL_WICK", 15
        return "NO_WHALE", 0
    except: return "NO_WHALE", 0

def check_cvd(df):
    try:
        if df['close'].iloc[-1] < df['close'].iloc[-3] and df['close'].iloc[-1] > (df['high'].iloc[-1]+df['low'].iloc[-1])/2 and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean():
            return "CVD_BULL_DIV", 15
        if df['close'].iloc[-1] > df['close'].iloc[-3] and df['close'].iloc[-1] < (df['high'].iloc[-1]+df['low'].iloc[-1])/2 and df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean():
            return "CVD_BEAR_DIV", 15
        return "CVD_NEUTRAL", 0
    except: return "CVD_NEUTRAL", 0

def check_vp(df):
    try:
        poc = df['close'].iloc[-50:].mode().iloc[0] if not df['close'].iloc[-50:].mode().empty else df['close'].iloc[-1]
        if abs(df['close'].iloc[-1]-poc)/df['close'].iloc[-1] < 0.01 and df['vol'].iloc[-1] > df['vol'].iloc[-20:-1].mean()*1.5:
            return f"VOL_POC {poc:.4f}", 10
        return "VOL_NORMAL", 0
    except: return "VOL_NORMAL", 0

def check_hs(df):
    try:
        c = df['close'].iloc[-1]
        for i in range(-20, -5):
            try:
                ls = df['low'].iloc[i-5:i].min(); head = df['low'].iloc[i:i+5].min()
                rs = df['low'].iloc[-10:-5].min()
                neck = df['high'].iloc[-15:].max()
                if head < ls*0.99 and head < rs*0.99 and c > neck: return "INV_H&S_BULL_BREAKOUT", 25
            except: pass
            try:
                ls = df['high'].iloc[i-5:i].max(); head = df['high'].iloc[i:i+5].max()
                rs = df['high'].iloc[-10:-5].max()
                neck = df['low'].iloc[-15:].min()
                if head > ls*1.01 and head > rs*1.01 and c < neck: return "H&S_BEAR_BREAKOUT", 25
            except: pass
        return "NO_H&S", 0
    except: return "NO_H&S", 0

def check_mw_bos_fvg(df15, df1h):
    score=0; sigs=[]
    try:
        h = df15['high'].iloc[-15:]; l = df15['low'].iloc[-15:]; c = df15['close']
        if l.iloc[2] < l.iloc[5]*0.99 and c.iloc[-1] > c.iloc[-5:-1].max(): sigs.append("W_PATTERN"); score+=15
        elif h.iloc[2] > h.iloc[5]*0.99 and c.iloc[-1] < c.iloc[-5:-1].min(): sigs.append("M_PATTERN"); score+=15
    except: pass
    try:
        if df1h['close'].iloc[-1] > df1h['high'].iloc[-20:-1].max(): sigs.append("BOS_UP"); score+=15
        elif df1h['close'].iloc[-1] < df1h['low'].iloc[-20:-1].min(): sigs.append("BOS_DOWN"); score+=15
    except: pass
    try:
        if df15['low'].iloc[-1] > df15['high'].iloc[-3]: sigs.append("FVG_BULL"); score+=10
        if df15['high'].iloc[-1] < df15['low'].iloc[-3]: sigs.append("FVG_BEAR"); score+=10
    except: pass
    return sigs, score

def calc_sl_tp(entry, sig, df1h):
    try:
        atr = (df1h['high']-df1h['low']).rolling(14).mean().iloc[-1]
        if np.isnan(atr) or atr==0: atr=entry*0.02
        if sig=="BUY":
            sl=df1h['low'].iloc[-10:].min()*0.998
            if sl>=entry: sl=entry-atr*1.5
            risk=entry-sl
            return sl, entry+risk*1.5, entry+risk*3, entry+risk*5, risk
        else:
            sl=df1h['high'].iloc[-10:].max()*1.002
            if sl<=entry: sl=entry+atr*1.5
            risk=sl-entry
            return sl, entry-risk*1.5, entry-risk*3, entry-risk*5, risk
    except:
        return entry*0.98, entry*1.03, entry*1.06, entry*1.10, entry*0.02

def main():
    print("=== KILLER FIXED START ===")
    last = load_cooldown()
    ex, ex_name = get_exchange()
    btc_trend,_ = check_btc_filter(ex)
    print(f"Exchange: {ex_name} | BTC: {btc_trend}")

    for sym in SYMBOLS:
        if sym in last and datetime.now()-last[sym] < timedelta(hours=COOLDOWN_HOURS): continue
        df1h = fetch_safe(ex, sym, '1h', 150)
        if df1h is None:
            try:
                alt = ccxt.kucoin() if ex_name=="MEXC" else ccxt.mexc()
                df1h = fetch_safe(alt, sym, '1h', 150)
                if df1h is not None: ex=alt; ex_name="KUCOIN" if ex_name=="MEXC" else "MEXC"
            except: pass
            if df1h is None: continue
        df15 = fetch_safe(ex, sym, '15m', 150) or
