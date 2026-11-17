# V900 FINAL - Pumped vs Shed Logic - 3 Levels Locked
# Small +150% / Mid +100% / Big +60%
# No pullback, No funding, No 3x, No 0.5% - Signal the moment it hits
# Designed for 1 HOUR cron - 7d High stays, so late check still catches pump
# FIX: Use sparkline from markets - 4 calls total, no 429, BLESS not missed
import json, os, requests, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
UTC = timezone.utc
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

MIN_VOLUME = 5000000  # $5M global volume

def load_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except: return default

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

def get_group(cap_at_low):
    # Group is decided by Cap at LOW, locked for whole pump
    if cap_at_low < 200_000_000:
        return "Small", 150.0, 45.0  # Pump +150% = Shed -45%
    elif cap_at_low <= 2_000_000_000:
        return "Mid", 100.0, 30.0    # Pump +100% = Shed -30%
    else:
        return "Big", 60.0, 20.0     # Pump +60% = Shed -20%

def get_global_data():
    # CoinGecko = Global aggregated price + cap + volume
    # FIX: sparkline=true gives 7d low/high in SAME 4 calls
    # No more 626 x market_chart calls = no more 429
    result = {}
    for page in [1, 2, 3, 4]:
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}&price_change_percentage=7d&sparkline=true", timeout=20).json()
            for c in r:
                sym = c.get("symbol","").upper()
                if sym not in result:
                    spark = c.get("sparkline_in_7d", {}).get("price", []) or []
                    result[sym] = {
                        "cap_now": c.get("market_cap",0) or 0,
                        "global_price": c.get("current_price",0) or 0,
                        "global_vol": c.get("total_volume",0) or 0,
                        "gecko_id": c.get("id"),
                        "change_7d": c.get("price_change_percentage_7d_in_currency", 0) or 0,
                        "spark_7d": spark,
                    }
        except Exception as e:
            print(f"GLOBAL API ERROR page {page}: {e}")
            break
    return result

def get_mexc_perps():
    # MEXC = Execution price
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
        movers[sym] = {"price": price, "vol": vol, "symbol": sym_raw}
    return movers

def run_once():
    active = load_json(ACTIVE_FILE, {})
    now = datetime.now(TZ)
    now_utc = datetime.now(UTC)

    fresh = {}
    for k,v in active.items():
        try:
            t = datetime.fromisoformat(str(v.get("time","")).replace("Z","+00:00"))
            if t.tzinfo is None: t = t.replace(tzinfo=TZ)
            if (now - t).total_seconds() < 24*3600: fresh[k]=v
        except: fresh[k]=v
    active = fresh
    print(f"Active: {len(active)} - {list(active.keys())}")

    global_data = get_global_data()
    mexc = get_mexc_perps()
    print(f"MEXC perps: {len(mexc)} | Global: {len(global_data)}")

    for sym, m in mexc.items():
        if sym in active:
            print(f"{sym} SKIP - Already active")
            continue

        price_exec = m["price"]
        vol_local = m["vol"]

        g = global_data.get(sym, {})
        cap_now = g.get("cap_now", 0)
        global_price = g.get("global_price", price_exec)
        global_vol = g.get("global_vol", vol_local)

        if cap_now == 0 or global_price == 0:
            print(f"{sym} SKIP - No global data, cannot calc Pumped")
            continue

        # FIX: Use sparkline from markets - 0 extra calls, no 429, no missed BLESS
        # BLESS net +37.2% could still be Pumped +150% -> Shed -45% = Net +37.5%
        # So we NEVER pre-filter by change_7d - we always check sparkline low/high
        spark = g.get("spark_7d", [])
        if not spark:
            print(f"{sym} SKIP - No 7d sparkline")
            continue
        low_7d = min(spark)
        high_7d = max(spark)

        # === CAP AT LOW - Group locked at start of pump ===
        cap_at_low = cap_now * (low_7d / global_price) if global_price > 0 else cap_now
        group, pump_thresh, expected_shed = get_group(cap_at_low)

        # === PUMPED vs SHED MATHS - Using Global Prices ===
        pumped = (high_7d - low_7d) / low_7d * 100 if low_7d > 0 else 0
        shed = (high_7d - global_price) / high_7d * 100 if high_7d > 0 else 0
        net = (global_price - low_7d) / low_7d * 100 if low_7d > 0 else 0

        print(f"{sym} | {group} CapLow ${cap_at_low/1e6:.1f}M (CapNow ${cap_now/1e6:.1f}M) | Pumped +{pumped:.1f}% / Need +{pump_thresh}% | Shed -{shed:.1f}% | Net +{net:.1f}%")

        # $5M filter - Global volume
        if max(global_vol, vol_local) < MIN_VOLUME:
            print(f"{sym} SKIP - Vol ${max(global_vol, vol_local):,.0f} < $5M")
            continue

        side = None
        reason = ""

        # === SIGNAL LOGIC - No pullback wait ===
        # FIX FOR 1 HOUR CRON: Allow late entry
        # Skip only if shed >= expected * 1.5 (really dumped already)
        # Example Small: expected -45%, we still signal even if shed -60%, we skip only if shed -67.5%+
        if pumped >= pump_thresh:
            if shed >= expected_shed * 1.5:
                print(f"{sym} SKIP - Already shed -{shed:.1f}% (expected -{expected_shed}%, limit -{expected_shed*1.5:.1f}%) - move done")
                continue
            else:
                side = "SHORT"
                reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed only -{shed:.1f}% so far, expected -{expected_shed}% - SHORT now"

        if side is None:
            print(f"{sym} SKIP - Pumped +{pumped:.1f}% < +{pump_thresh}%")
            continue

        # SL / TP based on Expected Shed from scan
        if side == "SHORT":
            sl = round(price_exec * 1.10, 8)
            tp1 = round(price_exec * (1 - (expected_shed/100)*0.5), 8)
            tp2 = round(price_exec * (1 - expected_shed/100), 8)
            runner = round(price_exec * (1 - (expected_shed/100)*1.5), 8)
            emoji = "\U0001F534"
        else:
            sl = round(price_exec * 0.90, 8)
            tp1 = round(price_exec * 1.15, 8)
            tp2 = round(price_exec * 1.25, 8)
            runner = round(price_exec * 1.40, 8)
            emoji = "\U0001F7E2"

        signal = {
            "sym": sym, "side": side, "price": price_exec,
            "pumped": pumped, "shed": shed, "net": net,
            "cap_at_low": cap_at_low, "group": group,
            "low_7d": low_7d, "high_7d": high_7d,
            "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner,
            "reason": reason, "time": now.isoformat()
        }
        active[sym] = signal

        msg = f"{emoji} <b>V900 PERP {side} {sym}</b> - {group}\nCap at Low: ${cap_at_low/1e6:.1f}M (Now ${cap_now/1e6:.1f}M)\nPumped: +{pumped:.1f}% (Need +{pump_thresh}%)\nShed so far: -{shed:.1f}% (Expected -{expected_shed}%)\nLow 7d: {fmt(low_7d)} | High 7d: {fmt(high_7d)}\nGlobal Vol: ${max(global_vol, vol_local):,.0f}\n{reason}\nPrice: {fmt(price_exec)}\nSL: {fmt(sl)}\nTP1: {fmt(tp1)}\nTP2: {fmt(tp2)}\nRunner: {fmt(runner)}"
        send_telegram(msg)
        print(f"{sym} {side} - {reason}")

    save_json(ACTIVE_FILE, active)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    run_once()
