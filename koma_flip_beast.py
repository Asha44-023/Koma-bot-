# === KOMA SCALPING 5MIN - CATCHES WICKS YOU SEE ===
PUMP_TRIGGER = 2.5   # 2.5% in 5min = pump (for 5min chart)
DUMP_TRIGGER = -2.5
TP_PCT = 3.0
SL_PCT = 2.5
TIME_STOP_HOURS = 1
VOL_MULT = 0.8  # lower = more trades
SYMBOL = "KOMA/USDT:USDT"

# ... keep send_msg and get_position_entry_time same ...

def scalp_plan(ex, free_bal, send_telegram, can_send_func):
    try:
        positions = ex.fetch_positions([SYMBOL])
        for p in positions:
            # ... keep your same TP/SL/TIME STOP code ...
            pass # your existing code here

        try:
            ohlcv = ex.fetch_ohlcv(SYMBOL, '5m', limit=20)  # <-- 5 MIN
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
            if len(df) < 10:
                return "NO DATA"
            
            change_5m = (df['c'].iloc[-1] - df['c'].iloc[-2]) / df['c'].iloc[-2] * 100
            price = df['c'].iloc[-1]
            vol_now = df['v'].iloc[-1]
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            if pd.isna(vol_avg): vol_avg = vol_now
            vol_ratio = vol_now/vol_avg if vol_avg>0 else 1.0
            
            # Only WAIT if BOTH low vol AND low change
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
                    ex.set_leverage(5, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "sell", qty)
                send_msg(send_telegram, f"🔴 *SCALP SHORT {change_5m:.2f}%* 5m Vol {vol_ratio:.1f}x")
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
                    ex.set_leverage(5, SYMBOL)
                    ex.set_margin_mode('isolated', SYMBOL)
                except: pass
                ex.create_market_order(SYMBOL, "buy", qty)
                send_msg(send_telegram, f"🟢 *SCALP LONG {change_5m:.2f}%* 5m Vol {vol_ratio:.1f}x")
                return f"LONG DUMP {change_5m:.2f}%"
            
            return f"WAIT 5m change {change_5m:.2f}% Vol {vol_ratio:.1f}x need {PUMP_TRIGGER}%"
            
        except Exception as e:
            return f"ohlcv err {e}"
    except Exception as e:
        return f"beast err {e}"
