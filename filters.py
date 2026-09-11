# my_filters.py - KOMA Elite Filters
# Paste this whole file in separate space

def check_all_filters(price, low_24h, high_24h, low_4h, high_4h, rsi_1h, premium, vol_now, vol_avg, btc_trend, signal_type):

    # --- FILTER 1: LOCATION ---
    # Blocks short at bottom like 0.01395
    range_24h = high_24h - low_24h
    location = (price - low_24h) / range_24h if range_24h > 0 else 0.5
    
    if signal_type == "SHORT" and location < 0.6:
        print(f"BLOCKED 1 - Bottom location {location*100:.0f}%")
        return True  # BLOCK

    # --- FILTER 2: CONSOLIDATION BOX ---
    # Blocks tight box 0.0140-0.0142
    range_4h_pct = (high_4h - low_4h) / price if price > 0 else 0
    if range_4h_pct < 0.02:
        print(f"BLOCKED 2 - Consolidating {range_4h_pct*100:.2f}%")
        return True  # BLOCK

    # --- FILTER 3: RSI ---
    # Blocks weak RSI
    if signal_type == "SHORT" and rsi_1h < 60:
        print(f"BLOCKED 3 - RSI low {rsi_1h}")
        return True  # BLOCK

    # --- FILTER 4: PREMIUM ---
    # Blocks weak premium -0.01%
    if signal_type == "SHORT" and premium > -0.03:
        print(f"BLOCKED 4 - Weak premium {premium}")
        return True  # BLOCK

    # --- FILTER 5: VOLUME ---
    # Blocks dead volume
    if vol_now < vol_avg * 0.7:
        print(f"BLOCKED 5 - Low volume")
        return True  # BLOCK

    # --- FILTER 6: BTC TREND ---
    # Blocks short when BTC pumping
    if signal_type == "SHORT" and btc_trend == "UP":
        print(f"BLOCKED 6 - BTC UP, no short")
        return True  # BLOCK

    print(f"PASSED ALL - Location {location*100:.0f}% | RSI {rsi_1h} | Premium {premium}")
    return False  # ALLOW TRADE
