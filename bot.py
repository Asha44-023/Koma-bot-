# V800 - SAFER - Volume + Confirmation - MEXC - BUY + SELL
import json, os, re, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"
COOLDOWN_FILE = "cooldown.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

MIN_VOLUME = 500000

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
    r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=20).json()
    if isinstance(r, dict):
        print(f"MEXC ERROR: {r}")
        return {}
    movers = {}
    for t in r:
        sym_raw = t.get('symbol','')
        if "_USDT" in sym_raw:
            sym = sym_raw.replace("_USDT","")
        elif sym_raw.endswith("USDT"):
            sym = sym_raw.replace("USDT","")
        else:
            continue
        if sym in ["BTC","ETH","BNB","SOL","XRP","DOGE"]: continue
        try:
            pct = parse_pct(t.get('priceChangePercent'))
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])
            vol = float(t.get('quoteVolume', 0) or t.get('volume', 0) or 0)
        except: continue
        if pct is None: continue
        if abs(pct) >= 20:
            movers[sym] = {"pct": pct, "price": price, "symbol": sym_raw, "high": high, "low": low, "vol": vol}
    print(f"Found {len(movers)} movers >=20%")
    for k,v in sorted(movers.items(), key=lambda x: -abs(x[1]['pct']))[:20]:
        print(f"MOVER {k}: {v['pct']:.1f}% price {v['price']} vol ${v['vol']:,.0f}")
    return movers

def run_once(reset_cooldowns=False):
    active = load_json(ACTIVE_FILE, {})
    cooldowns = load_json(COOLDOWN_FILE, {}) if not reset_cooldowns else {}
    history = load_json(HISTORY_FILE, {})
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    yesterday_str = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
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
        print("MEXC returned 0 movers - NOT overwriting history")
    for sym, data in movers.items():
        if sym in active: continue
        if sym in cooldowns: continue
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
            print(f"{sym} SKIP - Low volume ${vol:,.0f} < $500k")
            continue
        from_high = (price - high) / high * 100 if high > 0 else 0
        from_low = (price - low) / low * 100 if low > 0 else 0
        if is_new and today_pct > 30:
            if from_high <= -3:
                side = "SELL"; reason = f"NEW pump + confirmation, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SELL - Still at High, {from_high:.1f}% off High, wait for pullback")
                continue
        elif not is_new and today_pct > 30 and y_pct > 30:
            if from_high <= -3:
                side = "SELL"; day_label = "Runner"; reason = f"RUNNER {y_pct:.1f}% yday + {today_pct:.1f}% today, {from_high:.1f}% off High"
            else:
                print(f"{sym} SKIP SELL Runner - Still at High")
                continue
        elif not is_new and today_pct < -20 and y_pct > 30:
            if from_high <= -3:
                side = "SELL"; reason = f"PUMP THEN DUMP {y_pct:.1f}% yday"
            else:
                print(f"{sym} SKIP SELL - No pullback yet")
                continue
        elif is_new and today_pct > 20 and price < mid:
            if from_high <= -3:
                side = "SELL"; reason = "NEW pump fading below mid + pullback"
            else:
                print(f"{sym} SKIP SELL - No pullback yet")
                continue
        if side is None and is_new and today_pct < -25:
            if from_low >= 3:
                side = "BUY"; reason = f"NEW dumped {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP BUY - Still at Low, {from_low:.1f}% off Low, wait for bounce")
                continue
        elif side is None and not is_new and today_pct < -20 and y_pct < -20:
            if from_low >= 3:
                side = "BUY"; reason = f"DUMPED 2 DAYS {y_pct:.1f}% yday + {today_pct:.1f}% today, bounced +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP BUY - Still at Low, wait for bounce")
                continue
        elif side is None and not is_new and today_pct > 20 and y_pct < -30:
            if from_low >= 3:
                side = "BUY"; day_label = "Bounce"; reason = f"BOUNCE after {y_pct:.1f}% yday dump, +{from_low:.1f}% off Low"
            else:
                print(f"{sym} SKIP BUY Bounce - Still at Low")
                continue
        if side is None:
            print(f"{sym} SKIP - {today_pct:.1f}% today, {y_pct} yday")
            continue
        # RED = U0001F534, GREEN = U0001F7E2
        if side == "SELL":
            sl = round(price * 1.10, 8); tp1 = round(price * 0.85, 8); tp2 = round(price * 0.75, 8); runner = round(price * 0.60, 8); emoji = "\U0001F534"
        else:
            sl = round(price * 0.90, 8); tp1 = round(price * 1.15, 8); tp2 = round(price * 1.25, 8); runner = round(price * 1.40, 8); emoji = "\U0001F7E2"
        signal = {"sym": sym, "side": side, "price": price, "pct": today_pct, "y_pct": y_pct, "mid": mid, "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner, "day": day_label, "reason": reason, "time": datetime.now(TZ).isoformat()}
        active[sym] = signal
        cooldowns[sym] = datetime.now(TZ).isoformat()
        y_txt = "NEW" if is_new else f"{y_pct:.1f}% yday"
        msg = f"{emoji} <b>V800 {side} {sym}</b> - {day_label}\nToday: {today_pct:.1f}% | Yesterday: {y_txt}\nVol: ${vol:,.0f}\n{reason}\nPrice: {fmt(price)}\nMid: {fmt(mid)}\nSL: {fmt(sl)}\nTP1: {fmt(tp1)}\nTP2: {fmt(tp2)}\nRunner: {fmt(runner)}"
        send_telegram(msg)
        print(f"{sym} {side} - {reason}")
    save_json(ACTIVE_FILE, active)
    save_json(COOLDOWN_FILE, cooldowns)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    import sys
    reset = "--reset" in sys.argv or os.getenv("RESET") == "true"
    run_once(reset_cooldowns=reset)
