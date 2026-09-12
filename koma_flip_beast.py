import time
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# === KOMA BEAST + ANTI-FAKEOUT - $12.90 ===
PUMP_TRIGGER = 1.5
DUMP_TRIGGER = -1.5
TP_PCT = 8.0
SL_PCT = 3.0
TIME_STOP_HOURS = 0.33  # 20 MIN
VOL_MULT = 0.5
SYMBOL = "KOMA/USDT:USDT"
LEVERAGE = 10

RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
MAX_WICK_RATIO = 1.5

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
    return df

def scalp_plan(ex, free_bal, send_telegram, can_send_func):
    try:
        positions = ex.fetch_positions([SYMBOL])
        for p in positions:
            try:
                contracts = float(p.get('contracts',0) or 0)
                info = p.get('info',{})
                if contracts == 0:
                    contracts = float(info.get('holdVol',0) or 0)
                if abs(contracts) > 0:
                    side = p.get('side') or info.get('positionSide') or 'long'
                    side = side.lower()
                    entry_price = float(info.get('openPrice') or info.get('avgPrice') or p.get('entryPrice') or 0)
                    mark = float(info.get('markPrice') or info.get('lastPrice') or entry_price)
                    if entry_price > 0:
                        if 'long' in side:
                            pnl_pct = (mark - entry_price)/entry_price*100
                        else:
                            pnl_pct = (entry_price - mark)/entry_price*100
                    else:
                        pnl_pct = 0
                    open_ts = get_position_entry_time(p)
                    if open_ts:
                        hours_open = (time.time() - open_ts)/3600
                        if hours_open >= TIME_STOP_HOURS:
                            try:
                                close_side = "sell" if "long" in side else "buy"
                                ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                                send_msg(send_telegram, f"⏰ *BEAST 20MIN STOP* {side.upper()} {hours_open*60:.0f}min PNL {pnl_pct:.2f}%")
                                return f"TIME STOP {hours_open*60:.0f}min PNL {pnl_pct:.2f}%"
                            except Exception as e:
                                send_msg(send_telegram, f"⚠️ Time stop fail {e}")
                    if pnl_pct >= TP_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"💰 *BEAST TP {TP_PCT}%* {side.upper()} +{pnl_pct:.2f}% | $12.90 -> ${float(free_bal)+float(free_bal)*LEVERAGE*TP_PCT/100/10:.2f}")
                            return f"TP +{pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ TP fail {e}")
                    if pnl_pct <= -SL_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"✂️ *BEAST SL {SL_PCT}%* {side.upper()} {pnl_pct:.2f}%")
                            return f"SL {pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ SL fail {e}")
                    return f"HOLD {side.upper()} PNL {pnl_pct:.2f}%"
            except Exception as e:
                print(f"pos err {e}")

        try:
            ohlcv = ex.fetch_ohlcv(SYMBOL, '5m', limit=30)
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            if len(df) < 25:
                return "NO DATA"
            
            df = add_filters(df)
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            change_5m = (last['c'] - prev['c']) / prev['c'] * 100
            price = last['c']
            vol_now = last['v']
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            vol_ratio = vol_now/vol_avg if vol_avg>0 else 1.0
            
            rsi = last['rsi']
            bb_up = last['bb_upper']
            bb_low = last['bb_lower']
            wick_ratio = last['wick_ratio']
            close_pos = last['close_pos']
            
            if vol_ratio < VOL_MULT and abs(change_5m) < PUMP_TRIGGER:
                return f"WAIT Vol {vol_ratio:.1f}x change {change_5m:.2f}% RSI {rsi:.0f}"

            if change_5m <= DUMP_TRIGGER:
                if rsi > RSI_OVERSOLD:
                    return f"FAKE DUMP RSI {rsi:.0f}>{RSI_OVERSOLD}"
                if price > bb_low:
                    return f"FAKE DUMP inside BB {price:.6f}>{bb_low:.6f}"
                if wick_ratio > MAX_WICK_RATIO:
                    return f"FAKE DUMP wick {wick_ratio:.1f}x"
                if close_pos > 0.4:
                    return f"FAKE DUMP close {close_pos:.2f} not low"
                if not can_send_func(SYMBOL, f"DUMP{change_5m:.0f}", 10):
                    return f"DUMP {change_5m:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(min(max(bal*0.8, 3), bal*0.9), 2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "buy", qty)
                send_msg(send_telegram, f"🟢 *BEAST LONG REAL* {change_5m:.2f}% RSI {rsi:.0f} Vol {vol_ratio:.1f}x Price {price:.6f} TP {price*1.08:.6f}")
                return f"LONG REAL {change_5m:.2f}% RSI {rsi:.0f}"

            if change_5m >= PUMP_TRIGGER:
                if rsi < RSI_OVERBOUGHT:
                    return f"FAKE PUMP RSI {rsi:.0f}<{RSI_OVERBOUGHT}"
                if price < bb_up:
                    return f"FAKE PUMP inside BB {price:.6f}<{bb_up:.6f}"
                if wick_ratio > MAX_WICK_RATIO:
                    return f"FAKE PUMP wick {wick_ratio:.1f}x"
                if close_pos < 0.6:
                    return f"FAKE PUMP close {close_pos:.2f} not high"
                if not can_send_func(SYMBOL, f"PUMP{change_5m:.0f}", 10):
                    return f"PUMP {change_5m:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(min(max(bal*0.8, 3), bal*0.9), 2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "sell", qty)
                send_msg(send_telegram, f"🔴 *BEAST SHORT REAL* {change_5m:.2f}% RSI {rsi:.0f} Vol {vol_ratio:.1f}x Price {price:.6f} TP {price*0.92:.6f}")
                return f"SHORT REAL {change_5m:.2f}% RSI {rsi:.0f}"

            return f"WAIT change {change_5m:.2f}% RSI {rsi:.0f} Vol {vol_ratio:.1f}x need {PUMP_TRIGGER}%"
            
        except Exception as e:
            return f"ohlcv err {e}"
            
    except Exception as e:
        return f"beast err {e}"
