import time
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# === KOMA SCALP BEAST $12.91 - KOMA 1.5% OVERRIDE REAL MONEY ===
PUMP_TRIGGER = 1.5
DUMP_TRIGGER = -1.5
TP_PCT = 8.0
SL_PCT = 3.0
TIME_STOP_HOURS = 0.33 # 20 MIN
VOL_MULT = 0.3  # UNLOCKED - was 0.5
SYMBOL = "KOMA/USDT:USDT"
LEVERAGE = 10

RSI_OVERSOLD = 40  # looser
RSI_OVERBOUGHT = 60 # looser, takes 60+
MAX_WICK_RATIO = 2.5 # was 1.5
TRAIL_TRIGGER = 3.0
TRAIL_OFFSET = 0.8
VOL_SPIKE = 0.3  # UNLOCKED - was 2.0 - THIS WAS BLOCKING YOU

peak_pnl = {"long": 0, "short": 0}

def send_msg(send_fn, msg):
    try: send_fn(msg)
    except: print(msg)

def get_position_entry_time(position_info):
    try:
        info = position_info.get('info',{})
        ts = info.get('createTime') or info.get('openTime') or info.get('updateTime')
        if ts:
            ts = int(ts)
            if ts > 1e12: ts = ts/1000
            return ts
    except: pass
    return None

def add_filters(df):
    delta = df['c'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, 0.0001)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['ma20'] = df['c'].rolling(20).mean()
    df['std20'] = df['c'].rolling(20).std()
    df['bb_upper'] = df['ma20'] + df['std20']*2
    df['bb_lower'] = df['ma20'] - df['std20']*2
    df['body'] = abs(df['c'] - df['o']).replace(0, 0.000001)
    df['upper_wick'] = df['h'] - df[['c','o']].max(axis=1)
    df['lower_wick'] = df[['c','o']].min(axis=1) - df['l']
    df['wick_ratio'] = (df['upper_wick'] + df['lower_wick']) / df['body']
    df['close_pos'] = (df['c'] - df['l']) / (df['h'] - df['l']).replace(0,1)
    df['vol_ma10'] = df['v'].rolling(10).mean()
    df['vol_ma20'] = df['v'].rolling(20).mean()
    df['ema9'] = df['c'].ewm(span=9).mean()
    df['ema21'] = df['c'].ewm(span=21).mean()
    df['vwap'] = (df['c'] * df['v']).cumsum() / df['v'].cumsum()
    return df

def scalp_plan(ex, free_bal, send_telegram, can_send_func):
    global peak_pnl
    try:
        positions = ex.fetch_positions([SYMBOL])
        for p in positions:
            try:
                contracts = float(p.get('contracts',0) or 0)
                info = p.get('info',{})
                if contracts == 0:
                    contracts = float(info.get('holdVol',0) or 0)
                if abs(contracts) > 0:
                    side = (p.get('side') or info.get('positionSide') or 'long').lower()
                    entry_price = float(info.get('openPrice') or info.get('avgPrice') or p.get('entryPrice') or 0)
                    mark = float(info.get('markPrice') or info.get('lastPrice') or entry_price)
                    pnl_pct = ((mark - entry_price)/entry_price*100) if 'long' in side else ((entry_price - mark)/entry_price*100) if entry_price>0 else 0

                    key = 'long' if 'long' in side else 'short'
                    if pnl_pct > peak_pnl.get(key,0):
                        peak_pnl[key] = pnl_pct
                    if peak_pnl[key] >= TRAIL_TRIGGER:
                        if pnl_pct <= peak_pnl[key] - TRAIL_OFFSET:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"🔥 *TRAIL TP* {side.upper()} peak {peak_pnl[key]:.2f}% -> close {pnl_pct:.2f}%")
                            peak_pnl[key]=0
                            return f"TRAIL TP {pnl_pct:.2f}%"

                    open_ts = get_position_entry_time(p)
                    if open_ts and (time.time()-open_ts)/3600 >= TIME_STOP_HOURS:
                        close_side = "sell" if "long" in side else "buy"
                        ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                        send_msg(send_telegram, f"⏰ *20MIN STOP* {side.upper()} {pnl_pct:.2f}%")
                        peak_pnl[key]=0
                        return f"TIME STOP {pnl_pct:.2f}%"

                    if pnl_pct >= TP_PCT:
                        close_side = "sell" if "long" in side else "buy"
                        ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                        send_msg(send_telegram, f"💰 *BEAST TP {TP_PCT}%* {side.upper()} +{pnl_pct:.2f}%")
                        peak_pnl[key]=0
                        return f"TP {pnl_pct:.2f}%"
                    if pnl_pct <= -SL_PCT:
                        close_side = "sell" if "long" in side else "buy"
                        ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                        send_msg(send_telegram, f"✂️ *SL {SL_PCT}%* {side.upper()} {pnl_pct:.2f}%")
                        peak_pnl[key]=0
                        return f"SL {pnl_pct:.2f}%"
                    return f"HOLD {side.upper()} PNL {pnl_pct:.2f}% peak {peak_pnl.get(key,0):.2f}%"
            except Exception as e:
                print(f"pos err {e}")

        # NO POSITION -> ENTRY
        try:
            ohlcv5 = ex.fetch_ohlcv(SYMBOL, '5m', limit=30)
            df5 = pd.DataFrame(ohlcv5, columns=['t','o','h','l','c','v'])
            ohlcv1 = ex.fetch_ohlcv(SYMBOL, '1m', limit=30)
            df1 = pd.DataFrame(ohlcv1, columns=['t','o','h','l','c','v'])
            if len(df5)<25 or len(df1)<10:
                return "NO DATA"

            df5 = add_filters(df5)
            df1 = add_filters(df1)

            last5 = df5.iloc[-1]
            prev5 = df5.iloc[-2]
            last1 = df1.iloc[-1]

            change_5m = (last5['c'] - prev5['c']) / prev5['c'] * 100
            change_1m = (df1.iloc[-1]['c'] - df1.iloc[-3]['c']) / df1.iloc[-3]['c'] * 100

            price = last5['c']
            vol_ratio = last5['v']/last5['vol_ma10'] if last5['vol_ma10']>0 else 1
            rsi = last5['rsi']
            vwap = last5['vwap']
            vwap_dist = (price - vwap)/vwap*100
            ema9_1 = last1['ema9']
            ema21_1 = last1['ema21']

            if vol_ratio < VOL_MULT and abs(change_5m) < PUMP_TRIGGER:
                return f"WAIT Vol {vol_ratio:.1f}x change {change_5m:.2f}% RSI {rsi:.0f} VWAP {vwap_dist:.2f}%"

            # LONG
            if change_5m <= DUMP_TRIGGER:
                if rsi > RSI_OVERSOLD:
                    return f"FAKE DUMP RSI {rsi:.0f}>{RSI_OVERSOLD}"
                if last5['wick_ratio'] > MAX_WICK_RATIO:
                    return f"FAKE DUMP wick {last5['wick_ratio']:.1f}x"
                if not can_send_func(SYMBOL, f"DUMP{change_5m:.0f}", 10):
                    return f"DUMP cooldown"
                bal = float(free_bal)
                notional = round(min(max(bal*0.8, 3), bal*0.9), 2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "buy", qty)
                peak_pnl['long']=0
                send_msg(send_telegram, f"🟢 *KOMA BEAST LONG* {change_5m:.2f}% 1m {change_1m:.2f}% RSI {rsi:.0f} VWAP {vwap_dist:.2f}% Vol {vol_ratio:.1f}x")
                return f"LONG {change_5m:.2f}%"

            # SHORT - KOMA 1.5% OVERRIDE REAL MONEY
            if change_5m >= PUMP_TRIGGER:
                if rsi < RSI_OVERBOUGHT:
                    return f"FAKE PUMP RSI {rsi:.0f}<{RSI_OVERBOUGHT}"
                if last5['wick_ratio'] > MAX_WICK_RATIO:
                    return f"FAKE PUMP wick {last5['wick_ratio']:.1f}x"
                if not can_send_func(SYMBOL, f"PUMP{change_5m:.0f}", 10):
                    return f"PUMP cooldown"
                bal = float(free_bal)
                notional = round(min(max(bal*0.8, 3), bal*0.9), 2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "sell", qty)
                peak_pnl['short']=0
                send_msg(send_telegram, f"🔴 *KOMA BEAST SHORT* {change_5m:.2f}% 1m {change_1m:.2f}% RSI {rsi:.0f} VWAP {vwap_dist:.2f}% Vol {vol_ratio:.1f}x OVERRIDE REAL")
                return f"SHORT {change_5m:.2f}% 1m {change_1m:.2f}%"

            return f"WAIT {change_5m:.2f}% 1m {change_1m:.2f}% RSI {rsi:.0f} VWAP {vwap_dist:.2f}% Vol {vol_ratio:.1f}x need {PUMP_TRIGGER}%"

        except Exception as e:
            return f"ohlcv err {e}"
    except Exception as e:
        return f"beast err {e}"
