# V900.3 FINAL - Pumped vs Shed Logic - BOTH WAYS - BEST ONLY
# Small +150% / Mid +100% / Big +60%
# SHORT: Pumped hit, shed NOT done yet -> short the remaining shed
# LONG: Pumped hit, shed DONE + overshoot -> long the bounce
# BEST ONLY: Group first (Big > Mid > Small), then Net, then Vol - No score
# V900.2 filters kept: Days-Since-Spike >=2, Entry Zone, 7-day expiry
import json, os, requests, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Africa/Nairobi")
UTC = timezone.utc
ACTIVE_FILE = "active.json"
HISTORY_FILE = "movers_history.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID") or os.getenv("CHAT_ID")

MIN_VOLUME = 5000000
MAX_ACTIVE_DAYS = 7
WARNING_DAY = 5
MAX_SIGNALS_PER_SCAN = 1
GROUP_RANK = {"Big": 3, "Mid": 2, "Small": 1}

EXPECTED_DAYS = {"Small": "3-5 days", "Mid": "2-4 days", "Big": "1-3 days"}

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
    if cap_at_low < 200_000_000:
        return "Small", 150.0, 45.0
    elif cap_at_low <= 2_000_000_000:
        return "Mid", 100.0, 30.0
    else:
        return "Big", 60.0, 20.0

def days_since_spike(spark):
    if not spark or len(spark) < 48:
        return 99, 0, []
    n = len(spark)
    daily_closes = []
    chunk = n // 7
    for i in range(7):
        start = i * chunk
        end = (i + 1) * chunk if i < 6 else n
        daily_closes.append(spark[end - 1])
    spike_idx = -1
    spike_pct = 0
    for i in range(1, len(daily_closes)):
        if daily_closes[i-1] <= 0:
            continue
        chg = (daily_closes[i] - daily_closes[i-1]) / daily_closes[i-1] * 100
        if chg > 50:
            spike_idx = i
            spike_pct = chg
    if spike_idx == -1:
        return 99, 0, daily_closes
    days_ago = (len(daily_closes) - 1) - spike_idx
    return days_ago, spike_pct, daily_closes

def get_global_data():
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

def analyze_outcome(sig, cur, days):
    entry = sig.get("price", 0)
    tp1 = sig.get("tp1", 0)
    sl = sig.get("sl", 0)
    high_7d = sig.get("high_7d", entry)
    if entry == 0 or tp1 == 0:
        return 30, "Unknown - no data", "WAIT - No clear next signal", 0, 40, 30
    total_dist = abs(entry - tp1)
    moved = abs(entry - cur) if (sig.get("side")=="SHORT" and cur < entry) or (sig.get("side")=="LONG" and cur > entry) else -abs(cur - entry)
    progress = max(0, min(100, (moved / total_dist * 100) if total_dist > 0 else 0))
    if progress >= 70:
        p_tp1, p_chop, p_sl = 65, 25, 10
        cause = "On track - move in progress, momentum intact"
    elif progress >= 40:
        p_tp1, p_chop, p_sl = 45, 35, 20
        cause = "Slowing - move stalled, opposite side defending"
    elif progress >= 20:
        p_tp1, p_chop, p_sl = 30, 45, 25
        cause = "Momentum lost - stalled for days, volume fading"
    else:
        if (sig.get("side")=="SHORT" and cur >= entry) or (sig.get("side")=="LONG" and cur <= entry):
            p_tp1, p_chop, p_sl = 15, 35, 50
            cause = "Invalidated - price back past entry, thesis wrong"
        else:
            p_tp1, p_chop, p_sl = 20, 50, 30
            cause = "Dead - no momentum, chop / sideways"
    if days >= 5 and progress < 50:
        p_tp1 = max(10, p_tp1 - 15)
        p_chop = p_chop + 10
        cause += " | Overdue - past expected 3-5 days"
    if sig.get("side")=="SHORT":
        if cur >= high_7d or cur >= entry * 1.05:
            next_sig = "INVALIDATED - DO NOT RE-SHORT | Next: WATCH LONG if it holds above high for 24h"
            next_sig += f"\nRe-short only if pumps +15% to {fmt(entry * 1.15)} then rejects"
        elif progress >= 50:
            bounce = fmt(cur * 1.12)
            next_sig = f"HOLD / RE-SHORT ON BOUNCE | Next: If bounces +12% to {bounce} and rejects, re-short"
        elif progress >= 20:
            next_sig = "WAIT - Shed never started properly | Next: Ignore until fresh pump +50% from here, then re-evaluate"
        else:
            next_sig = "NO TRADE - Chop / Invalidated | Next: Move on, ignore coin until new pump"
    else:
        low_7d = sig.get("low_7d", entry)
        if cur <= low_7d or cur <= entry * 0.95:
            next_sig = "INVALIDATED - DO NOT RE-LONG | Broke below low, dump won"
            next_sig += f"\nRe-long only if dumps -15% to {fmt(entry * 0.85)} then holds"
        elif progress >= 50:
            dip = fmt(cur * 0.88)
            next_sig = f"HOLD / RE-LONG ON DIP | Next: If dips -12% to {dip} and holds, re-long"
        elif progress >= 20:
            next_sig = "WAIT - Bounce never started properly | Next: Ignore until fresh dump -50% from here, then re-evaluate"
        else:
            next_sig = "NO TRADE - Chop / Invalidated | Next: Move on, ignore coin until new pump"
    return p_tp1, cause, next_sig, progress, p_chop, p_sl

def analyze_sl(sig, cur, days):
    entry = sig.get("price", 0)
    high_7d = sig.get("high_7d", entry)
    low_7d = sig.get("low_7d", entry)
    sl = sig.get("sl", entry)
    side = sig.get("side","SHORT")
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
        hit = None
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
        if not hit and days >= WARNING_DAY and not sig.get("warned_5d"):
            p_tp1, cause, next_sig, progress, p_chop, p_sl = analyze_outcome(sig, cur, days)
            pct_now = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
            msg = f"⚠️ <b>{sym} Day {days:.1f} WARNING</b> - {group}\nStill no TP1 after {days:.1f} days (Expected: {expected})\nNow: {fmt(cur)} | Result so far: {pct_now:+.1f}% | Progress to TP1: {progress:.0f}%\nProbability to still hit TP1: {p_tp1}% | Chop: {p_chop}% | SL: {p_sl}%\nProbable Cause: {cause}\nAction: Consider exiting / move SL to entry. Bot will auto-expire on Day {MAX_ACTIVE_DAYS}."
            send_telegram(msg)
            sig["warned_5d"] = True
            print(f"{sym} Day 5 WARNING sent - Progress {progress:.0f}%")
        if not hit and days >= MAX_ACTIVE_DAYS:
            hit = "EXPIRED"
        if hit:
            record = {
                "sym": sym, "side": side, "group": group,
                "entry": entry, "exit_price": cur, "hit": hit,
                "pumped": sig.get("pumped"), "shed": sig.get("shed"),
                "time_in": sig.get("time"), "time_out": now.isoformat(),
                "days_taken": round(days, 2),
                "expected_days": expected,
                "tp1": tp1, "tp2": tp2, "runner": runner, "sl": sl,
            }
            history.append(record)
            save_json(HISTORY_FILE, history)
            to_remove.append(sym)
            pct = (entry - cur)/entry*100 if side == "SHORT" else (cur - entry)/entry*100
            if hit == "EXPIRED":
                p_tp1, cause, next_sig, progress, p_chop, p_sl = analyze_outcome(sig, cur, days)
                msg = f"⏰ <b>{sym} EXPIRED</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nResult: {pct:+.1f}% | Progress to TP1: {progress:.0f}% | Days held: {days:.2f} (Expected: {expected})\n\n📊 <b>Probability if held longer:</b>\nTP1: {p_tp1}% | Chop: {p_chop}% | SL: {p_sl}%\n\n🔍 <b>Probable Cause:</b>\n{cause}\n\n➡️ <b>Next Signal:</b>\n{next_sig}\n\nClosing - no more tracking"
                print(f"{sym} EXPIRED after {days:.2f}d - Prob TP1 {p_tp1}%")
            elif hit == "SL":
                cause, next_sig, p_pump, p_dump, p_chop = analyze_sl(sig, cur, days)
                msg = f"🛑 <b>{sym} SL HIT</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nLoss: {pct:+.1f}% | Days: {days:.2f} (Expected: {expected})\n\n🔍 <b>Probable Cause:</b>\n{cause}\n\n📊 <b>What to expect next:</b>\nPump again: {p_pump}% | Dump back: {p_dump}% | Chop: {p_chop}%\n\n➡️ <b>Next Signal:</b>\n{next_sig}"
                print(f"{sym} SL HIT in {days:.2f}d - Pump again {p_pump}%")
            else:
                msg = f"✅ <b>{sym} {hit} HIT</b> - {group}\nEntry: {fmt(entry)} -> Now: {fmt(cur)}\nProfit: {pct:+.1f}%\nDays taken: {days:.2f} days (Expected: {expected})\nPumped was +{sig.get('pumped',0):.1f}%"
                print(f"{sym} {hit} HIT in {days:.2f}d - Expected {expected}")
            send_telegram(msg)
    for sym in to_remove:
        del active[sym]
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
        price_exec = m["price"]
        vol_local = m["vol"]
        g = global_data.get(sym, {})
        cap_now = g.get("cap_now", 0)
        global_price = g.get("global_price", price_exec)
        global_vol = g.get("global_vol", vol_local)
        if cap_now == 0 or global_price == 0:
            print(f"{sym} SKIP - No global data, cannot calc Pumped")
            continue
        spark = g.get("spark_7d", [])
        if not spark:
            print(f"{sym} SKIP - No 7d sparkline")
            continue
        low_7d = min(spark)
        high_7d = max(spark)
        cap_at_low = cap_now * (low_7d / global_price) if global_price > 0 else cap_now
        group, pump_thresh, expected_shed = get_group(cap_at_low)
        pumped = (high_7d - low_7d) / low_7d * 100 if low_7d > 0 else 0
        shed = (high_7d - global_price) / high_7d * 100 if high_7d > 0 else 0
        net = (global_price - low_7d) / low_7d * 100 if low_7d > 0 else 0
        print(f"{sym} | {group} CapLow ${cap_at_low/1e6:.1f}M (CapNow ${cap_now/1e6:.1f}M) | Pumped +{pumped:.1f}% / Need +{pump_thresh}% | Shed -{shed:.1f}% | Net +{net:.1f}%")
        if max(global_vol, vol_local) < MIN_VOLUME:
            print(f"{sym} SKIP - Vol ${max(global_vol, vol_local):,.0f} < $5M")
            continue
        side = None
        reason = ""
        if pumped >= pump_thresh:
            days_ago, spike_pct, daily_closes = days_since_spike(spark)
            print(f"{sym} Spike check: last +50% day was {days_ago}d ago (+{spike_pct:.0f}%)")
            if days_ago < 2:
                print(f"{sym} SKIP V900.3 - Spike {days_ago}d ago (+{spike_pct:.0f}%) - TOO EARLY, whale still defending. Wait.")
                continue
            if shed < expected_shed:
                side = "SHORT"
                reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed only -{shed:.1f}% so far, expected -{expected_shed}% - SHORT now | Spike was {days_ago}d ago (+{spike_pct:.0f}%), cooled"
                if days_ago == 99:
                    reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed only -{shed:.1f}% so far, expected -{expected_shed}% - SHORT now | No 1-day spike, grind pump, cooled"
            else:
                if net <= 0:
                    print(f"{sym} SKIP LONG - Net {net:.1f}% <= 0, broke below 7d low, dead coin")
                    continue
                side = "LONG"
                reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed -{shed:.1f}% DONE (expected -{expected_shed}%), net still +{net:.1f}% - LONG bounce now | Spike was {days_ago}d ago (+{spike_pct:.0f}%), cooled"
                if days_ago == 99:
                    reason = f"{group} pumped +{pumped:.1f}% hit +{pump_thresh}%, shed -{shed:.1f}% DONE (expected -{expected_shed}%), net still +{net:.1f}% - LONG bounce now | No 1-day spike, grind pump, cooled"
        if side is None:
            print(f"{sym} SKIP - Pumped +{pumped:.1f}% < +{pump_thresh}%")
            continue
        entry_price = price_exec
        entry_high = round(price_exec * 1.02, 8)
        entry_low = round(price_exec * 0.98, 8)
        valid_until = now + timedelta(hours=1)
        if side == "SHORT":
            sl = round(price_exec * 1.10, 8)
            tp1 = round(price_exec * (1 - (expected_shed/100)*0.5), 8)
            tp2 = round(price_exec * (1 - expected_shed/100), 8)
            runner = round(price_exec * (1 - (expected_shed/100)*1.5), 8)
            emoji = "🔴"
        else:
            sl = round(price_exec * 0.90, 8)
            tp1 = round(price_exec * (1 + (expected_shed/100)*0.5), 8)
            tp2 = round(price_exec * (1 + expected_shed/100), 8)
            runner = round(price_exec * (1 + (expected_shed/100)*1.5), 8)
            emoji = "🟢"
        candidates.append({
            "sym": sym, "side": side, "price": entry_price,
            "entry_high": entry_high, "entry_low": entry_low,
            "valid_until": valid_until,
            "pumped": pumped, "shed": shed, "net": net,
            "cap_at_low": cap_at_low, "cap_now": cap_now, "group": group,
            "low_7d": low_7d, "high_7d": high_7d,
            "sl": sl, "tp1": tp1, "tp2": tp2, "runner": runner,
            "reason": reason, "emoji": emoji,
            "vol": max(global_vol, vol_local),
            "days_ago": days_ago, "spike_pct": spike_pct,
            "expected_shed": expected_shed
        })
    # === V900.3 BEST ONLY - Same as manual ranking ===
    # Sort by: Group first, then Net, then Vol - No score
    if candidates:
        candidates.sort(key=lambda x: (GROUP_RANK.get(x["group"], 0), x["net"], x["vol"]), reverse=True)
        best = candidates[0]
        print(f"BEST: {best['sym']} {best['group']} Net +{best['net']:.1f}% Vol ${best['vol']:,.0f} - sending, {len(candidates)-1} others skipped")
        for c in candidates[1:]:
            print(f"SKIPPED - {c['sym']} {c['group']} Net +{c['net']:.1f}% Vol ${c['vol']:,.0f} - weaker than {best['sym']}")
        sym = best["sym"]
        signal = {
            "sym": sym, "side": best["side"], "price": best["price"],
            "entry_high": best["entry_high"], "entry_low": best["entry_low"],
            "valid_until": best["valid_until"].isoformat(),
            "pumped": best["pumped"], "shed": best["shed"], "net": best["net"],
            "cap_at_low": best["cap_at_low"], "group": best["group"],
            "low_7d": best["low_7d"], "high_7d": best["high_7d"],
            "sl": best["sl"], "tp1": best["tp1"], "tp2": best["tp2"], "runner": best["runner"],
            "reason": best["reason"], "time": now.isoformat(), "warned_5d": False,
            "days_since_spike": best["days_ago"],
            "spike_pct": best["spike_pct"]
        }
        active[sym] = signal
        exp_days = EXPECTED_DAYS.get(best["group"], "3-5 days")
        msg = (
            f"{best['emoji']} <b>V900.3 PERP {best['side']} {sym}</b> - {best['group']} - BEST SIGNAL\n"
            f"Expected to TP2: {exp_days}\n"
            f"Cap at Low: ${best['cap_at_low']/1e6:.1f}M (Now ${best['cap_now']/1e6:.1f}M)\n"
            f"Pumped: +{best['pumped']:.1f}%\n"
            f"Shed so far: -{best['shed']:.1f}% (Expected -{best['expected_shed']}%)\n"
            f"Net: +{best['net']:.1f}%\n"
            f"Low 7d: {fmt(best['low_7d'])} | High 7d: {fmt(best['high_7d'])}\n"
            f"Global Vol: ${best['vol']:,.0f}\n"
            f"{best['reason']}\n"
            f"\n🎯 <b>ENTER AT: {fmt(best['price'])}</b>\n"
            f"Entry Zone: {fmt(best['entry_low'])} - {fmt(best['entry_high'])}\n"
            f"Valid Until: {best['valid_until'].strftime('%H:%M')} EAT (+1h) - If price is outside zone when you see this, SKIP, do not chase\n"
            f"SL: {fmt(best['sl'])}\n"
            f"TP1: {fmt(best['tp1'])}\n"
            f"TP2: {fmt(best['tp2'])}\n"
            f"Runner: {fmt(best['runner'])}"
        )
        send_telegram(msg)
        print(f"{sym} {best['side']} - BEST SIGNAL SENT")
    save_json(ACTIVE_FILE, active)
    print(f"Done - Active: {len(active)}")

if __name__ == "__main__":
    run_once()
