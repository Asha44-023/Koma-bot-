def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, vol_now, vol_avg, btc_trend, signal_type, reasons=None):
    if reasons is None:
        reasons = []
    reasons_str = " ".join(reasons).upper()

    # Whale override saves pump on all 6 coins
    whale_override = any(x in reasons_str for x in [
        "LIQ_GRAB", "WHALE_TRAP", "KOMA_PUMP_OVERRIDE", 
        "BREAKOUT_LONG", "BREAKOUT_SHORT", "STOP_HUNT", "ACCUM"
    ])
    
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    range_24h_pct = high_24h - low_24h
    location_24h = ((price - low_24h) / range_24h_pct * 100) if range_24h_pct > 0 else 50

    # 1. JUNCTION MANIPULATION FILTER - YOUR NEW LOGIC
    if range_4h_pct < 0.015:
        if not whale_override:
            msg = f"JUNCTION BOX {range_4h_pct*100:.2f}% WAIT no {signal_type}"
            print(f"BLOCKED - {msg}")
            return True, msg
        else:
            if vol_now < vol_avg * 1.1:
                msg = f"JUNCTION + whale but weak vol {vol_now/vol_avg:.1f}x WAIT"
                return True, msg
            # Confirmed breakout with volume
            msg = f"CONFIRMED {signal_type} BREAKOUT Vol {vol_now/vol_avg:.1f}x"
            return False, msg

    # 2. LOCATION FILTER
    if not whale_override:
        if signal_type == "LONG" and location_24h > 85:
            msg = f"At top {location_24h:.1f}% no LONG"
            return True, msg
        if signal_type == "SHORT" and location_24h < 15:
            msg = f"At bottom {location_24h:.1f}% no SHORT"
            return True, msg

    # 3. RSI EXTREME - 82 for your 6 lowcaps
    if not whale_override:
        if signal_type == "LONG" and rsi_1h > 82:
            msg = f"RSI extreme {rsi_1h:.1f} no LONG"
            return True, msg
        if signal_type == "SHORT" and rsi_1h < 18:
            msg = f"RSI extreme {rsi_1h:.1f} no SHORT"
            return True, msg

    # 4. VOLUME FILTER
    if not whale_override:
        if vol_now < vol_avg * 0.7:
            msg = f"Low vol {vol_now/vol_avg:.1f}x WAIT"
            return True, msg

    # 5. BTC FILTER
    if not whale_override:
        if btc_trend == "BEARISH" and signal_type == "LONG":
            msg = f"BTC bear no LONG"
            return True, msg
        if btc_trend == "BULLISH" and signal_type == "SHORT":
            msg = f"BTC bull no SHORT"
            return True, msg

   
