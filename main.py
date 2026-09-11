import ccxt
import pandas as pd
import requests
import os, json, time
from datetime import datetime, timedelta
from filters import check_all_filters
from autopilot import auto_trade

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")
CF = "last_alerts.json"
TF = "trades.json"
MIN_SCORE = 75

last_sent_time = {}
def is_duplicate(coin, minutes=30):
    now_ts = time.time()
    if coin in last_sent_time:
        if now_ts - last_sent_time[coin] < minutes * 60:
            return True
    last_sent_time[coin] = now_ts
    return False

SYMBOLS = [
 "VELVET/USDT:USDT",
 "KOMA/USDT:USDT",
 "GRASS/USDT:USDT",
 "SIREN/USDT:USDT",
 "HEI/USDT:USDT",
 "LAB/USDT:USDT"
]

def ge():
 ex = ccxt.mexc({'enableRateLimit': True})
 return ex, "MEXC-FUT"

def gc(s):
 c = s.replace("/","").replace(":USDT","")
 c = c.replace(":","")
 if not c.endswith("USDT"):
  c += "USDT"
 try:
  url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={c}"
  r = requests.get(url, timeout=5).json()
  return float(r.get('priceChangePercent',0))
 except:
  return 0.0

def filt(sym, typ):
 d = gc(sym)
 if typ == "LONG" and d < -8:
  return False
 if typ == "SHORT" and d > 8:
  return False
 if abs(d) > 12:
  return False
 return True

def tg(m):
 try:
  url = f"https://api.telegram.org/bot{BOT}/sendMessage"
  requests.post(url, data={"chat_id": CHAT, "text": m, "parse_mode": "Markdown"}, timeout=15)
 except:
  pass

def lc():
 try:
  with open(CF,"r") as f:
   data = json.load(f)
   out = {}
   for k,v in data.items():
    out[k] = datetime.fromisoformat(v)
   return out
 except:
  return {}

def sc(d):
 try:
  with open(CF,"w") as f:
   out = {}
   for k,v in d.items():
    out[k] = v.isoformat()
   json.dump(out, f)
 except:
  pass

def lt():
 try:
  with open(TF,"r") as f:
   return json.load(f)
 except:
  return {}

def st(d):
 try:
  with open(TF,"w") as f:
   json.dump(d, f, default=str)
 except:
  pass

def rsi(c, p=14):
 d = c.diff()
 g = d.where(d>0,0).rolling(p).mean()
 l = -d.where(d<0,0).rolling(p).mean()
 return 100-(100/(1+g/l))

def fs(ex, sym, tf, lim):
 try:
  o = ex.fetch_ohlcv(sym, tf, limit=lim)
  if not o or len(o) < 60:
   print(f"❌ FETCH FAIL {sym} len={len(o) if o else 0}")
   return None
  df = pd.DataFrame(o)
  df.columns = ['ts','open','high','low','close','vol']
  for col in ['close','high','low','open','vol']:
   df[col] = df[col].astype(float)
  return df
 except Exception as e:
  print(f"❌ FETCH ERR {sym}: {e}")
  return None

def btc_t(ex):
 try:
  df = fs(ex, "BTC/USDT:USDT", "4h", 50)
  if df is None:
   return "BTC_NEUTRAL"
  e50 = df['close'].ewm(span=50).mean().iloc[-1]
  e200 = df['close'].ewm(span=200).mean().iloc[-1]
  cp = df['close'].iloc[-1]
  if cp > e50 > e200:
   return "BTC_BULL"
  if cp < e50 < e200:
   return "BTC_BEAR"
  return "BTC_NEUTRAL"
 except:
  return "BTC_NEUTRAL"

def kz_c():
 try:
  h = datetime.utcnow().hour
  if 0 <= h <= 3:
   return "ASIAN_KZ", 3
  if 8 <= h <= 11:
   return "LONDON_KZ", 5
  if 13 <= h <= 16:
   return "NY_KZ", 5
  return "OFF_KZ", 0
 except:
  return "OFF_KZ", 0

def ob_c(df):
 try:
  last = df.tail(10)
  if last['low'].min() < df['low'].iloc[-20:-10].min():
   return "BULL_OB", 10
  if last['high'].max() > df['high'].iloc[-20:-10].max():
   return "BEAR_OB", 10
  return "NO_OB", 0
 except:
  return "NO_OB", 0

def eq_c(df):
 try:
  lows = df['low'].tail(20)
  highs = df['high'].tail(20)
  if (lows.max()-lows.min())/lows.min()*100 < 0.5:
   return "EQ_LOWS", 10
  if (highs.max()-highs.min())/highs.min()*100 < 0.5:
   return "EQ_HIGHS", 10
  return "NO_EQ", 0
 except:
  return "NO_EQ", 0

def tur_c(df):
 try:
  if df['low'].iloc[-1] < df['low'].iloc[-20:-1].min():
   if df['close'].iloc[-1] > df['low'].iloc[-20:-1].min():
    return "TURTLE_LONG", 15
  if df['high'].iloc[-1] > df['high'].iloc[-20:-1].max():
   if df['close'].iloc[-1] < df['high'].iloc[-20:-1].max():
    return "TURTLE_SHORT", 15
  return "NO_TURTLE", 0
 except:
  return "NO_TURTLE", 0

def mss_c(df):
 try:
  if df['high'].iloc[-1] > df['high'].iloc[-2]:
   if df['high'].iloc[-2] < df['high'].iloc[-3]:
    return "MSS_BULL", 10
  if df['low'].iloc[-1] < df['low'].iloc[-2]:
   if df['low'].iloc[-2] > df['low'].iloc[-3]:
    return "MSS_BEAR", 10
  return "NO_MSS", 0
 except:
  return "NO_MSS", 0

def pd_c(df):
 try:
  high = df['high'].tail(50).max()
  low = df['low'].tail(50).min()
  mid = (high+low)/2
  cp = df['close'].iloc[-1]
  if cp < mid:
   return "DISCOUNT", 10
  else:
   return "PREMIUM", 0
 except:
  return "NO_PD", 0

def fvg_c(df):
 try:
  if df['low'].iloc[-1] > df['high'].iloc[-3]:
   return "BULL_FVG", 10
  if df['high'].iloc[-1] < df['low'].iloc[-3]:
   return "BEAR_FVG", 10
  return "NO_FVG", 0
 except:
  return "NO_FVG", 0

def liq_sweep_c(df):
 try:
  if df['low'].iloc[-1] < df['low'].iloc[-10:-1].min():
   vol_up = df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5
   if vol_up:
    if df['close'].iloc[-1] > df['low'].iloc[-10:-1].min():
     return "LIQ_SWEEP_LONG", 30
  if df['high'].iloc[-1] > df['high'].iloc[-10:-1].max():
   vol_up = df['vol'].iloc[-1] > df['vol'].iloc[-10:-1].mean()*1.5
   if vol_up:
    if df['close'].iloc[-1] < df['high'].iloc[-10:-1].max():
     return "LIQ_SWEEP_SHORT", 30
  return "NO_SWEEP", 0
 except:
  return "NO_SWEEP", 0

def whale_manip_c(df):
 try:
  c1 = df['close'].iloc[-3]
  c2 = df['close'].iloc[-2]
  c3 = df['close'].iloc[-1]
  v1 = df['vol'].iloc[-3]
  v2 = df['vol'].iloc[-2]
  v3 = df['vol'].iloc[-1]
  if v2 > v1*2 and v2 > v3*2:
   if c2 < c1 and c2 < c3:
    return "WHALE_FAKE_DOWN", -20
   if c2 > c1 and c2 > c3:
    return "WHALE_FAKE_UP", -20
  return "NO_WHALE", 0
 except:
  return "NO_WHALE", 0

def vol_profit_c(df, pnl):
 if pnl < 0.8:
  return "NO_VOL",0,"NONE"
 vp = df['vol'].iloc[-2]
 vn = df['vol'].iloc[-1]
 va = df['vol'].iloc[-20:-1].mean()
 bull = df['close'].iloc[-1] > df['open'].iloc[-1]
 if vn > vp*1.30 and vn > va:
  if bull:
   return "VOLBUYINCREASE",15,"HOLD_LONG"
  else:
   return "VOLSELLINCREASE",15,"HOLD_SHORT"
 if vn < vp*0.70:
  if bull:
   return "VOLBUYDECREASE",0,"TP_LONG"
  else:
   return "VOLSELLDECREASE",0,"TP_SHORT"
 return "NO_VOL",0,"NONE"

def junction_decision(df, pos):
 try:
  last20 = df.tail(20)
  high = last20['high'].max()
  low = last20['low'].min()
  rng = (high-low)/low*100
  if rng > 2.8:
   return None,None
  rs = rsi(df['close']).iloc[-1]
  close = df['close'].iloc[-1]
  ema20 = df['close'].ewm(span=20).mean().iloc[-1]
  if pos == "LONG":
   if rs > 58 and close > ema20:
    return "HOLD_BULL", f"HOLD LONG Box RSI {rs:.0f}"
   if rs < 48:
    return "EXIT_WARN", f"JUNCTION LONG Weak RSI {rs:.0f} Exit 50%"
  if pos == "SHORT":
   if rs < 42 and close < ema20:
    return "HOLD_BEAR", f"HOLD SHORT Box RSI {rs:.0f}"
  return None,None
 except:
  return None,None

def score_v8(df, ex):
 bull = 0
 bear = 0
 re = []
 fake = []
 try:
  ob_name, ob_pts = ob_c(df)
  if ob_pts > 0:
   if "BULL" in ob_name:
    bull += ob_pts
   else:
    bear += ob_pts
   re.append(ob_name)
  eq_name, eq_pts = eq_c(df)
  if eq_pts > 0:
   bull += eq_pts
   re.append(eq_name)
  tur_name, tur_pts = tur_c(df)
  if tur_pts > 0:
   if "LONG" in tur_name:
    bull += tur_pts
   else:
    bear += tur_pts
   re.append(tur_name)
  mss_name, mss_pts = mss_c(df)
  if mss_pts > 0:
   if "BULL" in mss_name:
    bull += mss_pts
   else:
    bear += mss_pts
   re.append(mss_name)
  pd_name, pd_pts = pd_c(df)
  re.append(pd_name)
  if "DISCOUNT" in pd_name:
   bull += pd_pts
  fvg_name, fvg_pts = fvg_c(df)
  if fvg_pts > 0:
   if "BULL" in fvg_name:
    bull += fvg_pts
   else:
    bear += fvg_pts
   re.append(fvg_name)
  liq_name, liq_pts = liq_sweep_c(df)
  if liq_pts > 0:
   if "LONG" in liq_name:
    bull += liq_pts
   else:
    bear += liq_pts
   re.append(liq_name)
  whale_name, whale_pts = whale_manip_c(df)
  if whale_pts < 0:
   fake.append(whale_name)
  else:
   re.append(whale_name)
  kz_name, kz_pts = kz_c()
  re.append(kz_name)
  bull += kz_pts
  bear += kz_pts
  bt = btc_t(ex)
  re.append(bt)
  if bt == "BTC_BULL":
   bull += 10
  if bt == "BTC_BEAR":
   bear += 10
  rs = rsi(df['close']).iloc[-1]
  if rs < 30:
   bull += 15
   re.append(f"RSI_{rs:.0f}_OS")
  if rs > 70:
   bear += 15
   re.append(f"RSI_{rs:.0f}_OB")
 except:
  pass
 return bull,bear,re,fake

def main():
 print(f"🚀 KILLER BOT START {datetime.utcnow()} UTC - {len(SYMBOLS)} coins")
 ex, exn = ge()
 ca = lc()
 tr = lt()
 now = datetime.utcnow()
 for sym in SYMBOLS:
  try:
   df = fs(ex, sym, "15m", 200)
   if df is None:
    print(f"⏭️ {sym} SKIP - No data")
    continue
   va = df['vol'].rolling(20).mean().iloc[-1]
   v5 = df['vol'].iloc[-5:].mean()
   if v5 < va*1.3:
    print(f"⏭️ {sym} BLOCKED - VOL low {v5:.2f} < {va*1.3:.2f} (1.3x avg)")
    continue
   bull,bear,re,fake = score_v8(df, ex)
   total = 50+max(bull,bear)
   print(f"📊 {sym} Score {total} Bull {bull} Bear {bear} Reasons: {re}")
   if total < MIN_SCORE:
    print(f"⏭️ {sym} BLOCKED - Score {total} < {MIN_SCORE}")
    continue
   if bull > bear:
    typ = "LONG"
    action = "BUY"
   elif bear > bull:
    typ = "SHORT"
    action = "SELL"
   else:
    print(f"⏭️ {sym} BLOCKED - No clear direction bull={bull} bear={bear}")
    continue
   try:
    price_now = df['close'].iloc[-1]
    low_24 = df['low'].tail(96).min()
    high_24 = df['high'].tail(96).max()
    low_4 = df['low'].tail(16).min()
    high_4 = df['high'].tail(16).max()
    rsi_now = rsi(df['close']).iloc[-1]
    premium_now = 0
    vol_now = df['vol'].iloc[-1]
    vol_avg = df['vol'].tail(20).mean()
    btc_trend = btc_t(ex)
    if btc_trend == "BTC_BULL":
        btc_trend_simple = "UP"
    elif btc_trend == "BTC_BEAR":
        btc_trend_simple = "DOWN"
    else:
        btc_trend_simple = "NEUTRAL"
    filter_result = check_all_filters(price_now, low_24, high_24, low_4, high_4, rsi_now, premium_now, vol_now, vol_avg, btc_trend_simple, typ)
    if isinstance(filter_result, tuple):
        blocked, reason = filter_result
    else:
        blocked = filter_result
        reason = "Blocked by premium/btc filter"
    if blocked:
        print(f"🛡️ FILTER BLOCK {sym} {typ}: {reason} Price {price_now:.5f} RSI {rsi_now:.0f}")
        continue
   except Exception as e:
    print(f"Filter err {e} for {sym}")
    continue
   if is_duplicate(sym, 30):
       print(f"⏭️ DUPLICATE BLOCK {sym} - sent <30min ago")
       continue
   if not filt(sym, typ):
    d = gc(sym)
    print(f"⏭️ {sym} BLOCKED - 24h change {d:.1f}% extreme")
    continue
   key = f"{sym}_{typ}"
   if key in ca:
    diff = now - ca[key]
    if diff < timedelta(hours=2):
     print(f"⏭️ {sym} {typ} BLOCKED - Cooldown {diff}")
     continue
   price = df['close'].iloc[-1]
   sl = price*0.97 if typ == "LONG" else price*1.03
   tp = price*1.06 if typ == "LONG" else price*0.94
   if len(fake) > 0:
    print(f"⏭️ {sym} BLOCKED - Fake whale {fake}")
    continue
   strength = "STRONG" if total < 80 else "MAX"
   reasons = ', '.join(re[:6])
   msg = f"{action} {sym} {typ} {strength} ({total}/100)\nPrice: {price:.5f}\nSL: {sl:.5f} TP: {tp:.5f}\nReasons: {reasons}\n{exn}"
   tg(msg)
   print(f"✅ PASSED & SENT {sym} {typ} {total}/100")

   if sym in ["KOMA/USDT:USDT", "GRASS/USDT:USDT"] and total >= 75:
       print(f"🤖 AUTO FIRING {sym} {typ} {total}")
       try:
           ok = auto_trade(sym, typ, sl, tp, total)
           if ok:
               tg(f"🤖 *AUTO EXECUTED*\n{sym} {typ} {total}/100\nEntry ${price:.5f} SL ${sl:.5f} TP ${tp:.5f}")
               print(f"💰 AUTO SUCCESS {sym}")
           else:
               print(f"❌ AUTO FAILED {sym} - check MEXC balance/leverage")
       except Exception as e:
           print(f"❌ Auto trade err {e}")

   ca[key] = now
   sc(ca)
   if key not in tr:
    tr[key] = {"entry": price, "type": typ, "time": now.isoformat()}
   st(tr)
  except Exception as e:
   print(f"❌ ERR {sym} {e}")
   time.sleep(1)

 # Check existing trades for HOLD/TP
 for key,data in list(tr.items()):
  try:
   sym = key.replace(f"_{data['type']}","")
   if sym not in SYMBOLS:
    for s in SYMBOLS:
     if s.split("/")[0] in key:
      sym = s
      break
   df = fs(ex, sym, "15m", 200)
   if df is None:
    continue
   typ = data.get("type","LONG")
   entry = data.get("entry",0)
   now_p = df['close'].iloc[-1]
   if typ == "LONG":
    pnl = (now_p-entry)/entry*100
   else:
    pnl = (entry-now_p)/entry*100
   v_name,_,v_dir = vol_profit_c(df, pnl)
   jv_key = f"VOL_{key}_{v_name}"
   if v_dir!= "NONE":
    if jv_key not in ca or (now - ca[jv_key]) > timedelta(hours=1):
     if v_dir == "HOLD_LONG":
      tg(f"HOLD {sym} LONG Vol UP PnL {pnl:.2f}% Keep HOLD Price {now_p:.5f}")
     if v_dir == "TP_LONG":
      tg(f"TAKE PROFIT {sym} LONG Vol DOWN PnL {pnl:.2f}% Secure 50% Price {now_p:.5f}")
     if v_dir == "HOLD_SHORT":
      tg(f"HOLD {sym} SHORT Vol UP PnL {pnl:.2f}% Keep HOLD")
     if v_dir == "TP_SHORT":
      tg(f"TAKE PROFIT {sym} SHORT Vol DOWN PnL {pnl:.2f}%")
     ca[jv_key] = now
     sc(ca)
   dec, j_msg = junction_decision(df, typ)
   if dec:
    j_key = f"JUNC_{key}"
    if j_key not in ca or (now - ca[j_key]) > timedelta(hours=1):
     full = f"{j_msg}\nCoin: {sym}\nEntry {entry:.5f} Now {now_p:.5f} PnL {pnl:.2f}%"
     tg(full)
     ca[j_key] = now
     sc(ca)
  except Exception as e:
   print(f"JUNC ERR {e}")
   continue
 print("🏁 SCAN COMPLETE")

if __name__ == "__main__":
 main()
