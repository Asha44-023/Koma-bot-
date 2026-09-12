import time
import ccxt
import pandas as pd
from datetime import datetime, timezone

# === KOMA BEAST V4 - FAST GROWTH 1.1x + 80% SIZE ===
PUMP_TRIGGER = 10.0
DUMP_TRIGGER = -10.0
TP_PCT = 8.0
SL_PCT = 5.0
TIME_STOP_HOURS = 4
VOL_MULT = 1.1  # FAST - was 1.3
SYMBOL = "KOMA/USDT:USDT"

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
        has_pos = False
        pnl_pct = 0
        side = ""
        entry_price = 0
        pos_info = None
        
        for p in positions:
            try:
                contracts = float(p.get('contracts',0) or 0)
                info = p.get('info',{})
                if contracts == 0:
                    contracts = float(info.get('holdVol',0) or 0)
                if abs(contracts) > 0:
                    has_pos = True
                    pos_info = p
                    side = p.get('side') or info.get('positionSide') or 'long'
                    side = side.lower()
                    entry_price = float(info.get('openPrice') or info.get('avgPrice') or p.get('entryPrice') or 0)
                    unrealized = float(p.get('unrealizedPnl') or info.get('unrealisedPnl') or 0)
                    if entry_price > 0:
                        mark = float(info.get('markPrice') or info.get('lastPrice') or entry_price)
                        if 'long' in side:
                            pnl_pct = (mark - entry_price)/entry_price*100
                        else:
                            pnl_pct = (entry_price - mark)/entry_price*100
                    
                    open_ts = get_position_entry_time(p)
                    if open_ts:
                        hours_open = (time.time() - open_ts)/3600
                        if hours_open >= TIME_STOP_HOURS:
                            try:
                                close_side = "sell" if "long" in side else "buy"
                                ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                                send_msg(send_telegram, f"⏰ *KOMA TIME STOP {TIME_STOP_HOURS}H* Closed {side.upper()} after {hours_open:.1f}h\nPNL {pnl_pct:.2f}%")
                                return f"TIME STOP CLOSED {hours_open:.1f}h PNL {pnl_pct:.2f}%"
                            except Exception as e:
                                send_msg(send_telegram, f"⚠️ Time stop close failed {e}")

                    if pnl_pct >= TP_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"💰 *KOMA TP {TP_PCT}%* Closed {side.upper()} PNL +{pnl_pct:.2f}%")
                            return f"TP CLOSED +{pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ TP close failed {e}")
                    
                    if pnl_pct <= -SL_PCT:
                        try:
                            close_side = "sell" if "long" in side else "buy"
                            ex.create_market_order(SYMBOL, close_side, abs(contracts), params={"reduceOnly": True})
                            send_msg(send_telegram, f"✂️ *KOMA SL {SL_PCT}%* Closed {side.upper()} PNL {pnl_pct:.2f}%")
                            return f"SL CLOSED {pnl_pct:.2f}%"
                        except Exception as e:
                            send_msg(send_telegram, f"⚠️ SL close failed {e}")
                    
                    return f"HOLD {side.upper()} PNL {pnl_pct:.2f}% Entry {entry_price}"
            except Exception as e:
                print(f"pos check err {e}")

        try:
            ohlcv = ex.fetch_ohlcv(SYMBOL, '1h', limit=5)
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            if len(df) < 2:
                return "NO DATA"
            
            change_1h = (df['c'].iloc[-1] - df['c'].iloc[-2]) / df['c'].iloc[-2] * 100
            price = df['c'].iloc[-1]
            vol_now = df['v'].iloc[-1]
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            
            if pd.isna(vol_avg): vol_avg = vol_now
            
            if vol_now < vol_avg * VOL_MULT and abs(change_1h) < PUMP_TRIGGER:
                return f"WAIT Vol {vol_now/vol_avg:.1f}x < {VOL_MULT}x"
            
            if change_1h >= PUMP_TRIGGER:
                if not can_send_func(SYMBOL, f"PUMP{change_1h:.0f}", 30):
                    return f"PUMP {change_1h:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(bal * 0.8, 2)  # FAST 80% - was 40%
                if notional < 3: notional = 3
                qty = notional / price
                try:
                    ex.set_leverage(5, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "sell", qty)
                send_msg(send_telegram, f"🔴 *KOMA AUTO SHORT PUMP {change_1h:.2f}%* Vol {vol_now/vol_avg:.1f}x\nPrice {price:.6f} Size ${notional}\nTP {TP_PCT}% SL {SL_PCT}%")
                return f"SHORT PUMP {change_1h:.2f}%"
            
            if change_1h <= DUMP_TRIGGER:
                if not can_send_func(SYMBOL, f"DUMP{change_1h:.0f}", 30):
                    return f"DUMP {change_1h:.2f}% cooldown"
                bal = float(free_bal)
                notional = round(bal * 0.8, 2)  # FAST 80%
                if notional < 3: notional = 3
                qty = notional / price
                try:
                    ex.set_leverage(5, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "buy", qty)
                send_msg(send_telegram, f"🟢 *KOMA AUTO LONG DUMP {change_1h:.2f}%* Vol {vol_now/vol_avg:.1f}x\nPrice {price:.6f} Size ${notional}\nTP {TP_PCT}% SL {SL_PCT}%")
                return f"LONG DUMP {change_1h:.2f}%"
            
            return f"WAIT change {change_1h:.2f}% Vol {vol_now/vol_avg:.1f}x"
            
        except Exception as e:
            return f"ohlcv err {e}"
            
    except Exception as e:
        return f"beast err {e}"
