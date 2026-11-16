# V800 - PERP STRICT $5M - NO COOLDOWN FILE - Never gets stuck
import json, os, re, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"
VOL_FILE = "vol_history.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

# === STRICT PERP SETTINGS - BEST FOR YOU ===
MIN_VOLUME = 5000000  # $5M - blocks CASHCAT $662k, allows RARE $11M
MIN_MOVE = 35.0      # Must be +/-35% to qualify
CONFIRMATION = 5.0   # Must be 5% off High / Low

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    print(f"TELEGRAM DEBUG - Token set: {bool(TELEGRAM_TOKEN)} Chat ID set: {bool(TELEGRAM_CHAT_ID)}")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM ERROR: Token or Chat ID missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"TELEGRAM RESPONSE: {r.status_code} {r.text[:400]}")
    except Exception as e:
        print(f"TELEGRAM EXCEPTION: {e}")

def parse_pct(v):
    if v is None: return None
    s = str(v)
    has_percent_sign = '%' in s
    m = re.search(r'-?\d+\.?\d*', s)
    if not m: return None
    val = float(m.group(0))
    if has_percent_sign:
        return val
    return val * 100

def fmt(p):
    s = f"{p:.8f}".rstrip('0').rstrip('.')
    return s

def get_movers():
    # === PERPS ONLY - MEXC Contract Ticker ===
    r = requests.get("https://contract.mexc.com/api/v1/contract/ticker", timeout=20).json()
    data_list = r.get("data", []) if isinstance(r, dict) else r
    if not data_list:
        print(f"MEXC PERP ERROR: {r}")
        return {}
    movers = {}
    for t in data_list:
        sym_raw = t.get('symbol','')
        if "_USDT" not in sym_raw:
            continue
        sym = sym_raw.replace("_USDT","")
        if sym in ["BTC","ETH","BNB","SOL","XRP","DOGE"]: continue
        try:
            # PERP fields: lastPrice, high24Price, low24Price, amount24, riseFallRates
            pct_raw = t.get('riseFallRates')
            pct = float(pct_raw) * 100 if pct_raw is not None else parse_pct(t.get('riseFallRate'))
            price = float(t['lastPrice'])
            high = float(t.get('high24Price', price))
            low = float(t.get('low24Price', price))
            vol = float(t.get('amount24', 0) or t.get('volume24', 0) or 0)
        except: continue
        if pct is None: continue
        if abs(pct) >= MIN_MOVE:  # 35% now, not 20%
            movers[sym] = {"pct": pct, "price": price, "symbol": sym_raw, "high": high, "low": low, "vol": vol}
    print(f"Found {len(movers)} PERP movers >={MIN_MOVE}%")
    for k,v in sorted(movers.items(), key=lambda x: -abs(x[1]['pct']))[:20]:
        print(f"MOVER {k}: {v['pct']:.1f}% price {v['price']} PERP Vol ${v['vol']:,.0f}")
    return movers

def run_once():
    active = load_json(ACTIVE_FILE, {})
    history = load_json(HISTORY_FILE, {})
    vol_hist = load_json(VOL_FILE, {})
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # Active expires after 24h - NO cooldown file
    fresh_active = {}
    for k, v in active.items():
        try:
            t = datetime.fromisoformat(str(v.get("time","")).replace("Z","+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=TZ)
            if (now - t).total_seconds() < 24*3600:
                fresh_active[k] = v
            else:
                print(f"Active expired for {k}, can signal again")
        except:
            fresh_active[k] = v
    active = fresh_active
    print(f"Active after cleanup: {len(active)} - {list(active.keys())[:10]}")

    raw_yday = history.get(yesterday_str, {}) if isinstance(history, dict) else {}
    yesterday_movers = {}
    if isinstance(raw_yday, dict):
        for k,v in raw_yday.items():
            clean_k = k.replace("_USDT","").replace("USDT","")
            yesterday_movers[clean_k] = parse_pct(v)
    print(f"Today {today_str} Yday {yesterday_str} Yday movers: {len(yesterday_movers)}")
    movers = get_movers()
    if movers:
        history[today_str] = {k: v["pct"] for k,v in movers.items()}
        save_json(HISTORY_FILE, history)
    else:
        print("MEXC PERP returned 0 movers - NOT overwriting history")

    for sym, data in movers.items():
        if sym in active:
            print(f"{sym} SKIP - Already active in last 24h")
            continue
        today_pct = data["pct"]
        price = data["price"]
        high = data["high"]
        low = data["low"]
        vol = data["vol"]
        mid = (high + low) / 2
        y_pct = yesterday_movers.get(sym, None)
        is_new = (y_pct is None)
        side = None
        day_label = "Day1" if is_new else "Day2+"
        reason = ""

        # === $5M FILTER ===
        if vol < MIN_VOLUME:
            print(f"{sym} SKIP - Low PERP volume ${vol:,.0f} < $5M")
            continue

        # === VOLUME + PRICE LOGIC ===
        # Track volume growth: if volume growth is slowing while price is still at extreme = trend dying
        prev_vol = vol_hist.get(sym, vol)
        vol_growth = vol - prev_vol
        vol_hist[sym] = vol
        # We still allow signal, but we log it. Main filter is 5% confirmation which proves trend is dying.
        # If volume is still exploding (vol_growth huge) + price at high, it's still strong - wait.
        # Since we already require 5% off High/Low, that IS the proof volume is failing to hold price.

        from_high = (price - high) / high * 100 if high > 0 else 0
        from_low = (price - low) / low * 100 if low > 0 else 0

        # === SHORTS - 5% confirmation ===
        if is_new and today_pct > 35:
            if from_high <= -CONFIRMATION:
                side = "SHORT"; reason = f"NEW pump + confirmation, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SHORT - Still at High, {from_high:.1f}% off High, wait for 5% pullback")
                continue
        elif not is_new and today_pct > 35 and y_pct is not None and y_pct > 35:
            if from_high <= -CONFIRMATION:
                side = "SHORT"; day_label = "Runner"; reason = f"RUNNER {y_pct:.1f}% yday + {today_pct:.1f}% today, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SHORT Runner - Still at High")
                continue
        elif not is_new and today_pct < -20 and y_pct is not None and y_pct > 35:
            if from_high <= -CONFIRMATION:
                side = "SHORT"; reason = f"PUMP THEN DUMP {y_pct:.1f}% yday"
            else:
                print(f"{sym} SKIP SHORT - No pullback yet")
                continue
        elif is_new and today_pct > 35 and price < mid:
            if from_high <= -CONFIRMATION:
                side = "SHORT"; reason = "NEW pump fading below mid + pullback"
            else:
                print(f"{sym} SKIP SHORT - No pullback yet")
                continue

        # === LONGS - 5% confirmation ===
        if side is None and is_new and today_pct < -35:
            if from_low >= CONFIRMATION:
                side = "LONG"; reason = f"NEW dumped {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG - Still at Low, {from_low:.1f}% off Low, wait for 5% bounce")
                continue
        elif side is None and not is_new and today_pct < -20 and y_pct is not None and y_pct < -20:
            if from_low >= CONFIRMATION:
                side = "LONG"; reason = f"DUMPED 2 DAYS {y_pct:.1f}% yday + {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG - Still at Low, wait for bounce")
                continue
        elif side is None and not is_new and today_pct > 20 and y_pct is not None and y_pct < -35:
            if from_low >= CONFIRMATION:
                side = "LONG"; day_label = "Bounce"; reason = f"BOUNCE after {y_pct:.1f}% yday dump, +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG Bounce - Still at Low")
                continue

        if side is None:
            print(f"{sym} SKIP - {today_pct:.1f}% today, {y_pct} yday")
            continue

        # RED = U0001F534, GREEN = U0001F7E2
        if side == "SHORT":
            sl = round(price * 1.10, 8); tp1 = round(price * 0.85, 8); tp2 = round(price * 0.75, 8); runner = round(price * 0.60, 8); emoji = "\U0001F534"
        else:
            sl = round(price * 0.90, 8); tp1 = round(price * 1.15, 8); tp2 = round(price * 1.25, 8); runner = round(price * 1.40, 8); emoji = "\U0001F7E2"
        signal = {"sym": sym, "side": side, "price": price, "pct": today_pct, "y_pct": y_pct, "mid": mid, "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner, "day": day_label, "reason": reason, "time": now.isoformat()}
        active[sym] = signal
        y_txt = "NEW" if is_new else f"{y_pct:.1f}% yday"
        msg = f"{emoji} <b>V800 PERP {side} {sym}</b> - {day_label}\nToday: {today_pct:.1f}% | Yesterday: {y_txt}\nPERP Vol: ${vol:,.0f}\n{reason}\nPrice: {fmt(price)}\nMid: {fmt(mid)}\nSL: {fmt(sl)}\nTP1: {fmt(tp1)}\nTP2: {fmt(tp2)}\nRunner: {fmt(runner)}"
        send_telegram(msg)
        print(f"{sym} {side} - {reason}")

    save_json(VOL_FILE, vol_hist)
    save_json(ACTIVE_FILE, active)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    run_once()
