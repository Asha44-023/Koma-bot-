# filters.py - KOMA & GRASS - TIGHT & SAFE - NO BAD TRADES
def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, premium, vol_now, vol_avg, btc_trend, signal_type):

    range_24h = high_24h - low_24h
    location = (price - low_24h) / range_24h if range_24h > 0 else 0.5
    
    # FILTER 1: TIGHT - Block SHORT if bottom 25% (was 10%)
    if signal_type == "SHORT" and location < 0.25:
        msg = f"At bottom {location*100:.0f}% no SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 2: TIGHT - Block LONG if top 85% (NEW - prevents buying top)
    if signal_type == "LONG" and location > 0.85:
        msg = f"At top {location*100:.0f}% no LONG"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 3: Box filter - TIGHT 1.5% (was 1%)
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    if range_4h_pct < 0.015:
        msg = f"Tight box {range_4h_pct*100:.2f}% chop"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 4: RSI - TIGHT & SAFE
    if signal_type == "SHORT" and rsi_1h < 50:
        msg = f"RSI low {rsi_1h:.0f} no SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg
    if signal_type == "LONG" and rsi_1h > 70:
        msg = f"RSI high {rsi_1h:.0f} no LONG"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 5: Volume - TIGHT - need 0.6x avg (was 0.3)
    if vol_now < vol_avg * 0.6:
        msg = f"Weak vol {vol_now:.0f} < {vol_avg:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg

    # FILTER 6: BTC trend - TIGHT - Block LONG if BTC DOWN
    if btc_trend == "DOWN" and signal_type == "LONG":
        msg = f"BTC DOWN block LONG"
        print(f"BLOCKED - {msg}")
        return True, msg
    if btc_trend == "UP
