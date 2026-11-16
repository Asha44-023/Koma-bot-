# V800 - PERPS ONLY - MEXC Futures - LONG + SHORT
import json, os, re, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

MIN_VOLUME = 500000  # $500k PERP volume

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
    # MEXC PERPS ONLY - Futures ticker
    try:
        r = requests.get("https://contract.mexc.com/api/v1/contract/ticker", timeout=20).json()
    except Exception as e:
        print(f"MEXC PERP ERROR: {e}")
        return {}
    data = r.get("data", []) if isinstance(r, dict) else []
    if not data:
        print(f"MEXC PERP ERROR: {r}")
        return {}
    movers = {}
    for t in data:
        sym_raw = t.get('symbol','')  # e.g. CHOMP_USDT
        if "_USDT" in sym_raw:
            sym = sym_raw.replace("_USDT","")
        else:
            continue
        if sym in ["BTC","ETH","BNB","SOL","XRP","DOGE"]: continue
        try:
            # Futures uses riseFallRate (0.471 = 47.1%) or priceChangePercent
            raw_pct = t.get('riseFallRate', t.get('priceChangePercent'))
            pct = float(raw_pct) * 100 if raw_pct is not None and abs(float(raw_pct)) < 10 else parse_pct(raw_pct)
            price = float(t['lastPrice'])
            high = float(t.get('high24Price', t.get('highPrice', price)))
            low = float(t.get('low24Price', t.get('lowPrice', price)))
            # amount24 = volume in USDT for perps
            vol = float(t.get('amount24', 0) or t.get('quoteVolume', 0) or t.get('volume24', 0) or 0)
        except Exception as e:
            continue
        if pct is None: continue
        if abs(pct) >= 20:
            movers[sym] = {"pct": pct, "price": price, "symbol": sym_raw, "high": high, "low": low, "vol": vol}
    print(f"Found {len(movers)} PERP movers >=20%")
    for k,v in sorted(movers.items(), key=lambda x: -abs(x[1]['pct']))[:20]:
        print(f"PERP MOVER {k}: {v['pct']:.1f}% price {v['price']} vol ${v['vol']:,.0f}")
    return movers

def run_once():
    active = load_json(ACTIVE_FILE, {})
    history = load_json(HISTORY_FILE, {})
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
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
        if vol < MIN_VOLUME:
            print(f"{sym} SKIP - Low PERP volume ${vol:,.0f} < $500k")
            continue
        from_high = (price - high) / high * 100 if high > 0 else 0
        from_low = (price - low) / low * 100 if low > 0 else 0
        # SHORT signals - pump fading
        if is_new and today_pct > 30:
            if from_high <= -3:
                side = "SHORT"; reason = f"NEW pump + confirmation, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SHORT - Still at High, {from_high:.1f}% off High, wait for pullback")
                continue
        elif not is_new and today_pct > 30 and y_pct > 30:
            if from_high <= -3:
                side = "SHORT"; day_label = "Runner"; reason = f"RUNNER {y_pct:.1f}% yday + {today_pct:.1f}% today, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SHORT Runner - Still at High")
                continue
        elif not is_new and today_pct < -20 and y_pct > 30:
            if from_high <= -3:
                side = "SHORT"; reason = f"PUMP THEN DUMP {y_pct:.1f}% yday"
            else:
                print(f"{sym} SKIP SHORT - No pullback yet")
                continue
        elif is_new and today_pct > 20 and price < mid:
            if from_high <= -3:
                side = "SHORT"; reason = "NEW pump fading below mid + pullback"
            else:
                print(f"{sym} SKIP SHORT - No pullback yet")
                continue
        # LONG signals - dump bouncing
        if side is None and is_new and today_pct < -25:
            if from_low >= 3:
                side = "LONG"; reason = f"NEW dumped {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG - Still at Low, {from_low:.1f}% off Low, wait for bounce")
                continue
        elif side is None and not is_new and today_pct < -20 and y_pct < -20:
            if from_low >= 3:
                side = "LONG"; reason = f"DUMPED 2 DAYS {y_pct:.1f}% yday + {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG - Still at Low, wait for bounce")
                continue
        elif side is None and not is_new and today_pct > 20 and y_pct < -30:
            if from_low >= 3:
                side = "LONG"; day_label = "Bounce"; reason = f"BOUNCE after {y_pct:.1f}% yday dump, +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP LONG Bounce - Still at Low")
                continue
        if side is None:
            print(f"{sym} SKIP - {today_pct:.1f}% today, {y_pct} yday")
            continue
        # RED = SHORT, GREEN = LONG
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
    save_json(ACTIVE_FILE, active)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    run_once()
