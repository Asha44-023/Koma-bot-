import time
import ccxt
import pandas as pd
from datetime import datetime, timezone

# === KOMA BEAST 5MIN - FOR $12.90 ===
PUMP_TRIGGER = 1.5   # 1.5% = catch early at 0.01711
DUMP_TRIGGER = -1.5  # -1.5% = catch early
TP_PCT = 8.0         # 8% TP = $10.32 profit on $12.90 at 10x
SL_PCT = 3.0         # 3% SL
TIME_STOP_HOURS = 1
VOL_MULT = 0.5       # 0.5x = catch even low vol at top
SYMBOL = "KOMA/USDT:USDT"
LEVERAGE = 10        # BEAST 10x for KOMA

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
                                send_msg(send_telegram, f"⏰ *BEAST TIME STOP {TIME_STOP_HOURS}H* {side.upper()} {hours_open:.1f}h PNL {pnl_pct:.2f}%")
                                return f"TIME STOP CLOSED {hours_open:.1f}h PNL {pnl_pct:.2f}%"
                            except Exception as e:
                                send_msg(send_telegram, f"⚠️ Time stop fail {e}")

                    if pnl_pct >= TP_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"💰 *BEAST TP {TP_PCT}%* {side.upper()} +{pnl_pct:.2f}% | $12.90 -> profit ${float(free_bal)*LEVERAGE*TP_PCT/100:.2f}")
                            return f"TP CLOSED +{pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ TP fail {e}")
                    
                    if pnl_pct <= -SL_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"✂️ *BEAST SL {SL_PCT}%* {side.upper()} {pnl_pct:.2f}%")
                            return f"SL CLOSED {pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ SL fail {e}")
                    
                    return f"HOLD {side.upper()} PNL {pnl_pct:.2f}% TP {TP_PCT}%"
            except Exception as e:
                print(f"pos err {e}")

        try:
            ohlcv = ex.fetch_ohlcv(SYMBOL, '5m', limit=20)
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            if len(df) < 10:
                return "NO DATA"
            
            change_5m = (df['c'].iloc[-1] - df['c'].iloc[-2]) / df['c'].iloc[-2] * 100
            price = df['c'].iloc[-1]
            vol_now = df['v'].iloc[-1]
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            if pd.isna(vol_avg): vol_avg = vol_now
            vol_ratio = vol_now/vol_avg if vol_avg>0 else 1.0
            
            if vol_ratio < VOL_MULT and abs(change_5m) < PUMP_TRIGGER:
                return f"WAIT 5m Vol {vol_ratio:.1f}x change {change_5m:.2f}%"
            
            if change_5m >= PUMP_TRIGGER:
                if not can_send_func(SYMBOL, f"PUMP{change_5m:.0f}", 10):
                    return f"PUMP {change_5m:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(bal * 0.8, 2)
                if notional < 3: notional = 3
                if notional > bal*0.9: notional = round(bal*0.9,2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "sell", qty)
                send_msg(send_telegram, f"🔴 *BEAST SHORT {change_5m:.2f}%* 5m Vol {vol_ratio:.1f}x Price {price:.6f} | TP 8% -> {price*0.92:.6f}")
                return f"SHORT PUMP {change_5m:.2f}%"
            
            if change_5m <= DUMP_TRIGGER:
                if not can_send_func(SYMBOL, f"DUMP{change_5m:.0f}", 10):
                    return f"DUMP {change_5m:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(bal * 0.8, 2)
                if notional < 3: notional = 3
                if notional > bal*0.9: notional = round(bal*0.9,2)
                qty = notional / price
                try:
                    ex.set_leverage(LEVERAGE, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "buy", qty)
                send_msg(send_telegram, f"🟢 *BEAST LONG {change_5m:.2f}%* 5m Vol {vol_ratio:.1f}x Price {price:.6f} | TP 8% -> {price*1.08:.6f} = ${bal*LEVERAGE*0.08:.2f} profit")
                return f"LONG DUMP {change_5m:.2f}%"
            
            return f"WAIT 5m change {change_5m:.2f}% Vol {vol_ratio:.1f}x need {PUMP_TRIGGER}%"
            
        except Exception as e:
            return f"ohlcv err {e}"
            
    except Exception as e:
        return f"beast err {e}"
