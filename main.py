import ccxt
import pandas as pd
import requests

# --- CONFIGURATION & ENV ---
BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
CF = "last_alerts.json"
TF = "trades.json"
MIN_SCORE = 75

SYMBOLS = [
    "VELVET/USDT:USDT",
    "KOMA/USDT:USDT",
    "GRASS/USDT:USDT",
    "SIREN/USDT:USDT",
    "HEI/USDT:USDT",
    "LAB/USDT:USDT",
]


# --- UTILITY & API FUNCTIONS ---
def ge():
    """Initializes and returns the MEXC exchange instance."""
    return ccxt.mexc(
        {
            "apiKey": os.getenv("MEXC_API_KEY", ""),
            "secret": os.getenv("MEXC_SECRET_KEY", ""),
            "options": {"defaultType": "swap"},
      def gc(s):
    """Fetches 24h ticker data from MEXC REST API for a given symbol."""
    try:
        # Properly clean and format the symbol string for the API call
        cleaned = s.split("/")[0] + "USDT"
        url = f"https://mexc.com{cleaned}"
        r = requests.get(url, timeout=10).json()
        if isinstance(r, list) and len(r) > 0:
            return float(r[0].get("priceChangePercent", 0))
        return float(r.get("priceChangePercent", 0))
    except Exception:
        return 0.0  }
    )


def gc(s):
    """Fetches 24h ticker data from MEXC REST API for a given symbol."""
    try:
        cleaned = s.split("/")[0] + "USDT"
        url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={cleaned}"
        r = requests.get(url, timeout=10).json()
        if isinstance(r, list) and len(r) > 0:
            return float(r[0].get("priceChangePercent", 0))
        return float(r.get("priceChangePercent", 0))
    except Exception:
        return 0.0


def tg(m):
    """Sends a markdown-formatted message to the configured Telegram channel."""
    if not BOT or not CHAT:
        print(f"[Telegram Mock]: {m}")
        return
    url = f"https://telegram.org{BOT}/sendMessage"
    try:
        requests.post(
            url, json={"chat_id": CHAT, "text": m, "parse_mode": "Markdown"}, timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")


def lc():
    """Loads the alert cooldown tracking registry."""
    if os.path.exists(CF):
        try:
            with open(CF, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def sc(d):
    """Saves the alert cooldown tracking registry."""
    try:
        with open(CF, "w") as f:
            json.dump(d, f, indent=4)
    except Exception as e:
        print(f"Error saving tracking file: {e}")


def lt():
    """Loads open active trade tracking database."""
    if os.path.exists(TF):
        try:
            with open(TF, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def st(d):
    """Saves the active trade tracking database."""
    try:
        with open(TF, "w") as f:
            json.dump(d, f, indent=4)
    except Exception as e:
        print(f"Error saving trades file: {e}")


def fs(ex, sym, tf="15m", lim=200):
    """Fetches OHLCV historical candlestick data dataframes via CCXT."""
    try:
        data = ex.fetch_ohlcv(sym, timeframe=tf, limit=lim)
        df = pd.DataFrame(
            data, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching candles for {sym}: {e}")
        return pd.DataFrame()


# --- INDICATORS & TECHNICAL ANALYSIS ---
def rsi(c, p=14):
    """Calculates Relative Strength Index series from Close prices."""
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=p, min_periods=p).mean()
    avg_loss = loss.rolling(window=p, min_periods=p).mean()

    for i in range(p, len(c)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (p - 1) + gain.iloc[i]) / p
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (p - 1) + loss.iloc[i]) / p

    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def btc_t(ex):
    """Checks the macro BTC trend filter via 4h 50/200 Exponential Moving Average alignment."""
    try:
        df = fs(ex, "BTC/USDT:USDT", tf="4h", lim=250)
        if df.empty or len(df) < 200:
            return "CHOP"
        ema50 = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = df["close"].ewm(span=200, adjust=False).mean().iloc[-1]
        return "BULL" if ema50 > ema200 else "BEAR"
    except Exception:
        return "CHOP"


def filt(sym, typ):
    """Enforces cooldown timers between signals per symbol and action direction."""
    reg = lc()
    k = f"{sym}_{typ}"
    now_ts = datetime.utcnow().timestamp()
    if k in reg:
        if now_ts - reg[k] < 7200:  # 2 Hours Cooldown Window
            return False
    reg[k] = now_ts
    sc(reg)
    return True


# --- STRATEGY SCORING SYSTEM MODULES ---
def ob_c(df):
    """Scores Order Block footprints across structure matrix points."""
    return 20 if df["volume"].iloc[-1] > df["volume"].rolling(20).mean().iloc[-1] else 0


def eq_c(df):
    """Scores double equal extreme levels detection limits (EQH / EQL)."""
    h1, h2 = df["high"].iloc[-2], df["high"].iloc[-3]
    l1, l2 = df["low"].iloc[-2], df["low"].iloc[-3]
    score = 0
    if abs(h1 - h2) / h1 < 0.0005:
        score += 25
    if abs(l1 - l2) / l1 < 0.0005:
        score += 25
    return min(score, 25)


def tur_c(df):
    """Scores classic Turtle Soup stop-run counters."""
    last_low = df["low"].iloc[-1]
    last_high = df["high"].iloc[-1]
    low_20 = df["low"].iloc[-21:-1].min()
    high_20 = df["high"].iloc[-21:-1].max()
    if last_low < low_20 and df["close"].iloc[-1] > low_20:
        return 25
    if last_high > high_20 and df["close"].iloc[-1] < high_20:
        return 25
    return 0


def mss_c(df):
    """Scores Market Structure Shift confirmations via local swing breaks."""
    close = df["close"].iloc[-1]
    high_10 = df["high"].iloc[-11:-1].max()
    low_10 = df["low"].iloc[-11:-1].min()
    if close > high_10 or close < low_10:
        return 20
    return 0


def pd_c(df):
    """Scores execution zone within Premium vs Discount ranges."""
    h_max = df["high"].rolling(20).max().iloc[-1]
    l_min = df["low"].rolling(20).min().iloc[-1]
    rng = h_max - l_min
    if rng == 0:
        return 0
    pos = (df["close"].iloc[-1] - l_min) / rng
    if pos < 0.3 or pos > 0.7:
        return 10
    return 0


def liq_sweep_c(df):
    """Evaluates high priority Liquidity Sweeps via ATR and candle wicks metrics."""
    h, l, o, c = df["high"].iloc[-1], df["low"].iloc[-1], df["open"].iloc[-1], df["close"].iloc[-1]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1] if len(df) >= 14 else (h - l)
    if atr == 0:
        return 0, "NONE"

    u_wick = h - max(o, c)
    l_wick = min(o, c) - l

    if l_wick > 1.5 * atr and c > o:
        return 30, "BULL"
    if u_wick > 1.5 * atr and c < o:
        return 30, "BEAR"
    return 0, "NONE"


def whale_manip_c(df):
    """Identifies Whale Trap abnormalities or Real Buying Breakouts."""
    v_now = df["volume"].iloc[-1]
    v_avg = df["volume"].rolling(20).mean().iloc[-1]
    chg = abs(df["close"].iloc[-1] - df["open"].iloc[-1]) / df["open"].iloc[-1]

    if v_now > 3 * v_avg and chg < 0.002:
        return 0, "FAKE"
    if v_now > 2.5 * v_avg and df["close"].iloc[-1] > df["high"].iloc[-2]:
        return 20, "REAL_BUY"
    return 0, "NONE"


def fvg_c(df):
    """Scores Fair Value Gaps displacements imbalance footprints."""
    if (df["low"].iloc[-1] > df["high"].iloc[-3]) or (df["high"].iloc[-1] < df["low"].iloc[-3]):
        return 15
    return 0


def kz_c():
    """Identifies session timeline Killzones and attributes dynamic scores/weights."""
    hr = datetime.utcnow().hour
    if 8 <= hr < 11:
        return 5, "LONDON"
    elif 13 <= hr < 16:
        return 10, "NY"
    elif 0 <= hr < 2:
        return -5, "ASIAN"
    return 0, "NONE"


def score_v8(df):
    """Aggregates absolute matrix values into a directional scoring report."""
    bull, bear = 0, 0
    fakes = []

    ob = ob_c(df)
    eq = eq_c(df)
    tur = tur_c(df)
    mss = mss_c(df)
    pd_v = pd_c(df)
    fvg = fvg_c(df)

    kz_w, kz_n = kz_c()
    if kz_n == "ASIAN":
        fakes.append("Asian Session Chop Box")

    ls_pts, ls_dir = liq_sweep_c(df)
    wm_pts, wm_msg = whale_manip_c(df)

    if wm_msg == "FAKE":
        fakes.append("Whale Manipulation Trap Detected")

    # Composite Allocation Routing
    base_pool = ob + eq + tur + mss + pd_v + fvg
    if kz_w > 0:
        base_pool += kz_w

    c_close = df["close"].iloc[-1]
    ma20 = df["close"].rolling(20).mean().iloc[-1]

    if c_close >= ma20:
        bull += base_pool + (ls_pts if ls_dir == "BULL" else 0) + (wm_pts if wm_msg == "REAL_BUY" else 0)
    if c_close <= ma20:
        bear += base_pool + (ls_pts if ls_dir == "BEAR" else 0)

    return bull, bear, fakes


# --- TRAILING HOLD LOGIC MATRIX ENGINE ---
def is_consolidating(df):
    """Evaluates channel range volatility compressions."""
    last20 = df["close"].iloc[-20:]
    rng = (last20.max() - last20.min()) / last20.min()
    v5 = df["volume"].iloc[-5:].mean()
    v_avg = df["volume"].rolling(20).mean().iloc[-1]
    return rng < 0.028 and v5 < (v_avg * 0.75)


def vol_profit_c(df, pnl):
    """Parses volume delta adjustments for holding/taking profits logic."""
    v_now = df["volume"].iloc[-1]
    v_prev = df["volume"].iloc[-2]
    v_avg = df["volume"].rolling(20).mean().iloc[-1]

    if pnl > 0 and v_now > 1.30 * v_prev and v_now > 1.30 * v_avg:
        return "VOLBUYINCREASE" if df["close"].iloc[-1] > df["open"].iloc[-1] else "VOLSELLINCREASE"
    if v_now < 0.70 * v_avg:
        return "VOLBUYDECREASE" if df["close"].iloc[-1] > df["open"].iloc[-1] else "VOLSELLDECREASE"
    return "CONTINUE"


def junction_decision(df, position_type):
    """Determines breakout boundary validation checkpoints inside boxes."""
    if not is_consolidating(df):
        return "CONTINUE"

    c_close = df["close"].iloc[-1]
    ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
    r_val = rsi(df["close"]).iloc[-1]

Use code with caution.
if position_type == "LONG":
if r_val > 58 and c_close > ema20:
return "HOLD_BULL"
if r_val < 48:
return "EXIT_WARN"
elif position_type == "SHORT":
if r_val < 42 and c_close < ema20:
return "HOLD_BEAR"
return "CONTINUE"
--- EXECUTION HOOKS ENGINE ---
def execute_signal_scan(ex):
"""Scans and acts on trade entry parameters for all 6 coins."""
print("Executing Signal Entry Scan Loop...")
btc_status = btc_t(ex)
for sym in SYMBOLS:
df = fs(ex, sym, tf="15m", lim=200)
if df.empty or len(df) < 40:
continue
# Volume Filter Calculation
v5_avg = df["volume"].iloc[-5:].mean()
v20_avg = df["volume"].rolling(20).mean().iloc[-1]
if v5_avg <= (1.3 * v20_avg):
continue
bull, bear, fakes = score_v8(df)
high_score = max(bull, bear)
total_score = 50 + high_score
if total_score < MIN_SCORE:
continue
typ = "LONG" if bull >= bear else "SHORT"
# 24h Change Filter Guardrails
chg_24h = gc(sym)
if abs(chg_24h) > 12.0:
fakes.append("Volatility Overflow Extreme Pump/Dump > 12%")
if typ == "LONG" and chg_24h < -8.0:
fakes.append("Long Blocked: Too Deep Downward Slope <-8%")
if typ == "SHORT" and chg_24h > 8.0:
fakes.append("Short Blocked: Too Highly Pumped Above >+8%")
# Final Filter Validations
if btc_status == "CHOP":
fakes.append("BTC Correlation Disrupted")
if typ == "LONG" and btc_status == "BEAR":
fakes.append("Against Macro BTC Trend Direction")
if typ == "SHORT" and btc_status == "BULL":
fakes.append("Against Macro BTC Trend Direction")
if is_consolidating(df):
fakes.append("Locked inside tight consolidation box")
if len(fakes) > 0:
print(f"Skipping Entry {sym} due to Filters: {fakes}")
continue
if not filt(sym, typ):
continue
# Build Trade Matrix Parameters
entry_price = float(df["close"].iloc[-1])
sl = entry_price * 0.97 if typ == "LONG" else entry_price * 1.03
tp = entry_price * 1.06 if typ == "LONG" else entry_price * 0.94
strength = "MAX" if total_score >= 80 else "STRONG" if total_score >= 60 else "WEAK"
if strength == "WEAK":
continue
# Transmit Alert Notification
alert_msg = (
f"🚀 KOMA NEW SIGNAL AVAILABLE\n\n"
f"• Asset: {sym}\n"
f"• Direction: {typ}\n"
f"• Score Metrics: {total_score} ({strength})\n"
f"• Execution Price: {entry_price}\n"
f"• Stop Loss: {sl:.5f}\n"
f"• Take Profit: {tp:.5f}\n"
f"• 24h Delta: {chg_24h}%"
)
tg(alert_msg)
# Database Pipeline Storage Tracking Update
trades = lt()
trades[sym] = {
"type": typ,
"entry_price": entry_price,
"sl": sl,
"tp": tp,
"last_hold_alert": 0,
}
st(trades)
def execute_hold_scan(ex):
"""Evaluates open positions metrics to transmit trailing hold signals."""
print("Executing Active Trades Tracking Engine...")
trades = lt()
if not trades:
return
now_ts = datetime.utcnow().timestamp()
for sym in list(trades.keys()):
df = fs(ex, sym, tf="15m", lim=200)
if df.empty:
continue
t_data = trades[sym]
c_price = float(df["close"].iloc[-1])
# Evaluate Position PNL Context
if t_data["type"] == "LONG":
pnl = (c_price - t_data["entry_price"]) / t_data["entry_price"]
is_invalidated = c_price <= t_data["sl"] or c_price >= t_data["tp"]
else:
pnl = (t_data["entry_price"] - c_price) / t_data["entry_price"]
is_invalidated = c_price >= t_data["sl"] or c_price <= t_data["tp"]
if is_invalidated:
print(f"Trade target or stop invalidation met for {sym}. Cleaning tracking database records.")
del trades[sym]
st(trades)
continue
# Parse Volumetric Profit Mechanics (1-hour message rate throttle)
if now_ts - t_data.get("last_hold_alert", 0) > 3600:
vol_verdict = vol_profit_c(df, pnl)
if vol_verdict in ["VOLBUYINCREASE", "VOLSELLINCREASE"]:
tg(f"📈 HOLD ACTIVE LOGIC [{sym}]\nVolume momentum increasing. Maintain {t_data['type']} pattern positions structure safely.")
t_data["last_hold_alert"] = now_ts
elif vol_verdict in ["VOLBUYDECREASE", "VOLSELLDECREASE"]:
tg(f"⚠️ TAKE PROFIT ADVISORY [{sym}]\nVolume velocity exhaustion warning detected. Consider locking returns fractions.")
t_data["last_hold_alert"] = now_ts
# Parse Junction Consolidation Channels Breakouts Checkpoints
junc_verdict = junction_decision(df, t_data["type"])
if junc_verdict in ["HOLD_BULL", "HOLD_BEAR"]:
tg(f"💎 JUNCTION BOX HOLD [{sym}]\nConsolidation breakout bias aligned strong. HOLD POSITION verified.")
elif junc_verdict == "EXIT_WARN":
tg(f"🚨 JUNCTION EXIT WARNING [{sym}]\nStructural range momentum distribution breakdown alert! Protect capital allocations.")
del trades[sym]
st(trades)
def main():
"""Main Orchestrator Entrypoint Loop Interface."""
print("KOMA BOT V9.1 Daemon Engine Starting Up Operational Cycles...")
ex = ge()
while True:
try:
execute_signal_scan(ex)
execute_hold_scan(ex)
except Exception as e:
print(f"Runtime Operational Loop Instability Error Exception: {e}")
print("Execution tracking wave window finished. Sleeping 60 seconds...")
time.sleep(60)
if name == "main":
main()
