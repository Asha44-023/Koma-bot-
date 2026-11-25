# V900.3 FINAL - Pumped vs Shed - BOTH WAYS - BEST ONLY + LEG 2 RE-ENTRY
# V900.3 UPDATE 2026-11-25 - MEXC + COINGECKO BOTH - REAL MONTHLY / WEEKLY FETCH
# MEXC = TRUTH (price, monthly, weekly). CoinGecko = BACKUP if MEXC kline empty.
# If both disagree >5%, MEXC wins. CoinGecko was wrong 24 Nov: EVAA $2.54 vs MEXC $1.9762.
# PURE MATH ONLY - No trendlines, no support, no patterns. Only % + Low > Low comparisons.
# MONTHLY: Pump >100% + Shed -30% to -60% = TAKE. WEEKLY: Last Low > Prev Low = HL = TAKE, Last Low < Prev Low = LL = WAIT.
# PUMP 2D BLOCK = 10% | MEXC 24H BLOCK = 30% | SHED COOLING = 10% | TRACKER = tracker.json
import json, os, requests, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
UTC = timezone.utc
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"
TRACKER_FILE = "tracker.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

MIN_VOLUME = 5000000
MAX_ACTIVE_DAYS = 7
WARNING_DAY = 5
MAX_SIGNALS_PER_SCAN = 4
GROUP_RANK = {"Big": 3, "Mid": 2, "Small": 1}

PUMP_BLOCK_PCT = 10.0
SHED_DONE_BLOCK = 0.90
MAX_SPIKES_7D = 2
FRESH_SPIKE_48H_PCT = 90.0
MEXC_24H_BLOCK = 30.0
SHED_COOLING_MAX = 10.0

MONTHLY_PUMP_MIN = 100.0
MONTHLY_SHED_MIN = 30.0
MONTHLY_SHED_MAX = 60.0
MEXC_VS_GECKO_MAX_DIFF = 5.0

EXPECTED_DAYS = {"Small": "3-5 days", "Mid": "2-4 days", "Big": "1-3 days"}
LEG2_BOUNCE_PCT = 0.12
LEG2_CONFIRM_PCT = 0.02

def load_json(path, default):
    try:
        with open(path) as f:
            data = json.load(f)
            if isinstance(default, list) and not isinstance(data, list):
                return []
            if isinstance(default, dict) and not isinstance(data, dict):
                return {}
            return data
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM ERROR: Token/Chat missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"TELEGRAM: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"TELEGRAM EXCEPTION: {e}")

def fmt(p):
    return f"{p:.8f}".rstrip('0').rstrip('.')

# --- NEW 2026-11-25 - MONTHLY / WEEKLY - MEXC + COINGECKO BOTH ---
def calc_monthly_pump(monthly_low, monthly_high):
    if monthly_low <= 0: return 0
    return (monthly_high - monthly_low) / monthly_low * 100

def calc_monthly_shed(monthly_high, current_price):
    if monthly_high <= 0: return 0
    return (current_price - monthly_high) / monthly_high * 100

def check_weekly_structure(weekly_lows):
    if len(weekly_lows) < 2: return "UNKNOWN", "WAIT - Not enough weekly lows"
    last = weekly_lows[-1]
    prev = weekly_lows[-2]
    if last > prev:
        return "HL", "HL formed - Anticipate HH next - BUY the HL"
    else:
        return "LL", "New LL - Anticipate LH next - WAIT, DO NOT BUY"

def get_mexc_kline(sym, interval):
    # interval: Month1, Week1, Day1
    # MEXC returns list of [time, open, high, low, close, volume...] or dict
    try:
        url = f"https://contract.mexc.com/api/v1/contract/kline/{sym}_USDT?interval={interval}"
        r = requests.get(url, timeout=15).json()
        data = r.get("data", []) if isinstance(r, dict) else r
        if not data: return []
        candles = []
        for c in data:
            # Handle both list and dict formats
            if isinstance(c, list) and len(c) >= 5:
                candles.append({"time": c[0], "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4])})
            elif isinstance(c, dict):
                candles.append({"time": c.get("time", c.get("t", 0)), "open": float(c.get("open", c.get("o", 0)) or 0), "high": float(c.get("high", c.get("h", 0)) or 0), "low": float(c.get("low", c.get("l", 0)) or 0), "close": float(c.get("close", c.get("c", 0)) or 0)})
        return candles
    except Exception as e:
        print(f"MEXC KLINE ERROR {sym} {interval}: {e}")
        return []

def get_gecko_90d(gecko_id):
    # Fallback: 90 days daily prices from CoinGecko
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{gecko_id}/market_chart?vs_currency=usd&days=90"
        r = requests.get(url, timeout=20).json()
        prices = r.get("prices", [])
        return [p[1] for p in prices]
    except Exception as e:
        print(f"GECKO 90D ERROR {gecko_id}: {e}")
        return []

def get_monthly_weekly(sym, gecko_id, current_price):
    # Tries MEXC first, CoinGecko second. Returns dict with monthly_pump, monthly_shed, weekly_lows, source
    monthly_low = 0
    monthly_high = 0
    weekly_lows = []
    source = "NONE"
    # 1. MEXC Monthly
    mexc_month = get_mexc_kline(sym, "Month1")
    mexc_week = get_mexc_kline(sym, "Week1")
    mexc_ok = False
    if mexc_month and len(mexc_month) >= 1:
        # Use last completed month candle + current month if available
        # Take last 2 candles to cover full monthly range
        last_months = mexc_month[-2:] if len(mexc_month) >= 2 else mexc_month
        monthly_low = min([c["low"] for c in last_months if c["low"] > 0])
        monthly_high = max([c["high"] for c in last_months if c["high"] > 0])
        mexc_ok = True
    if mexc_week and len(mexc_week) >= 2:
        weekly_lows = [c["low"] for c in mexc_week[-3:] if c["low"] > 0]
    # If MEXC monthly missing, try CoinGecko 90d
    gecko_low = 0
    gecko_high = 0
    gecko_weekly = []
    if not mexc_ok or not weekly_lows:
        if gecko_id:
            prices_90d = get_gecko_90d(gecko_id)
            if prices_90d and len(prices_90d) >= 30:
                last_30d = prices_90d[-30:]
                gecko_low = min(last_30d)
                gecko_high = max(last_30d)
                # Weekly lows from 90d: split into 7-day chunks, take low of each week, last 3 weeks
                chunks = [prices_90d[i:i+7] for i in range(0, len(prices_90d), 7)]
                gecko_weekly = [min(ch) for ch in chunks[-3:] if ch]
    # Decide source
    if mexc_ok and monthly_low > 0:
        source = "MEXC"
        # If Gecko also exists and disagrees >5% on monthly high, trust MEXC, log it
        if gecko_high > 0 and monthly_high > 0:
            diff = abs(gecko_high - monthly_high) / monthly_high * 100
            if diff > MEXC_VS_GECKO_MAX_DIFF:
                print(f"{sym} MEXC vs GECKO diff {diff:.1f}% on monthly high - TRUST MEXC: {fmt(monthly_high)} vs Gecko {fmt(gecko_high)}")
        # If MEXC weekly missing but Gecko has it, use Gecko weekly as backup
        if not weekly_lows and gecko_weekly:
            weekly_lows = gecko_weekly
            source = "MEXC+ GECKO-WEEKLY"
    elif gecko_low > 0:
        monthly_low = gecko_low
        monthly_high = gecko_high
        weekly_lows = gecko_weekly
        source = "COINGECKO-BACKUP"
    else:
        return {"monthly_pump": 0, "monthly_shed": 0, "monthly_low": 0, "monthly_high": 0, "weekly_lows": [], "weekly_state": "UNKNOWN", "source": "NONE", "has_data": False}
    monthly_pump = calc_monthly_pump(monthly_low, monthly_high)
    monthly_shed = calc_monthly_shed(monthly_high, current_price)
    weekly_state, weekly_reason = check_weekly_structure(weekly_lows)
    return {"monthly_pump": monthly_pump, "monthly_shed": monthly_shed, "monthly_low": monthly_low, "monthly_high": monthly_high, "weekly_lows": weekly_lows, "weekly_state": weekly_state, "weekly_reason": weekly_reason, "source": source, "has_data": True}

def get_tracker():
    t = load_json(TRACKER_FILE, {"wins": 0, "losses": 0, "total_pnl_pct": 0.0, "history": []})
    if not isinstance(t, dict): t = {"wins": 0, "losses": 0, "total_pnl_pct": 0.0, "history": []}
    return t

def update_tracker(sym, side, group, result_pct, hit):
    t = get_tracker()
    if result_pct >= 0: t["wins"] += 1
    else: t["losses"] += 1
    t["total_pnl_pct"] = round(t.get("total_pnl_pct", 0) + result_pct, 2)
    t["history"].append({"sym": sym, "side": side, "group": group, "hit": hit, "pnl_pct": round(result_pct, 2), "time": datetime.now(TZ).isoformat()})
    save_json(TRACKER_FILE, t)
    total = t["wins"] + t["losses"]
    win_rate = (t["wins"] / total * 100) if total > 0 else 0
    msg = f"\n\n📊 <b>TRACKER UPDATE</b>\nRecord: {t['wins']}W - {t['losses']}L\nWin Rate: {win_rate:.0f}%\nTotal P&L: {t['total_pnl_pct']:+.1f}%"
    return msg

def get_group(cap_at_low):
    if cap_at_low < 200_000_000: return "Small", 150.0, 45.0, 0.75
    elif cap_at_low <= 2_000_000_000: return "Mid", 100.0, 30.0, 0.60
    else: return "Big", 60.0, 20.0, 0.53

def get_tps_range(side, high, low, ret2, entry):
    rng = high - low
    ret1 = ret2 * 0.5
    if side == "SHORT":
        tp1 = high - ret1 * rng; tp2 = high - ret2 * rng; runner = high - 1.00 * rng; sl = entry * 1.10
    else:
        tp1 = low + ret1 * rng; tp2 = low + ret2 * rng; runner = low + 1.00 * rng; sl = entry * 0.90
    return tp1, tp2, runner, sl

def get_low_2d(spark):
    if not spark: return 0
    if len(spark) >= 48: window = spark[-48:]
    else:
        cut = max(1, int(len(spark) * 2 / 7))
        window = spark[-cut:]
    return min(window)

def is_tp1_only(group, shed, expected_shed, days_ago):
    if expected_shed <= 0: return False
    shed_ratio = shed / expected_shed
    if group == "Small": return shed_ratio < 0.60 and days_ago <= 3
    elif group == "Mid": return shed_ratio < 0.70 and days_ago <= 4
    else: return shed_ratio < 0.75 and days_ago <= 5

def days_since_spike(spark):
    if not spark or len(spark) < 48: return 99, 0, []
    n = len(spark); daily_closes = []; chunk = n // 7
    for i in range(7):
        start = i * chunk; end = (i + 1) * chunk if i < 6 else n
        daily_closes.append(spark[end - 1])
    spike_idx = -1; spike_pct = 0
    for i in range(1, len(daily_closes)):
        if daily_closes[i-1] <= 0: continue
        chg = (daily_closes[i] - daily_closes[i-1]) / daily_closes[i-1] * 100
        if chg > 50: spike_idx = i; spike_pct = chg
    if spike_idx == -1: return 99, 0, daily_closes
    days_ago = (len(daily_closes) - 1) - spike_idx
    return days_ago, spike_pct, daily_closes

def count_spikes_7d(spark):
    if not spark or len(spark) < 48: return 0
    n = len(spark); chunk = n // 7; daily_closes = []
    for i in range(7):
        start = i * chunk; end = (i + 1) * chunk if i < 6 else n
        daily_closes.append(spark[end - 1])
    count = 0
    for i in range(1, len(daily_closes)):
        if daily_closes[i-1] <= 0: continue
        chg = (daily_closes[i] - daily_closes[i-1]) / daily_closes[i-1] * 100
        if chg > 50: count += 1
    return count

def fresh_spike_48h_pct(spark):
    if not spark or len(spark) < 10: return 0
    window = spark[-48:] if len(spark) >= 48 else spark
    lo = min(window); hi = max(window)
    if lo <= 0: return 0
    return (hi - lo) / lo * 100

def parse_mexc_24h_change(t):
    for key in ["riseFallRate", "riseFallRate24", "priceChangePercent", "change24", "riseFallValueRate"]:
        if key in t and t.get(key) is not None:
            try:
                v = float(t.get(key))
                if abs(v) < 2: return v * 100.0
                return v
            except: continue
    try:
        last = float(t.get("lastPrice", 0) or 0)
        diff = float(t.get("riseFallValue", 0) or 0)
        if last != 0 and diff != 0:
            prev = last - diff
            if prev != 0: return diff / prev * 100.0
    except: pass
    return 0.0

def get_global_data():
    result = {}
    for page in [1, 2, 3, 4]:
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}&price_change_percentage=7d&sparkline=true", timeout=20).json()
            for c in r:
                sym = c.get("symbol","").upper()
                if sym not in result:
                    spark = c.get("sparkline_in_7d", {}).get("price", []) or []
                    result[sym] = {"cap_now": c.get("market_cap",0) or 0, "global_price": c.get("current_price",0) or 0, "global_vol": c.get("total_volume",0) or 0, "gecko_id": c.get("id"), "change_7d": c.get("price_change_percentage_7d_in_currency", 0) or 0, "spark_7d": spark}
        except Exception as e:
            print(f"GLOBAL API ERROR page {page}: {e}")
            break
    return result

def get_mexc_perps():
    SKIP_SUFFIX = ["STOCK", "STOCKS"]
    SKIP_EXACT = {"XAU","XAG","NVIDIA","ANTHROPIC","OPENAI","SPX","NASDAQ","DJI","US100","US30","GOLD","SILVER","OIL","BTCDOM"}
    r = requests.get("https://contract.mexc.com/api/v1/contract/ticker", timeout=20).json()
    data_list = r.get("data",[]) if isinstance(r, dict) else r
    movers = {}
    for t in data_list:
        sym_raw = t.get('symbol','')
        if "_USDT" not in sym_raw: continue
        sym = sym_raw.replace("_USDT","")
        if sym in ["BTC","ETH","BNB","SOL","XRP","DOGE"]: continue
        if sym in SKIP_EXACT: continue
        if any(sym.endswith(s) for s in SKIP_SUFFIX): continue
        if "STOCK" in sym: continue
        try:
            price = float(t.get('lastPrice',0) or 0)
            amount24 = float(t.get('amount24',0) or 0)
            volume24 = float(t.get('volume24',0) or 0)
            vol = amount24 if amount24 > 1000 else volume24 * price
        except: continue
        if price == 0: continue
        change_24h = parse_mexc_24h_change(t)
        movers[sym] = {"price": price, "vol": vol, "symbol": sym_raw, "change_24h": change_24h}
    return movers

def analyze_outcome(sig, cur, days):
    entry = sig.get("price", 0); tp1 = sig.get("tp1", 0); high_7d = sig.get("high_7d", entry)
    if entry == 0 or tp1 == 0: return 30, "Unknown - no data", "WAIT - No clear next signal", 0, 40, 30
    total_dist = abs(entry - tp1)
    moved = abs(entry - cur) if (sig.get("side")=="SHORT" and cur < entry) or (sig.get("side")=="LONG" and cur > entry) else -abs(cur - entry)
    progress = max(0, min(100, (moved / total_dist * 100) if total_dist > 0 else 0))
    if progress >= 70: p_tp1, p_chop, p_sl = 65, 25, 10; cause = "On track - move in progress, momentum intact"
    elif progress >= 40: p_tp1, p_chop, p_sl = 45, 35, 20; cause = "Slowing - move stalled, opposite side defending"
    elif progress >= 20: p_tp1, p_chop, p_sl = 30, 45, 25; cause = "Momentum lost - stalled for days, volume fading"
    else:
        if (sig.get("side")=="SHORT" and cur >= entry) or (sig.get("side")=="LONG" and cur <= entry): p_tp1, p_chop, p_sl = 15, 35, 50; cause = "Invalidated - price back past entry, thesis wrong"
        else: p_tp1, p_chop, p_sl = 20, 50, 30; cause = "Dead - no momentum, chop / sideways"
    if days >= 5 and progress < 50: p_tp1 = max(10, p_tp1 - 15); p_chop = p_chop + 10; cause += " | Overdue - past expected 3-5 days"
    if sig.get("side")=="SHORT":
        if cur >= high_7d or cur >= entry * 1.05: next_sig = "INVALIDATED - DO NOT RE-SHORT | Next: WATCH LONG if it holds above high for 24h\nRe-short only if pumps +15% to " + fmt(entry * 1.15) + " then rejects"
        elif progress >= 50: next_sig = f"HOLD / RE-SHORT ON BOUNCE | Next: If bounces +12% to {fmt(cur * 1.12)} and rejects, re-short"
        elif progress >= 20: next_sig = "WAIT - Shed never started properly | Next: Ignore until fresh pump +50% from here, then re-evaluate"
        else: next_sig = "NO TRADE - Chop / Invalidated | Next: Move on, ignore coin until new pump"
    else:
        low_7d = sig.get("low_7d", entry)
        if cur <= low_7d or cur <= entry * 0.95: next_sig = "INVALIDATED - DO NOT RE-LONG | Broke below low, dump won\nRe-long only if dumps -15% to " + fmt(entry * 0.85) + " then holds"
        elif progress >= 50: next_sig = f"HOLD / RE-LONG ON DIP | Next: If dips -12% to {fmt(cur * 0.88)} and holds, re-long"
        elif progress >= 20: next_sig = "WAIT - Bounce never started properly | Next: Ignore until fresh dump -50% from here, then re-evaluate"
        else: next_sig = "NO TRADE - Chop / Invalidated | Next: Move on, ignore coin until new pump"
    return p_tp1, cause, next_sig, progress, p_chop, p_sl

def analyze_sl(sig, cur, days):
    entry = sig.get("price", 0); high_7d = sig.get("high_7d", entry); low_7d = sig.get("low_7d", entry); side = sig.get("side","SHORT")
    if side == "SHORT":
        above_high_pct = (cur - high_7d) / high_7d * 100 if high_7d > 0 else 0
        if cur >= high_7d:
            cause = f"Invalidated - price broke above 7d high (+{above_high_pct:.1f}% above high). Pump won, buyers in control. Short thesis dead."
            p_pump_again, p_dump, p_chop = 70, 15, 15
            next_sig = "DO NOT RE-SHORT - Pump is still alive\nNext: 1) WAIT 24h - if holds above high, WATCH LONG\n2) Only re-short if it pumps +50% fresh from here and then rejects\n3) If it dumps back below entry, re-short on bounce to entry"
        elif cur >= entry:
            cause = "Shed failed - price reclaimed entry. Buyers defended, momentum flipped."
            p_pump_again, p_dump, p_chop = 55, 25, 20
            next_sig = "DO NOT RE-SHORT immediately\nNext: WAIT 24h. If price holds above entry, invalidated. If it falls back below entry and rejects, then re-short on bounce."
        else:
            cause = "SL hit on wick / volatility - price spiked to SL then fell back"
            p_pump_again, p_dump, p_chop = 35, 40, 25
            next_sig = "WICK SL - Can re-short on bounce\nNext: Wait for bounce +10% to entry, if it rejects, re-short with same SL."
    else:
        below_low_pct = (low_7d - cur) / low_7d * 100 if low_7d > 0 else 0
        if cur <= low_7d:
            cause = f"Invalidated - price broke below 7d low (-{below_low_pct:.1f}% below low). Dump won, sellers in control. Long thesis dead."
            p_pump_again, p_dump, p_chop = 15, 70, 15
            next_sig = "DO NOT RE-LONG - Dump is still alive\nNext: 1) WAIT 24h - if holds below low, WATCH SHORT\n2) Only re-long if it dumps -50% fresh from here and then holds\n3) If it bounces back above entry, re-long on dip to entry"
        elif cur <= entry:
            cause = "Bounce failed - price fell back below entry. Sellers defended, momentum flipped."
            p_pump_again, p_dump, p_chop = 25, 55, 20
            next_sig = "DO NOT RE-LONG immediately\nNext: WAIT 24h. If price holds below entry, invalidated. If it bounces back above entry and holds, then re-long on dip."
        else:
            cause = "SL hit on wick / volatility - price dipped to SL then bounced back"
            p_pump_again, p_dump, p_chop = 40, 35, 25
            next_sig = "WICK SL - Can re-long on dip\nNext: Wait for dip -10% to entry, if it holds, re-long with same SL."
    return cause, next_sig, p_pump_again, p_dump, p_chop

def check_active_tps(active, mexc, global_data):
    history = load_json(HISTORY_FILE, [])
    if not isinstance(history, list): history = []
    now = datetime.now(TZ)
    to_remove = []
    for sym, sig in list(active.items()):
        cur = None
        if sym in mexc: cur = mexc[sym]["price"]
        elif sym in global_data: cur = global_data[sym]["global_price"]
        if not cur: continue
        entry = sig.get("price", 0)
        if not entry: continue
        try:
            t = datetime.fromisoformat(str(sig.get("time","")).replace("Z","+00:00"))
            if t.tzinfo is None: t = t.replace(tzinfo=TZ)
            days = (now - t).total_seconds() / 86400
        except: days = 0
        side = sig.get("side", "SHORT")
        tp1, tp2, runner, sl = sig.get("tp1",0), sig.get("tp2",0), sig.get("runner",0), sig.get("sl",0)
        group = sig.get("group","Small")
        expected = EXPECTED_DAYS.get(group, "3-5 days")
        leg = sig.get("leg", 1)
        if leg == 2 and not sig.get("leg2_active"):
            tp2_hit = (cur <= tp2) if side == "SHORT" else (cur >= tp2)
            runner_hit = (cur <= runner) if side == "SHORT" else (cur >= runner)
            if runner_hit or tp2_hit:
                hit_label = "RUNNER HIT WITHOUT LEG 2 - LEG 2 SKIPPED" if runner_hit else "TP2 HIT WITHOUT LEG 2 - LEG 2 SKIPPED"
                pct = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
                tracker_msg = update_tracker(sym, side, group, pct, hit_label)
                msg = f"✅ <b>{sym} {hit_label}</b> - {group}\nLeg 1 TP1 hit, then price ran straight through TP2 without the 12% bounce/dip.\nLeg 1 Entry: {fmt(entry)} -> Now: {fmt(cur)}\nProfit if held from Leg 1: {pct:+.1f}%\nTP2 was: {fmt(tp2)} | Runner was: {fmt(runner)}\nLeg 2 bounce/dip to {fmt(sig.get('bounce_target', 0))} NEVER came - LEG 2 SKIPPED, DO NOT wait for it.\nDays taken: {days:.2f} days (Expected: {expected}){tracker_msg}"
                send_telegram(msg)
                record = {"sym": sym, "side": side, "group": group, "entry": entry, "exit_price": cur, "hit": hit_label, "pumped": sig.get("pumped"), "shed": sig.get("shed"), "time_in": sig.get("time"), "time_out": now.isoformat(), "days_taken": round(days, 2), "expected_days": expected, "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl}
                history.append(record); save_json(HISTORY_FILE, history); to_remove.append(sym)
                continue
        if leg == 2 and not sig.get("leg2_active"):
            tp1_price = sig.get("tp1_hit_price", tp1); bounce_target = sig.get("bounce_target", 0); bounce_high = sig.get("bounce_high", 0); bounce_done = sig.get("bounce_done", False)
            if side == "SHORT":
                if cur > bounce_high: sig["bounce_high"] = cur; bounce_high = cur
                if not bounce_done and cur >= bounce_target:
                    sig["bounce_done"] = True
                    send_telegram(f"📈 <b>{sym} LEG 2 - BOUNCE REACHED</b> - {group}\nTP1 was {fmt(tp1_price)} -> Bounced to {fmt(cur)} (+{LEG2_BOUNCE_PCT*100:.0f}%)\nNow WAIT for rejection - re-entry when price falls 2% below bounce high.\nBounce High so far: {fmt(bounce_high)}\nDo NOT enter yet.")
                    continue
                if bounce_done and cur <= bounce_high * (1 - LEG2_CONFIRM_PCT):
                    new_entry = cur; new_sl = round(bounce_high * 1.02, 8); new_tp1 = tp2; new_tp2 = runner; new_runner = round(sig.get("low_7d", tp2), 8)
                    send_telegram(f"🔁 <b>LEG 2 RE-ENTRY SHORT {sym}</b> - {group}\nLeg 1 TP1 {fmt(tp1_price)} hit, bounced to {fmt(bounce_high)}, rejected.\n\n🎯 <b>ENTER AT: {fmt(new_entry)}</b>\nEntry Zone: {fmt(new_entry*0.98)} - {fmt(new_entry*1.02)}\nSL: {fmt(new_sl)} (above bounce high)\nTP1: {fmt(new_tp1)} (old TP2)\nTP2: {fmt(new_tp2)} (old Runner)\nRunner: {fmt(new_runner)} (= Low 7d)\nValid Until: {(now + timedelta(hours=1)).strftime('%H:%M')} EAT (+1h) - If outside zone, SKIP")
                    sig.update({"price": new_entry, "sl": new_sl, "tp1": new_tp1, "tp2": new_tp2, "runner": new_runner, "leg": 2, "leg2_active": True, "time": now.isoformat()})
                    continue
                if days >= MAX_ACTIVE_DAYS:
                    record = {"sym": sym, "side": side, "group": group, "entry": entry, "exit_price": cur, "hit": "TP1 + LEG2 EXPIRED - No bounce", "pumped": sig.get("pumped"), "shed": sig.get("shed"), "time_in": sig.get("time"), "time_out": now.isoformat(), "days_taken": round(days, 2), "expected_days": expected, "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl}
                    history.append(record); save_json(HISTORY_FILE, history); to_remove.append(sym)
                    send_telegram(f"⏰ <b>{sym} LEG 2 EXPIRED</b> - TP1 was hit, but no +12% bounce in {days:.1f}d. Closing. Profit from Leg 1 kept.")
                continue
            else:
                if cur < bounce_high or bounce_high == 0: sig["bounce_high"] = cur; bounce_high = cur
                if not bounce_done and cur <= bounce_target:
                    sig["bounce_done"] = True
                    send_telegram(f"📉 <b>{sym} LEG 2 - DIP REACHED</b> - {group}\nTP1 was {fmt(tp1_price)} -> Dipped to {fmt(cur)} (-{LEG2_BOUNCE_PCT*100:.0f}%)\nNow WAIT for hold - re-entry when price rises 2% above dip low.\nDip Low so far: {fmt(bounce_high)}\nDo NOT enter yet.")
                    continue
                if bounce_done and cur >= bounce_high * (1 + LEG2_CONFIRM_PCT):
                    new_entry = cur; new_sl = round(bounce_high * 0.98, 8); new_tp1 = tp2; new_tp2 = runner; new_runner = round(sig.get("high_7d", tp2), 8)
                    send_telegram(f"🔁 <b>LEG 2 RE-ENTRY LONG {sym}</b> - {group}\nLeg 1 TP1 {fmt(tp1_price)} hit, dipped to {fmt(bounce_high)}, held.\n\n🎯 <b>ENTER AT: {fmt(new_entry)}</b>\nEntry Zone: {fmt(new_entry*0.98)} - {fmt(new_entry*1.02)}\nSL: {fmt(new_sl)} (below dip low)\nTP1: {fmt(new_tp1)} (old TP2)\nTP2: {fmt(new_tp2)} (old Runner)\nRunner: {fmt(new_runner)} (= High 7d)\nValid Until: {(now + timedelta(hours=1)).strftime('%H:%M')} EAT (+1h) - If outside zone, SKIP")
                    sig.update({"price": new_entry, "sl": new_sl, "tp1": new_tp1, "tp2": new_tp2, "runner": new_runner, "leg": 2, "leg2_active": True, "time": now.isoformat()})
                    continue
                if days >= MAX_ACTIVE_DAYS:
                    record = {"sym": sym, "side": side, "group": group, "entry": entry, "exit_price": cur, "hit": "TP1 + LEG2 EXPIRED - No dip", "pumped": sig.get("pumped"), "shed": sig.get("shed"), "time_in": sig.get("time"), "time_out": now.isoformat(), "days_taken": round(days, 2), "expected_days": expected, "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl}
                    history.append(record); save_json(HISTORY_FILE, history); to_remove.append(sym)
                    send_telegram(f"⏰ <b>{sym} LEG 2 EXPIRED</b> - TP1 was hit, but no -12% dip in {days:.1f}d. Closing. Profit from Leg 1 kept.")
                continue
        hit = None
        if sig.get("leg2_active"):
            if side == "SHORT":
                if cur <= runner: hit = "RUNNER"
                elif cur <= tp2: hit = "TP2"
                elif cur <= tp1: hit = "TP1-LEG2"
                elif cur >= sl: hit = "SL-LEG2"
            else:
                if cur >= runner: hit = "RUNNER"
                elif cur >= tp2: hit = "TP2"
                elif cur >= tp1: hit = "TP1-LEG2"
                elif cur <= sl: hit = "SL-LEG2"
        else:
            if side == "SHORT":
                if cur <= runner: hit = "RUNNER"
                elif cur <= tp2: hit = "TP2"
                elif cur <= tp1: hit = "TP1"
                elif cur >= sl: hit = "SL"
            else:
                if cur >= runner: hit = "RUNNER"
                elif cur >= tp2: hit = "TP2"
                elif cur >= tp1: hit = "TP1"
                elif cur <= sl: hit = "SL"
        if not hit and days >= WARNING_DAY and not sig.get("warned_5d") and not sig.get("leg2_active"):
            p_tp1, cause, next_sig, progress, p_chop, p_sl = analyze_outcome(sig, cur, days)
            pct_now = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
            send_telegram(f"⚠️ <b>{sym} Day {days:.1f} WARNING</b> - {group}\nStill no TP1 after {days:.1f} days (Expected: {expected})\nNow: {fmt(cur)} | Result so far: {pct_now:+.1f}% | Progress to TP1: {progress:.0f}%\nProbability to still hit TP1: {p_tp1}% | Chop: {p_chop}% | SL: {p_sl}%\nProbable Cause: {cause}\nAction: Consider exiting / move SL to entry. Bot will auto-expire on Day {MAX_ACTIVE_DAYS}.")
            sig["warned_5d"] = True
        if not hit and days >= MAX_ACTIVE_DAYS: hit = "EXPIRED"
        if hit:
            if hit == "TP1" and not sig.get("leg2_active"):
                if sig.get("tp1_only"):
                    pct = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
                    tracker_msg = update_tracker(sym, side, group, pct, "TP1-ONLY")
                    send_telegram(f"✅ <b>{sym} TP1 HIT - TP1 ONLY - CLOSE ALL</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nProfit: {pct:+.1f}%\nDays taken: {days:.2f} days (Expected: {expected})\nPumped was +{sig.get('pumped',0):.1f}% | Shed was -{sig.get('shed',0):.1f}%\n\n🔒 <b>TP1 ONLY MODE - NO LEG 2</b>\nReason: Fresh pump - spike was {sig.get('days_since_spike','?')}d ago, shed not mostly done.\nPump still alive, DO NOT wait for TP2 / Leg 2. Take profit and move on.{tracker_msg}")
                    record = {"sym": sym, "side": side, "group": group, "entry": entry, "exit_price": cur, "hit": "TP1-ONLY", "pumped": sig.get("pumped"), "shed": sig.get("shed"), "time_in": sig.get("time"), "time_out": now.isoformat(), "days_taken": round(days, 2), "expected_days": expected, "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl}
                    history.append(record); save_json(HISTORY_FILE, history); to_remove.append(sym)
                    continue
                pct = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
                if side == "SHORT":
                    bounce_target = round(cur * (1 + LEG2_BOUNCE_PCT), 8)
                    bounce_msg = f"Wait for +12% bounce to {fmt(bounce_target)} then rejection, then re-enter SHORT to TP2 {fmt(tp2)}"
                else:
                    bounce_target = round(cur * (1 - LEG2_BOUNCE_PCT), 8)
                    bounce_msg = f"Wait for -12% dip to {fmt(bounce_target)} then hold, then re-enter LONG to TP2 {fmt(tp2)}"
                send_telegram(f"✅ <b>{sym} TP1 HIT - TAKE PROFIT - LEG 1 DONE - SELL HALF</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nProfit: {pct:+.1f}% - SELL HALF, MOVE SL TO ENTRY\nDays taken: {days:.2f} days (Expected: {expected})\nPumped was +{sig.get('pumped',0):.1f}%\n\n🔁 <b>LEG 2 - WAITING FOR BOUNCE/DIP</b>\n{bounce_msg}\nBot will alert you when bounce is reached and when to re-enter. DO NOT chase now.")
                sig.update({"leg": 2, "tp1_hit_price": cur, "bounce_target": bounce_target, "bounce_high": cur, "bounce_done": False, "leg2_active": False, "warned_5d": False, "time": now.isoformat(), "sl": entry})
                continue
            record = {"sym": sym, "side": side, "group": group, "entry": entry, "exit_price": cur, "hit": hit, "pumped": sig.get("pumped"), "shed": sig.get("shed"), "time_in": sig.get("time"), "time_out": now.isoformat(), "days_taken": round(days, 2), "expected_days": expected, "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl}
            history.append(record); save_json(HISTORY_FILE, history); to_remove.append(sym)
            pct = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
            if hit == "EXPIRED":
                p_tp1, cause, next_sig, progress, p_chop, p_sl = analyze_outcome(sig, cur, days)
                tracker_msg = update_tracker(sym, side, group, pct, hit)
                send_telegram(f"⏰ <b>{sym} EXPIRED</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nResult: {pct:+.1f}% | Progress to TP1: {progress:.0f}% | Days held: {days:.2f} (Expected: {expected})\n\n📊 <b>Probability if held longer:</b>\nTP1: {p_tp1}% | Chop: {p_chop}% | SL: {p_sl}%\n\n🔍 <b>Probable Cause:</b>\n{cause}\n\n➡️ <b>Next Signal:</b>\n{next_sig}\n\nClosing - no more tracking{tracker_msg}")
            elif hit in ("SL", "SL-LEG2"):
                cause, next_sig, p_pump, p_dump, p_chop = analyze_sl(sig, cur, days)
                leg_label = "LEG 2" if "LEG2" in hit else "LEG 1"
                tracker_msg = update_tracker(sym, side, group, pct, hit)
                send_telegram(f"🛑 <b>{sym} SL HIT ({leg_label}) - DELETED FROM ACTIVE</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nLoss: {pct:+.1f}% | Days: {days:.2f} (Expected: {expected})\nRemoved from ACTIVE - will NOT be tracked anymore.\n\n🔍 <b>Probable Cause:</b>\n{cause}\n\n📊 <b>What to expect next:</b>\nPump again: {p_pump}% | Dump back: {p_dump}% | Chop: {p_chop}%\n\n➡️ <b>Next Signal:</b>\n{next_sig}{tracker_msg}")
            else:
                tracker_msg = update_tracker(sym, side, group, pct, hit)
                send_telegram(f"✅ <b>{sym} {hit} HIT - DELETED FROM ACTIVE</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nProfit: {pct:+.1f}%\nDays taken: {days:.2f} days (Expected: {expected})\nPumped was +{sig.get('pumped',0):.1f}%{tracker_msg}")
    for sym in to_remove:
        if sym in active: del active[sym]
    return active

def run_once():
    active = load_json(ACTIVE_FILE, {})
    now = datetime.now(TZ)
    fresh = {}
    for k,v in active.items():
        try:
            t = datetime.fromisoformat(str(v.get("time","")).replace("Z","+00:00"))
            if t.tzinfo is None: t = t.replace(tzinfo=TZ)
            if (now - t).total_seconds() < MAX_ACTIVE_DAYS*24*3600: fresh[k]=v
        except: fresh[k]=v
    active = fresh
    print(f"Active: {len(active)} - {list(active.keys())}")
    global_data = get_global_data()
    mexc = get_mexc_perps()
    print(f"MEXC perps: {len(mexc)} | Global: {len(global_data)}")
    active = check_active_tps(active, mexc, global_data)
    candidates = []
    for sym, m in mexc.items():
        if sym in active:
            print(f"{sym} SKIP - Already active")
            continue
        price_exec = m["price"]; vol_local = m["vol"]; change_24h = m.get("change_24h", 0.0)
        g = global_data.get(sym, {})
        cap_now = g.get("cap_now", 0); global_price = g.get("global_price", price_exec); global_vol = g.get("global_vol", vol_local)
        gecko_id = g.get("gecko_id")
        if cap_now == 0 or global_price == 0:
            print(f"{sym} SKIP - No global data, cannot calc Pumped"); continue
        spark = g.get("spark_7d", [])
        if not spark:
            print(f"{sym} SKIP - No 7d sparkline"); continue
        low_7d = min(spark); high_7d = max(spark); low_2d = get_low_2d(spark)
        pump_2d = (global_price - low_2d) / low_2d * 100 if low_2d > 0 else 0
        pump_midpoint = (low_2d + high_7d) / 2 if low_2d > 0 else 0
        pump_dead = global_price < low_2d
        if pump_dead: pump_state = "DEAD"
        elif global_price < pump_midpoint: pump_state = "WEAKENING"
        else: pump_state = "ALIVE"
        cap_at_low = cap_now * (low_7d / global_price) if global_price > 0 else cap_now
        group, pump_thresh, expected_shed, ret2 = get_group(cap_at_low)
        pumped = (high_7d - low_7d) / low_7d * 100 if low_7d > 0 else 0
        shed = (high_7d - global_price) / high_7d * 100 if high_7d > 0 else 0
        net = (global_price - low_7d) / low_7d * 100 if low_7d > 0 else 0
        print(f"{sym} | {group} CapLow ${cap_at_low/1e6:.1f}M | Pumped7d +{pumped:.1f}% | Shed7d -{shed:.1f}% | Net +{net:.1f}% | Pump2d +{pump_2d:.1f}% | MEXC 24h {change_24h:+.2f}%")
        if max(global_vol, vol_local) < MIN_VOLUME:
            print(f"{sym} SKIP - Vol ${max(global_vol, vol_local):,.0f} < $5M"); continue
        if abs(change_24h) > MEXC_24H_BLOCK:
            print(f"{sym} SKIP V900.3 - MEXC 24H BLOCK - {change_24h:+.2f}% > +- {MEXC_24H_BLOCK:.0f}%"); continue
        spike_count = count_spikes_7d(spark); fresh_48h = fresh_spike_48h_pct(spark); shed_ratio = shed / expected_shed if expected_shed > 0 else 0
        if spike_count >= MAX_SPIKES_7D:
            print(f"{sym} SKIP - SECOND PUMP GUARD - {spike_count}x spikes"); continue
        if fresh_48h > FRESH_SPIKE_48H_PCT:
            print(f"{sym} SKIP - FRESH SPIKE GUARD - +{fresh_48h:.1f}%"); continue
        # NEW - REAL MONTHLY / WEEKLY - MEXC FIRST, COINGECKO BACKUP
        mw = get_monthly_weekly(sym, gecko_id, price_exec)
        if not mw.get("has_data"):
            print(f"{sym} SKIP - No Monthly/Weekly data from MEXC or CoinGecko"); continue
        monthly_pump = mw["monthly_pump"]; monthly_shed = mw["monthly_shed"]
        weekly_state = mw["weekly_state"]; weekly_lows = mw["weekly_lows"]; mw_source = mw["source"]
        print(f"{sym} MONTHLY [{mw_source}] Pump +{monthly_pump:.1f}% (need >{MONTHLY_PUMP_MIN:.0f}%) | Shed {monthly_shed:.1f}% (need -{MONTHLY_SHED_MIN:.0f}% to -{MONTHLY_SHED_MAX:.0f}%) | WEEKLY {weekly_state} Lows {weekly_lows}")
        if monthly_pump < MONTHLY_PUMP_MIN:
            print(f"{sym} SKIP - MONTHLY PUMP - +{monthly_pump:.1f}% < +{MONTHLY_PUMP_MIN:.0f}% - not a real pump"); continue
        if not (MONTHLY_SHED_MIN <= abs(monthly_shed) <= MONTHLY_SHED_MAX):
            print(f"{sym} SKIP - MONTHLY SHED - {monthly_shed:.1f}% not in -{MONTHLY_SHED_MIN:.0f}% to -{MONTHLY_SHED_MAX:.0f}% - shed not in zone"); continue
        if weekly_state == "LL":
            print(f"{sym} SKIP - WEEKLY LL - Last Low < Prev Low - Anticipate LH next - WAIT"); continue
        if weekly_state == "UNKNOWN":
            print(f"{sym} SKIP - WEEKLY UNKNOWN - Not enough weekly lows"); continue
        side = None; reason = ""
        if pumped >= pump_thresh:
            days_ago, spike_pct, daily_closes = days_since_spike(spark)
            print(f"{sym} Spike: {days_ago}d ago (+{spike_pct:.0f}%) | Shed ratio: {shed_ratio*100:.0f}% | MEXC 24h: {change_24h:+.2f}%")
            if days_ago < 2:
                print(f"{sym} SKIP - Spike {days_ago}d ago - TOO EARLY"); continue
            if shed < expected_shed:
                if shed_ratio >= SHED_DONE_BLOCK:
                    print(f"{sym} SKIP - SHED DONE GUARD - {shed_ratio*100:.0f}% done"); continue
                side = "SHORT"; reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed only -{shed:.1f}%, expected -{expected_shed}% - SHORT now | Spike was {days_ago}d ago | Monthly Pump +{monthly_pump:.1f}% Shed {monthly_shed:.1f}% Weekly {weekly_state}"
            else:
                if net <= 0:
                    print(f"{sym} SKIP LONG - Net {net:.1f}% <= 0"); continue
                if abs(change_24h) > SHED_COOLING_MAX:
                    print(f"{sym} SKIP LONG - SHED COOLING - MEXC 24h {change_24h:+.2f}%"); continue
                side = "LONG"; reason = f"{group} pumped +{pumped:.1f}%, shed -{shed:.1f}% DONE, net +{net:.1f}% - LONG bounce now | Spike was {days_ago}d ago | Monthly Pump +{monthly_pump:.1f}% Shed {monthly_shed:.1f}% Weekly {weekly_state} = HL, expect HH | MEXC 24h {change_24h:+.2f}% cooled"
        if pump_2d > PUMP_BLOCK_PCT:
            print(f"{sym} SKIP V900.3 - PUMP BLOCK - Pump2d +{pump_2d:.1f}% > +{PUMP_BLOCK_PCT:.0f}% (Low2d {fmt(low_2d)} -> Live {fmt(global_price)})")
            continue
        if side == "SHORT" and global_price >= high_7d:
            print(f"{sym} SKIP - Price still >= High"); continue
        if side == "LONG" and global_price <= low_7d:
            print(f"{sym} SKIP - Price still <= Low"); continue
        if side is None:
            print(f"{sym} SKIP - Pumped +{pumped:.1f}% < +{pump_thresh}%"); continue
        entry_price = price_exec; entry_high = round(price_exec * 1.02, 8); entry_low = round(price_exec * 0.98, 8); valid_until = now + timedelta(hours=1)
        tp1, tp2, runner, sl = get_tps_range(side, high_7d, low_7d, ret2, entry_price)
        tp1, tp2, runner, sl = round(tp1, 8), round(tp2, 8), round(runner, 8), round(sl, 8)
        if side == "LONG" and tp1 <= entry_price:
            print(f"{sym} SKIP - TP1 ALREADY PASSED - LONG TP1 {fmt(tp1)} <= Entry {fmt(entry_price)}"); continue
        if side == "SHORT" and tp1 >= entry_price:
            print(f"{sym} SKIP - TP1 ALREADY PASSED - SHORT TP1 {fmt(tp1)} >= Entry {fmt(entry_price)}"); continue
        emoji = "🔴" if side == "SHORT" else "🟢"
        tp1_only = is_tp1_only(group, shed, expected_shed, days_ago)
        print(f"{sym} TP1-ONLY: {tp1_only} | RANGE: High {fmt(high_7d)} Low {fmt(low_7d)} -> TP1 {fmt(tp1)} TP2 {fmt(tp2)} Runner {fmt(runner)} SL {fmt(sl)}")
        candidates.append({"sym": sym, "side": side, "price": entry_price, "entry_high": entry_high, "entry_low": entry_low, "valid_until": valid_until, "pumped": pumped, "shed": shed, "net": net, "cap_at_low": cap_at_low, "cap_now": cap_now, "group": group, "low_7d": low_7d, "high_7d": high_7d, "low_2d": low_2d, "pump_2d": pump_2d, "pump_midpoint": pump_midpoint, "pump_state": pump_state, "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner, "reason": reason, "emoji": emoji, "vol": max(global_vol, vol_local), "days_ago": days_ago, "spike_pct": spike_pct, "expected_shed": expected_shed, "ret2": ret2, "tp1_only": tp1_only, "monthly_pump": monthly_pump, "monthly_shed": monthly_shed, "weekly_state": weekly_state, "weekly_lows": weekly_lows, "mw_source": mw_source})
    if candidates:
        candidates.sort(key=lambda x: (GROUP_RANK.get(x["group"], 0), x["net"], x["vol"]), reverse=True)
        top_signals = candidates[:MAX_SIGNALS_PER_SCAN]
        for c in candidates[len(top_signals):]:
            print(f"SKIPPED - {c['sym']} {c['group']} Net +{c['net']:.1f}% - weaker than Top 4")
        for best in top_signals:
            sym = best["sym"]
            signal = {"sym": sym, "side": best["side"], "price": best["price"], "entry_high": best["entry_high"], "entry_low": best["entry_low"], "valid_until": best["valid_until"].isoformat(), "pumped": best["pumped"], "shed": best["shed"], "net": best["net"], "cap_at_low": best["cap_at_low"], "group": best["group"], "low_7d": best["low_7d"], "high_7d": best["high_7d"], "low_2d": best["low_2d"], "pump_2d": best["pump_2d"], "pump_midpoint": best["pump_midpoint"], "sl": best["sl"], "tp1": best["tp1"], "tp2": best["tp2"], "runner": best["runner"], "reason": best["reason"], "time": now.isoformat(), "warned_5d": False, "days_since_spike": best["days_ago"], "spike_pct": best["spike_pct"], "leg": 1, "leg2_active": False, "tp1_only": best["tp1_only"], "monthly_pump": best["monthly_pump"], "monthly_shed": best["monthly_shed"], "weekly_state": best["weekly_state"], "mw_source": best["mw_source"]}
            active[sym] = signal
            exp_days = EXPECTED_DAYS.get(best["group"], "3-5 days")
            mode_line = "🔒 TP1 ONLY - Fresh Pump, Close at TP1, NO Leg 2" if best["tp1_only"] else "🔁 TP1 + LEG 2 to TP2"
            msg = (f"{best['emoji']} <b>V900.3 PERP {best['side']} {sym}</b> - {best['group']} - BEST SIGNAL\nMode: {mode_line}\nExpected to TP2: {exp_days}\nCap at Low: ${best['cap_at_low']/1e6:.1f}M (Now ${best['cap_now']/1e6:.1f}M)\nMonthly [{best['mw_source']}]: Pump +{best['monthly_pump']:.1f}% | Shed {best['monthly_shed']:.1f}%\nWeekly: {best['weekly_state']} Lows {best['weekly_lows']} - Anticipate {'HH' if best['weekly_state']=='HL' else 'LH'} next\nPumped 7d: +{best['pumped']:.1f}%\nShed so far: -{best['shed']:.1f}% (Expected -{best['expected_shed']}%)\nNet: +{best['net']:.1f}%\nLow 7d: {fmt(best['low_7d'])} | High 7d: {fmt(best['high_7d'])} | Range: {fmt(best['high_7d']-best['low_7d'])}\nLow 2d: {fmt(best['low_2d'])} | Pump 2d: +{best['pump_2d']:.1f}% (Block >{PUMP_BLOCK_PCT:.0f}%) | Pump Mid: {fmt(best['pump_midpoint'])} | State: {best['pump_state']}\nGlobal Vol: ${best['vol']:,.0f}\n{best['reason']}\n\n🎯 <b>ENTER AT: {fmt(best['price'])}</b>\nEntry Zone: {fmt(best['entry_low'])} - {fmt(best['entry_high'])}\nValid Until: {best['valid_until'].strftime('%H:%M')} EAT (+1h) - If price is outside zone when you see this, SKIP, do not chase\nSL: {fmt(best['sl'])}\nTP1: {fmt(best['tp1'])} - TAKE PROFIT{' - CLOSE ALL if TP1 ONLY' if best['tp1_only'] else ', then SELL HALF + SL to Entry, then wait for Leg 2'}\nTP2: {fmt(best['tp2'])} - {'SKIPPED - TP1 ONLY MODE' if best['tp1_only'] else 'Via Leg 2 re-entry after bounce/dip'}\nRunner: {fmt(best['runner'])}")
            send_telegram(msg)
            print(f"{sym} {best['side']} - BEST SIGNAL SENT - TP1_ONLY={best['tp1_only']}")
    save_json(ACTIVE_FILE, active)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    run_once()
