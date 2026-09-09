import ccxt, requests, os, json, pandas as pd, numpy as np
from datetime import datetime, timedelta
import time

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
MIN_SCORE = 45
COOLDOWN_FILE = "last_alerts.json"
TRADES_FILE = "trades.json"
COOLDOWN_HOURS = 2
SYMBOLS = ["VELVET/USDT:USDT", "KOMA/USDT:USDT", "GRASS/USDT:USDT", "SIREN/USDT:USDT", "HEI/USDT:USDT", "LAB/USDT:USDT"]

def get_24h_change(mexc_symbol):
    try:
        clean = mexc_symbol.replace("/", "").replace(":USDT","").replace(":","")
        if not clean.endswith("USDT"): clean = clean + "USDT"
        url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={clean}"
        data = requests.get(url, timeout=5).json()
        return float(data.get('priceChangePercent', 0))
    except: return 0.0

def should_take_signal(mexc_sym, signal_type):
    daily_change = get_24h_change(mexc_sym)
    if signal_type == "SHORT" and daily_change > 8.0: return False
    if signal_type == "LONG" and daily_change < -8.0: return False
    if abs(daily_change) > 10:
        if daily_change > 10 and signal_type == "LONG": return True
        if daily_change < -10 and signal_type == "SHORT": return True
        return False
    return True

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
def load_trades():
    try:
        with open(TRADES_FILE, "r") as f: return json.load(f)
    except: return {}
def save_trades(d):
    try:
        with open(TRADES_FILE, "w") as f: json.dump(d, f, default=str)
    except: pass

def rsi(c, p=14):
    d = c.diff(); g = d.where(d>0,0).rolling(p).mean(); l = -d.where(d<0,0).rolling(p).mean(); return 100 - (100 / (1 + g/l))

def fetch_safe(ex, sym, tf, lim):
    try:
        o = ex.fetch_ohlcv(sym, tf, limit=lim)
        if not o or len(o)<60: return None
        df = pd.DataFrame(o, columns=['ts','open','high','low','close','vol'])
        for col in ['close','high','low','open','vol']: df[col]=df[col].astype(float)
        return df
    except: return None

def get_exchange():
    try:
        ex = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
        ex.fetch_ticker("BTC/USDT:USDT")
        print("Using MEXC FUTURES"); return ex, "MEXC-FUT"
    except:
        try:
            ex = ccxt.kucoin({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            ex.fetch_ticker("BTC/USDT:USDT")
            print("Using KuCoin FUTURES"); return ex, "KUCOIN-FUT"
        except:
            ex = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            return ex, "MEXC-FUT"

def check_btc(ex):
    try:
        df = fetch_safe(ex, "BTC/USDT:USDT", "4h", 50)
        if df is None: return "BTC_NEUTRAL"
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]
        if df['close'].iloc[-1] > ema50 > ema200: return "BTC_BULL"
        if df['close'].iloc[-1] < ema50 < ema200: return "BTC_BEAR"
        return "BTC_NEUTRAL"
    except: return "BTC_NEUTRAL"

def check_order_block(df):
    try:
        for i in range(-10, -3):
            if df['close'].iloc[i] < df['open'].iloc[i] and df['close'].iloc[-1] > df['high'].iloc[i]:
                if df['low'].iloc[i] <= df['low'].iloc[-5:].min()*1.01: return "BULL_OB", 20
            if df['close'].iloc[i] > df['open'].iloc[i] and df['close'].iloc[-1] < df['low'].iloc[i]:
                if df['high'].iloc[i] >= df['high'].iloc[-5:].max()*0.99: return "BEAR_OB", 20
        return "NO_OB", 0
    except: return "NO_OB", 0

def check_equal_levels(df):
    try:
        lows = df['low'].iloc[-20:-1]; highs = df['high'].iloc[-20:-1]
        if abs(lows.min() - sorted(lows)[1]) / lows.min() < 0.002 and df['low'].iloc[-1] < lows.min()*0.998 and df['close'].iloc[-1] > lows.min(): return "EQ_LOWS_SWEEP_BULL", 25
        if abs(highs.max() - sorted(highs, reverse=True)[1]) / highs.max() < 0.002 and df['high'].iloc[-1] > highs.max()*1.002 and df['close'].iloc[-1] < highs.max(): return "EQ_HIGHS_SWEEP_BEAR", 25
        return "NO_EQ", 0
    except: return "NO_EQ", 0

def check_turtle_soup(df):
    try:
        hh = df['high'].iloc[-20:-1].max(); ll = df['low'].iloc[-20:-1].min()
        if df['high'].iloc[-2] > hh and df['close'].iloc[-1] < hh and df['close'].iloc[-1] < df['open'].iloc[-1]: return "TURTLE_SOUP_BEAR", 25
        if df['low'].iloc[-2] < ll and df['close'].iloc[-1] > ll and df['close'].iloc[-1] > df['open'].iloc[-1]: return "TURTLE_SOUP_BULL", 25
        return "NO_TURTLE", 0
    except: return "NO_TURTLE", 0

def check_mss(df):
    try:
        if df['close'].iloc[-1] > df['high'].iloc[-10:-1].max() and df['close'].iloc[-3] < df['low'].iloc[-10:-3].min(): return "MSS_BULL", 20
        if df['close'].iloc[-1] < df['low'].iloc[-10:-1].min() and df['close'].iloc[-3] > df['high'].iloc[-10:-3].max(): return "MSS_BEAR", 20
        return "NO_MSS", 0
    except: return "NO_MSS", 0

def check_premium_discount(df):
    try:
        high = df['high'].iloc[-50:].max(); low = df['low'].iloc[-50:].min(); curr = df['close'].iloc[-1]
        if curr < low + (high-low)*0.25: return "DISCOUNT_BULL", 10
        if curr > high - (high-low)*0.25: return "PREMIUM_BEAR", 10
        return "EQ_ZONE", 0
    except: return "EQ_ZONE", 0

def check_killzone():
    try:
        hour = datetime.utcnow().hour
        if 8 <= hour <= 11: return "LONDON_KZ", 5
        if 13 <= hour <= 16: return "NY_KZ", 10
        if 0 <= hour <= 2: return "ASIAN_LOW", -5
        return "NO_KZ", 0
    except: return "NO_KZ", 0

def check_whale(df):
    try:
        avg = df['vol'].iloc[-20:-1].mean(); curr = df.iloc[-1]
        body = abs(curr['close']-curr['open'])+0.000001
        wu = curr['high'] - max(curr['open'], curr['close'])
        wd = min(curr['open'], curr['close']) - curr['low']
        range_size = curr['high'] - curr['low'] + 0.000001
        if curr['vol'] > avg*2.5 and wd > body*1.5 and wu < body*0.5: return "WHALE_BUY_WICK", 15
        if curr['vol'] > avg*2.5 and wu > body*1.5 and wd < body*0.5: return "WHALE_SELL_WICK", 15
        if curr['vol'] > avg*3 and range_size < df['high'].iloc[-20:-1].sub(df['low'].iloc[-20:-1]).mean()*0.6:
            return ("WHALE_ABSORPTION_BULL", 25) if curr['close'] > curr['open'] else ("WHALE_ABSORPTION_BEAR", 25)
        if curr['vol'] > avg*2 and wu > range_size*0.6 and curr['close'] < curr['open']*1.001: return "WHALE_SPOOF_SELL", 20
        if curr['vol'] > avg*2 and wd > range_size*0.6 and curr['close'] > curr['open']*0.999: return "WHALE_SPOOF_BUY", 20
        return "NO_WHALE", 0
    except: return "NO_WHALE", 0

def check_cvd(df):
    try:
        mid = (df['high'].iloc[-1]+df['low'].iloc[-1])/2; avgv = df['vol'].iloc[-20:-1].mean()
        vol_trend = df['vol'].iloc[-5:].mean() / (avgv+0.0001)
        price_change = (df['close'].iloc[-1] - df['close'].iloc[-5]) / (df['close'].iloc[-5]+0.0001)
        if price_change < -0.01 and df['close'].iloc[-1] > mid and vol_trend > 1.3: return "CVD_BULL_DIV_STRONG", 20
        if price_change > 0.01 and df['close'].iloc[-1] < mid and vol_trend > 1.3: return "CVD_BEAR_DIV_STRONG", 20
        if price_change > 0.015 and vol_trend < 0.7: return "VOL_FAKE_PUMP", 20
        if price_change < -0.015 and vol_trend < 0.7: return "VOL_FAKE_DUMP", 20
        return "CVD_NEUTRAL", 0
    except: return "CVD_NEUTRAL", 0

def check_volume_profile(df):
    try:
        recent_vol = df['vol'].iloc[-3:].mean(); past_vol = df['vol'].iloc[-15:-3].mean()+0.0001
        price_up = df['close'].iloc[-1] > df['close'].iloc[-5]; vol_up = recent_vol > past_vol*1.4
        if price_up and vol_up: return "VOL_CONFIRM_BULL", 15
        if not price_up and vol_up: return "VOL_CONFIRM_BEAR", 15
        if price_up and not vol_up: return "VOL_WEAK_BULL_TRAP", 15
        if not price_up and not vol_up: return "VOL_WEAK_BEAR_TRAP", 15
        return "VOL_NEUTRAL", 0
    except: return "VOL_NEUTRAL", 0

def check_liq(df):
    try:
        rh = df['high'].iloc[-20:-1].max(); rl = df['low'].iloc[-20:-1].min(); curr = df.iloc[-1]
        if curr['high'] > rh*1.005 and curr['close'] < rh: return "LIQ_HUNT_SELL", 20
        if curr['low'] < rl*0.995 and curr['close'] > rl: return "LIQ_HUNT_BUY", 20
        return "NO_HUNT", 0
    except: return "NO_HUNT", 0

def check_hs(df):
    try:
        c = df['close'].iloc[-1]; neck_high = df['high'].iloc[-15:].max(); neck_low = df['low'].iloc[-15:].min()
        for i in range(-20, -5):
            ls = df['low'].iloc[i-5:i].min(); head = df['low'].iloc[i:i+5].min(); rs = df['low'].iloc[-10:-5].min()
            if head < ls*0.99 and head < rs*0.99 and c > neck_high: return "INV_H&S_BULL", 25
            ls2 = df['high'].iloc[i-5:i].max(); head2 = df['high'].iloc[i:i+5].max(); rs2 = df['high'].iloc[-10:-5].max()
            if head2 > ls2*1.01 and head2 > rs2*1.01 and c < neck_low: return "H&S_BEAR", 25
        return "NO_H&S", 0
    except: return "NO_H&S", 0

def check_patterns(df15, df1h):
    score=0; sigs=[]
    try:
        h = df15['high'].iloc[-15:]; l = df15['low'].iloc[-15:]; c = df15['close']
        if l.iloc[2] < l.iloc[5]*0.99 and c.iloc[-1] > c.iloc[-5:-1].max(): sigs.append("W_PATTERN"); score+=15
        if h.iloc[2] > h.iloc[5]*0.99 and c.iloc[-1] < c.iloc[-5:-1].min(): sigs.append("M_PATTERN"); score+=15
    except: pass
    try:
        if df1h['close'].iloc[-1] > df1h['high'].iloc[-20:-1].max(): sigs.append("BOS_UP"); score+=15
        if df1h['close'].iloc[-1] < df1h['low'].iloc[-20:-1].min(): sigs.append("BOS_DOWN"); score+=15
    except: pass
    try:
        if df15['low'].iloc[-1] > df15['high'].iloc[-3]: sigs.append("FVG_BULL"); score+=10
        if df15['high'].iloc[-1] < df15['low'].iloc[-3]: sigs.append("FVG_BEAR"); score+=10
    except: pass
    return sigs, score

def check_market_shift(df15, df1h, entry_type):
    score=0; reasons=[]
    try:
        r = rsi(df15['close']).iloc[-1]
        if entry_type=="BUY" and r>68: score+=30; reasons.append(f"RSI_FLIP_OB {r:.0f}")
        if entry_type=="SELL" and r<32: score+=30; reasons.append(f"RSI_FLIP_OS {r:.0f}")
        if entry_type=="BUY" and df1h['close'].iloc[-1] < df1h['low'].iloc[-20:-1].min(): score+=40; reasons.append("BOS_FLIP_DOWN")
        if entry_type=="SELL" and df1h['close'].iloc[-1] > df1h['high'].iloc[-20:-1].max(): score+=40; reasons.append("BOS_FLIP_UP")
        avg=df15['vol'].iloc[-20:-1].mean(); curr=df15.iloc[-1]; body=abs(curr['close']-curr['open'])+0.00001
        wu=curr['high']-max(curr['open'],curr['close']); wd=min(curr['open'],curr['close'])-curr['low']
        if entry_type=="BUY" and curr['vol']>avg*2 and wu>body*1.5: score+=30; reasons.append("WHALE_SELL_AGAINST")
        if entry_type=="SELL" and curr['vol']>avg*2 and wd>body*1.5: score+=30; reasons.append("WHALE_BUY_AGAINST")
    except: pass
    return score, reasons

def calc_sl_tp(entry, sig, df1h):
    try:
        atr = (df1h['high']-df1h['low']).rolling(14).mean().iloc[-1]
        if atr!= atr or atr==0: atr=entry*0.02
        if sig=="BUY":
            sl=df1h['low'].iloc[-10:].min()*0.998
            if sl>=entry: sl=entry-atr*1.5
            risk=entry-sl; return sl, entry+risk*1.5, entry+risk*3, entry+risk*5
        else:
            sl=df1h['high'].iloc[-10:].max()*1.002
            if sl<=entry: sl=entry+atr*1.5
            risk=sl-entry; return sl, entry-risk*1.5, entry-risk*3, entry-risk*5
    except: return entry*0.98, entry*1.03, entry*1.06, entry*1.10

def main():
    print("=== V6.2 FINAL NO-DUP FIXED ===")
    last = load_cooldown(); trades = load_trades(); still_open = {}
    ex, ex_name = get_exchange(); btc_trend = check_btc(ex)
    print(f"Exchange: {ex_name} BTC: {btc_trend}")
    for sym, data in trades.items():
        df1h_g = fetch_safe(ex, sym, "1h", 100); df15_g = fetch_safe(ex, sym, "15m", 100)
        if df1h_g is None or df15_g is None: still_open[sym]=data; continue
        entry_type = data['type']; entry_price = data['entry']; entry_time = datetime.fromisoformat(data['time'])
        hours_open = (datetime.now()-entry_time).total_seconds()/3600
        curr_price = df15_g['close'].iloc[-1]
        pnl = (curr_price-entry_price)/entry_price*100 if entry_type=="BUY" else (entry_price-curr_price)/entry_price*100
        shift_score, shift_reasons = check_market_shift(df15_g, df1h_g, entry_type)
        if shift_score >= 40:
            tg(f"FLIP ALERT {sym} CLOSE {entry_type} Score {shift_score} PnL {pnl:.2f}%")
            if shift_score < 70: still_open[sym]=data
        elif hours_open > 3 and abs(pnl) < 1.0 and shift_score>=20:
            tg(f"NEUTRAL SHIFT {sym} Stuck {hours_open:.1f}h PnL {pnl:.2f}%")
            if hours_open < 24: still_open[sym]=data
        else:
            if hours_open < 48: still_open[sym]=data
    save_trades(still_open)
    sent_this_run = set()
    for sym in SYMBOLS:
        if sym in last and datetime.now()-last[sym] < timedelta(hours=COOLDOWN_HOURS): continue
        if sym in still_open: continue
        if sym in sent_this_run: continue
        df1h = fetch_safe(ex, sym, "1h", 150)
        if df1h is None: continue
        df15 = fetch_safe(ex, sym, "15m", 150)
        if df15 is None: df15 = df1h
        df5 = fetch_safe(ex, sym, "5m", 100)
        if df5 is None: df5 = df15
        entry = df5['close'].iloc[-1]
        total=0; triggers=[]; sig=None
        triggers.append(ex_name); triggers.append(btc_trend)
        hs, hs_s = check_hs(df1h)
        if hs_s>0: triggers.append(hs); total+=hs_s; sig="BUY" if "BULL" in hs else "SELL" if "BEAR" in hs else sig
        liq, liq_s = check_liq(df15)
        if liq_s>0: triggers.append(liq); total+=liq_s; sig="BUY" if "BUY" in liq else "SELL"
        whale, whale_s = check_whale(df15)
        if whale_s>0: triggers.append(whale); total+=whale_s; sig="BUY" if "BUY" in whale or "BULL" in whale else "SELL" if "SELL" in whale or "BEAR" in whale else sig
        cvd, cvd_s = check_cvd(df15)
        if cvd_s>0: triggers.append(cvd); total+=cvd_s; sig="BUY" if "BULL" in cvd else "SELL" if "BEAR" in cvd else "SELL" if "FAKE_PUMP" in cvd else "BUY" if "FAKE_DUMP" in cvd else sig
        mw_sigs, mw_sc = check_patterns(df15, df1h)
        for s in mw_sigs: triggers.append(s)
        total+=mw_sc
        if sig is None:
            if "W_PATTERN" in mw_sigs or "BOS_UP" in mw_sigs or "FVG_BULL" in mw_sigs: sig="BUY"
            if "M_PATTERN" in mw_sigs or "BOS_DOWN" in mw_sigs or "FVG_BEAR" in mw_sigs: sig="SELL"
        ob, ob_s = check_order_block(df15)
        if ob_s>0: triggers.append(ob); total+=ob_s; sig="BUY" if "BULL" in ob else "SELL" if "BEAR" in ob else sig
        eq, eq_s = check_equal_levels(df15)
        if eq_s>0: triggers.append(eq); total+=eq_s; sig="BUY" if "BULL" in eq else "SELL"
        tur, tur_s = check_turtle_soup(df15)
        if tur_s>0: triggers.append(tur); total+=tur_s; sig="BUY" if "BULL" in tur else "SELL"
        mss, mss_s = check_mss(df1h)
        if mss_s>0: triggers.append(mss); total+=mss_s; sig="BUY" if "BULL" in mss else "SELL"
        pd_zone, pd_s = check_premium_discount(df1h)
        triggers.append(pd_zone); total+=pd_s
        kz, kz_s = check_killzone()
        triggers.append(kz); total+=kz_s
        volp, volp_s = check_volume_profile(df15)
        if volp_s>0: triggers.append(volp); total+=volp_s
        r = rsi(df15['close']).iloc[-1]
        if r<30: triggers.append("RSI_OS"); total+=15; sig="BUY" if sig is None else sig
        if r>70: triggers.append("RSI_OB"); total+=15; sig="SELL" if sig is None else sig
        if sig=="SELL":
            if "DISCOUNT_BULL" in triggers: triggers.remove("DISCOUNT_BULL"); total-=10
            if "RSI_OS" in triggers: triggers.remove("RSI_OS"); total-=15
            if "BULL_OB" in triggers: triggers.remove("BULL_OB"); total-=20
            if "EQ_LOWS_SWEEP_BULL" in triggers: triggers.remove("EQ_LOWS_SWEEP_BULL"); total-=25
            if "TURTLE_SOUP_BULL" in triggers: triggers.remove("TURTLE_SOUP_BULL"); total-=25
            if "VOL_WEAK_BEAR_TRAP" in triggers: triggers.remove("VOL_WEAK_BEAR_TRAP"); total-=15
        if sig=="BUY":
            if "PREMIUM_BEAR" in triggers: triggers.remove("PREMIUM_BEAR"); total-=10
            if "RSI_OB" in triggers: triggers.remove("RSI_OB"); total-=15
            if "BEAR_OB" in triggers: triggers.remove("BEAR_OB"); total-=20
            if "EQ_HIGHS_SWEEP_BEAR" in triggers: triggers.remove("EQ_HIGHS_SWEEP_BEAR"); total-=25
            if "TURTLE_SOUP_BEAR" in triggers: triggers.remove("TURTLE_SOUP_BEAR"); total-=25
            if "VOL_WEAK_BULL_TRAP" in triggers: triggers.remove("VOL_WEAK_BULL_TRAP"); total-=15
        if total>100: total=100
        if total<0: total=0
        print(f"{sym} {total}/100 {sig} {triggers}")
        if total >= MIN_SCORE and sig is not None:
            if btc_trend=="BTC_BEAR" and sig=="BUY" and total<60: continue
            signal_for_filter = "SHORT" if sig == "SELL" else "LONG"
            if not should_take_signal(sym, signal_for_filter): continue
            if sym in sent_this_run: continue
            sl,tp1,tp2,tp3 = calc_sl_tp(entry, sig, df1h)
            clean_sym = sym.replace(":USDT","").replace(":USDT","")
            msg = f"🔥 *{clean_sym} {sig} - {total}/100 PRO MAX ({ex_name})* 🔥\n\nTriggers: {', '.join(triggers[:12])}\nEntry: `{entry:.6f}`\nSL: `{sl:.6f}`\nTP1: `{tp1:.6f}`\nTP2: `{tp2:.6f}`\nTP3: `{tp3:.6f}`\n\nFUTURES + Whale Vision"
            tg(msg)
            last[sym]=datetime.now(); save_cooldown(last)
            sent_this_run.add(sym)
            still_open[sym] = {"type": sig, "entry": entry, "time": datetime.now().isoformat()}
            save_trades(still_open)
        time.sleep(1.5)
    print("=== SCAN SUCCESS V6.2 NO DUP ===")

if __name__ == "__main__": main()
