# V800 - Scan V800 - MEXC - BUY + SELL - DEBUG VERSION
import json, os, re, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"
COOLDOWN_FILE = "cooldown.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"LOAD FAIL {path}: {e}")
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)

def parse_pct(v):
    if v is None: return None
    if isinstance(v, (int, float)):
        if abs(v) < 2 and v != 0:
            return v * 100
        return float(v)
    m = re.search(r'-?\d+\.?\d*', str(v))
    if not m: return None
    return float(m.group(0))

def get_movers():
    r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=20).json()
    print(f"MEXC raw type: {type(r)} len: {len(r) if isinstance(r, list) else r}")
    if isinstance(r, dict):
        print(f"MEXC ERROR: {r}")
        return {}
    # DEBUG - print first 5 raw tickers exactly as MEXC sends them
    print(f"SAMPLE RAW 0: {r[0] if len(r)>0 else 'empty'}")
    print(f"SAMPLE RAW 1: {r[1] if len(r)>1 else 'empty'}")
    print(f"SAMPLE RAW 2: {r[2] if len(r)>2 else 'empty'}")
    # Find max mover to see scale
    max_item = None
    max_pct = 0
    for t in r:
        try:
            p = parse_pct(t.get('priceChangePercent'))
            if p is not None and abs(p) > abs(max_pct):
                max_pct = p
                max_item = t
        except: pass
    print(f"MAX MOVER RAW: {max_item} parsed pct: {max_pct}")

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
        except Exception as e:
            continue
        if pct is None: continue
        if abs(pct) >= 20:
            movers[sym] = {"pct": pct, "price": price, "symbol": sym_raw, "high": high, "low": low}
    print(f"Found {len(movers)} movers >=20%")
    for k,v in movers.items():
        print(f"MOVER {k}: {v['pct']:.1f}% price {v['price']}")
    return movers

def run_once(reset_cooldowns=False):
    active = load_json(ACTIVE_FILE, {})
    cooldowns = load_json(COOLDOWN_FILE, {}) if not reset_cooldowns else {}
    history = load_json(HISTORY_FILE, {})
    print(f"HISTORY TYPE: {type(history)} KEYS: {list(history.keys())[:10] if isinstance(history, dict) else str(history)[:500]}")
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    yesterday_str = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    raw_yday = history.get(yesterday_str, {}) if isinstance(history, dict) else {}
    print(f"RAW YDAY for {yesterday_str}: {str(raw_yday)[:500]}")
    yesterday_movers = {}
    if isinstance(raw_yday, dict):
        for k,v in raw_yday.items():
            clean_k = k.replace("_USDT","").replace("USDT","")
            yesterday_movers[clean_k] = parse_pct(v)
    print(f"Today {today_str} Yesterday {yesterday_str} Yday movers: {len(yesterday_movers)}")
    print(f"Yday sample: {list(yesterday_movers.items())[:5]}")

    movers = get_movers()
    history[today_str] = {k: v["pct"] for k,v in movers.items()}
    save_json(HISTORY_FILE, history)

    for sym, data in movers.items():
        if sym in active: continue
        if sym in cooldowns: continue
        today_pct = data["pct"]
        price = data["price"]
        mid = (data["high"] + data["low"]) / 2
        y_pct = yesterday_movers.get(sym, None)
        is_new = (y_pct is None)
        side = None
        day_label = "Day1" if is_new else "Day2+"
        reason = ""
        if is_new and today_pct > 30:
            side = "SELL"; reason = "NEW pump"
        elif not is_new and today_pct > 30 and y_pct > 30:
            side = "SELL"; day_label = "Runner"; reason = f"RUNNER {y_pct:.1f}% yday + {today_pct:.1f}% today"
        elif not is_new and today_pct < -20 and y_pct > 30:
            side = "SELL"; reason = f"PUMP THEN DUMP {y_pct:.1f}% yday"
        elif is_new and today_pct > 20 and price < mid:
            side = "SELL"; reason = "NEW pump fading below mid"
        if side is None and is_new and today_pct < -25:
            side = "BUY"; reason = f"NEW dumped {today_pct:.1f}% today, bounce"
        elif side is None and not is_new and today_pct < -20 and y_pct < -20:
            side = "BUY"; reason = f"DUMPED 2 DAYS {y_pct:.1f}% yday + {today_pct:.1f}% today, exhausted"
        elif side is None and not is_new and today_pct > 20 and y_pct < -30:
            side = "BUY"; day_label = "Bounce"; reason = f"BOUNCE after {y_pct:.1f}% yday dump"
        if side is None:
            print(f"{sym} SKIP - {today_pct:.1f}% today, {y_pct} yday - no BUY/SELL setup")
            continue
        if side == "SELL":
            sl = round(price * 1.10, 8); tp1 = round(price * 0.85, 8); tp2 = round(price * 0.75, 8); runner = round(price * 0.60, 8); emoji = "🔴"
        else:
            sl = round(price * 0.90, 8); tp1 = round(price * 1.15, 8); tp2 = round(price * 1.25, 8); runner = round(price * 1.40, 8); emoji = "🟢"
        signal = {"sym": sym, "side": side, "price": price, "pct": today_pct, "y_pct": y_pct, "mid": mid, "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner, "day": day_label, "reason": reason, "time": datetime.now(TZ).isoformat()}
        active[sym] = signal
        cooldowns[sym] = datetime.now(TZ).isoformat()
        y_txt = "NEW" if is_new else f"{y_pct:.1f}% yday"
        msg = f"{emoji} <b>V800 {side} {sym}</b> - {day_label}\n📊 Today: {today_pct:.1f}% | Yesterday: {y_txt}\n📝 {reason}\n💰 Price: {price}\n🎯 Mid: {mid}\n🛑 SL: {sl}\n✅ TP1: {tp1}\n✅ TP2: {tp2}\n🏃 Runner: {runner}"
        send_telegram(msg)
        print(f"{sym} {side} - {reason}")
    save_json(ACTIVE_FILE, active)
    save_json(COOLDOWN_FILE, cooldowns)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    import sys
    reset = "--reset" in sys.argv or os.getenv("RESET") == "true"
    run_once(reset_cooldowns=reset)
