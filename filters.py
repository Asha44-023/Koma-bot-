# filters.py - ALL 6 COINS - TIGHT & SAFE - FIXED FOR ALL
def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, premium, vol_now, vol_avg, btc_trend, signal_type):

    range_24h = high_24h - low_24h
    location = (price - low_24h) / range_24h if range_24h > 0 else 0.5
    
    if signal_type == "SHORT" and location < 0.25:
        msg = f"At bottom {location*100:.0f}% no SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg

    if signal_type == "LONG" and location > 0.85:
        msg = f"At top {location*100:.0f}% no LONG"
        print(f"BLOCKED - {msg}")
        return True, msg

    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    if range_4h_pct < 0.015:
        msg = f"Tight box {range_4h_pct*100:.2f}% chop"
        print(f"BLOCKED - {msg}")
        return True, msg

    if signal_type == "SHORT" and rsi_1h < 50:
        msg = f"RSI low {rsi_1h:.0f} no SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg
    if signal_type == "LONG" and rsi_1h > 70:
        msg = f"RSI high {rsi_1h:.0f} no LONG"
        print(f"BLOCKED - {msg}")
        return True, msg

    if vol_now < vol_avg * 0.6:
        msg = f"Weak vol {vol_now:.0f} < {vol_avg:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg

    if btc_trend == "DOWN" and signal_type == "LONG":
        msg = f"BTC DOWN block LONG"
        print(f"BLOCKED - {msg}")
        return True, msg
    if btc_trend == "UP" and signal_type == "SHORT":
        msg = f"BTC UP block SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg

    msg = f"PASSED Loc:{location*100:.0f}% RSI:{rsi_1h:.0f} VolOK"
    return False, msg
