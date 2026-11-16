# V800 - Scan V800 - MEXC - BUY + SELL - Yesterday Check + Real Mid
import json, os, requests
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
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)

def get_movers():
    r = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=20).json()
    print(f"MEXC raw type: {type(r)} len: {len(r) if isinstance(r, list) else r}")
    if isinstance(r, dict):
        print(f"MEXC ERROR: {r}")
        return {}
    movers = {}
    for t in r:
        sym = t['symbol']
        if not sym.endswith("USDT"): continue
        if sym in ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT"]: continue
        try:
            pct = float(t['priceChangePercent'])
            price = float(t['lastPrice'])
            high = float(t['highPrice'])
            low = float(t['lowPrice'])
        except: continue
        if abs(pct) >= 20:
            movers[sym.replace("USDT","")] = {"pct": pct, "price": price, "symbol": sym, "high": high, "low": low}
    print(f"Found {len(movers)} movers >=20%")
    for k,v in movers.items():
        print(f"MOVER {k}: {v['pct']:.1f}% price {v['price']}")
    return movers

def run_once(reset_cooldowns=False):
    active = load_json(ACTIVE_FILE, {})
    cooldowns = load_json(COOLDOWN_FILE, {}) if not reset_cooldowns else {}
    history = load_json(HISTORY_FILE, {})
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    yesterday_str = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_movers = history.get(yesterday_str, {})
    print(f"Today {today_str} Yesterday {yesterday_str} Yday movers: {len(yesterday_movers)}")
    print(f"Yday sample: {list(yesterday_movers.items())[:5]}")
    print(f"Active loaded: {len(active)} Cooldowns loaded: {len(cooldowns)}")

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

        # ===== SELL LOGIC - Fake Pump -> Dump =====
        if is_new and today_pct > 30:
            side = "SELL"; reason = "NEW pump"
        elif not is_new and today_pct > 30 and y_pct > 30:
            side = "SELL"; day_label = "Runner"; reason = f"RUNNER {y_pct:.1f}% yday + {today_pct:.1f}% today"
        elif not is_new and today_pct < -20 and y_pct > 30:
            side = "SELL"; reason = f"PUMP THEN DUMP {y_pct:.1f}% yday"
        elif is_new and today_pct > 20 and price < mid:
            side = "SELL"; reason = "NEW pump fading below mid"

        # ===== BUY LOGIC - Dump -> Bounce =====
        if side is None and is_new and today_pct < -25:
            side = "BUY"; reason = f"NEW dumped {today_pct:.1f}% today, bounce"
        elif side is None and not is_new and today_pct < -20 and y_pct < -20:
            side = "BUY"; reason = f"DUMPED 2 DAYS {y_pct:.1f}% yday + {today_pct:.1f}% today, exhausted"
        elif side is None and not is_new and today_pct > 20 and y_pct < -30:
            side = "BUY"; day_label = "Bounce"; reason = f"BOUNCE after {y_pct:.1f}% yday dump"
        elif side is None and not is_new and today_pct < -20 and y_pct < -20 and price > mid:
            side = "BUY"; reason = "Dump exhausted, above mid"

        if side is None:
            print(f"{sym} SKIP - {today_pct:.1f}% today, {y_pct} yday - no BUY/SELL setup")
            continue

        if side == "SELL":
            sl = round(price * 1.10, 8)
            tp1 = round(price * 0.85, 8)
            tp2 = round(price * 0.75, 8)
            runner = round(price * 0.60, 8)
            emoji = "🔴"
        else:
            sl = round(price * 0.90, 8)
            tp1 = round(price * 1.15, 8)
            tp2 = round(price * 1.25, 8)
            runner = round(price * 1.40, 8)
            emoji = "🟢"

        signal = {"sym": sym, "side": side, "price": price, "pct": today_pct, "y_pct": y_pct,
                  "mid": mid, "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner,
                  "day": day_label, "reason": reason, "time": datetime.now(TZ).isoformat()}
        active[sym] = signal
        cooldowns[sym] = datetime.now(TZ).isoformat()

        y_txt = "NEW" if is_new else f"{y_pct:.1f}% yday"
        msg = f"{emoji} <b>V800 {side} {sym}</b> - {day_label}\n"
        msg += f"📊 Today: {today_pct:.1f}% | Yesterday: {y_txt}\n"
        msg += f"📝 {reason}\n💰 Price: {price}\n🎯 Mid: {mid}\n"
        msg += f"🛑 SL: {sl}\n✅ TP1: {tp1}\n✅ TP2: {tp2}\n🏃 Runner: {runner}"
        send_telegram(msg)
        print(f"{sym} {side} - {reason}")

    save_json(ACTIVE_FILE, active)
    save_json(COOLDOWN_FILE, cooldowns)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    import sys
    reset = "--reset" in sys.argv or os.getenv("RESET") == "true"
    run_once(reset_cooldowns=reset)
