# filters.py - ALL 6 COINS - WHALE + KOMA PUMP READY - $14.99 -> $10K
def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, premium, vol_now, vol_avg, btc_trend, signal_type, reasons=None):
    if reasons is None: reasons = []
    reasons_str = " ".join(reasons).upper()
    
    # === WHALE & KOMA PUMP OVERRIDE - DON'T BLOCK ===
    whale_override = any(x in reasons_str for x in ["LIQ_GRAB", "WHALE_TRAP", "WHALE_ACCUM", "KOMA_PUMP_OVERRIDE", "BREAKOUT_LONG", "BREAKOUT_SHORT", "STOP_HUNT"])
    
    range_24h = high_24h - low_24h
    location = (price - low_24h) / range_24h if range_24h > 0 else 0.5
    
    # Location filter - but allow if whale grab
    if not whale_override:
        if signal_type == "SHORT" and location < 0.25:
            msg = f"At bottom {location*100:.0f}% no SHORT"
            print(f"BLOCKED - {msg}")
            return True, msg
        if signal_type == "LONG" and location > 0.85:
            msg = f"At top {location*100:.0f}% no LONG"
            print(f"BLOCKED - {msg}")
            return True, msg

    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    if range_4h_pct < 0.015 and not whale_override:
        msg = f"Tight box {range_4h_pct*100:.2f}% chop"
        print(f"BLOCKED - {msg}")
        return True, msg

    # === KOMA PUMP FIX - RSI filter relaxed ===
    # Old: RSI>70 block LONG - kills pumps!
    # New: RSI>80 block LONG, but allow if whale/pump override
    if signal_type == "SHORT" and rsi_1h < 35 and not whale_override:
        msg = f"RSI low {rsi_1h:.0f} no SHORT"
        print(f"BLOCKED - {msg}")
        return True, msg
    if signal_type == "LONG" and rsi_1h > 82 and not whale_override:
        msg = f"RSI extreme {rsi_1h:.0f} no LONG"
        print(f"BLOCKED - {msg}")
        return True, msg

    # Vol filter - allow if breakout
    if vol_now < vol_avg * 0.5 and not whale_override:
        msg = f"Weak vol {vol_now:.0f} < {vol_avg:.0f}"
        print(f"BLOCKED - {msg}")
        return True, msg

    # BTC filter - relaxed for whale signals
    if not whale_override:
        if btc_trend == "DOWN" and signal_type == "LONG":
            # Allow LONG if strong whale signal even if BTC down
            if "BREAKOUT_LONG" not in reasons_str and "LIQ_GRAB_LONG" not in reasons_str:
                msg = f"BTC DOWN block LONG"
                print(f"BLOCKED - {msg}")
                return True, msg
        if btc_trend == "UP" and signal_type == "SHORT":
            if "BREAKOUT_SHORT" not in reasons_str and "LIQ_GRAB_SHORT" not in reasons_str:
                msg = f"BTC UP block SHORT"
                print(f"BLOCKED - {msg}")
                return True, msg

    msg = f"PASSED Loc:{location*100:.0f}% RSI:{rsi_1h:.0f} VolOK {'WHALE_OVERRIDE' if whale_override else ''}"
    return False, msg
