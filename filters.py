# filters.py - KOMA & GRASS - LOOSE but SAFE - FIXED TO RETURN TUPLE
def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, premium, vol_now, vol_avg, btc_trend, signal_type):

    range_24h = high_24h - low_24h
    location = (price - low_24h) / range_24h if range_24h > 0 else 0.5
    
    # FILTER 1: Only block SHORT if REALLY at bottom (10%)
    if signal_type == "SHORT" and location < 0.10:
        msg = f"At absolute bottom {location*100:.0f}%"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 2: Box filter - only block if SUPER tight <1%
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    if range_4h_pct < 0.01:
        msg = f"Super tight box {range_4h_pct*100:.2f}%"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 3: RSI - LOOSE
    if signal_type == "SHORT" and rsi_1h < 45:
        msg = f"RSI too low for SHORT {rsi_1h:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg
    if signal_type == "LONG" and rsi_1h > 75:
        msg = f"RSI too high for LONG {rsi_1h:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 4: Volume - LOOSE
    if vol_now < vol_avg * 0.3:
        msg = f"Dead volume vol {vol_now:.0f} < avg {vol_avg:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 5: PASSED
    msg = f"Loc:{location*100:.0f}% RSI:{rsi_1h:.0f} Prem:{premium} Vol OK"
    print(f"✅ PASSED - {msg}")
    return False, msg  # NOT BLOCKED = ALLOW TRADE
