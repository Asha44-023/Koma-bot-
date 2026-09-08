import ccxt, requests, os, numpy as np, pandas as pd, time

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

symbols = ["HEI/USDT", "LAB/USDT", "SIREN/USDT", "GRASS/USDT", "KOMA/USDT", "VELVET/USDT"]
exchanges = ["mexc", "kucoin"]

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"TG Error: {e}")

def rsi_calc(closes, period=14):
    delta = np.diff(closes)
    gain = np.where(delta>0, delta, 0)
    loss = np.where(delta<0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    if avg_loss == 0: return 70
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def ema_calc(closes, period):
    return pd.Series(closes).ewm(span=period).mean().iloc[-1]

send_telegram("⚡ *LOOPHOLE HUNTER STARTED*\nLooking for early entries, fake BOS, volume traps, W/M loopholes...\nNot strict - will hunt!")

for sym in symbols:
    for ex_name in exchanges:
        try:
            ex = getattr(ccxt, ex_name)()
            o15 = ex.fetch_ohlcv(sym, '15m', limit=100)
            o5 = ex.fetch_ohlcv(sym, '5m', limit=100)
            o1h = ex.fetch_ohlcv(sym, '1h', limit=100)
            o4h = ex.fetch_ohlcv(sym, '4h', limit=100)
            if len(o15) < 50: continue

            c15 = [x[4] for x in o15]
            v15 = [x[5] for x in o15]
            price = c15[-1]
            rsi15 = rsi_calc(np.array(c15))
            rsi5 = rsi_calc(np.array([x[4] for x in o15[-20:]]))
            ema9 = ema_calc(c15, 9)
            ema21 = ema_calc(c15, 21)
            ema50 = ema_calc(c15, 50)

            # LOOPHOLE VOLUME - Even 0.8x is loophole
            avg_vol = np.mean(v15[-20:])
            vol_spike = v15[-1] / avg_vol if avg_vol>0 else 1
            vol_trend = "INCREASING" if np.mean(v15[-5:]) > np.mean(v15[-10:-5]) else "DECREASING"
            vol_loophole = vol_spike >= 0.8 # Loophole: even low volume can pump

            # LOOPHOLE BOS - 80% close to BOS counts
            high_20 = max(c15[-20:-1])
            low_20 = min(c15[-20:-1])
            bos_up_real = price > high_20
            bos_down_real = price < low_20
            bos_up_loophole = price > high_20 * 0.995 # 99.5% = loophole BOS
            bos_down_loophole = price < low_20 * 1.005

            # LOOPHOLE PATTERNS - Micro W/M
            w_pat = c15[-1] > c15[-2] and c15[-2] < c15[-3]
            m_pat = c15[-1] < c15[-2] and c15[-2] > c15[-3]
            # Double bottom loophole - 2% diff still counts
            double_bottom_loophole = abs(c15[-2] - c15[-4]) / abs(c15[-2]) < 0.02 and c15[-2] < c15[-3]
            double_top_loophole = abs(c15[-2] - c15[-4]) / c15[-2] < 0.02 and c15[-2] > c15[-3]

            # 4H 1H
            t4h = "UP" if o4h[-1][4] > o4h[-20][4] else "DOWN"
            s1h = "BOS UP" if o1h[-1][4] > max([x[4] for x in o1h[-20:-1]]) else "BOS DOWN" if o1h[-1][4] < min([x[4] for x in o1h[-20:-1]]) else "RANGE"

            # ATR
            atr = np.mean([abs(o15[i][2]-o15[i][3]) for i in range(-14, 0)])
            if atr == 0: atr = price * 0.01
            sl_l = price - atr*1.5
            tp1_l, tp2_l, tp3_l = price + atr*1.2, price + atr*2.5, price + atr*4
            sl_s = price + atr*1.5
            tp1_s, tp2_s, tp3_s = price - atr*1.2, price - atr*2.5, price - atr*4

            # --- LOOPHOLE LOGIC - NOT STRICT ---
            loophole_score = 0
            if bos_up_loophole: loophole_score += 1
            if ema9 > ema21: loophole_score += 1
            if rsi15 > 30: loophole_score += 1
            if vol_loophole: loophole_score += 1
            if w_pat or double_bottom_loophole: loophole_score += 1

            loophole_score_short = 0
            if bos_down_loophole: loophole_score_short += 1
            if ema9 < ema21: loophole_score_short += 1
            if rsi15 < 70: loophole_score_short += 1
            if vol_loophole: loophole_score_short += 1
            if m_pat or double_top_loophole: loophole_score_short += 1

            # BUY LOOPHOLE - Need 3/5 only!
            if loophole_score >= 3:
                msg = f"🟢 *LOOPHOLE BUY {sym}* [{ex_name.upper()}] Score {loophole_score}/5\n\n*ENTRY:* ${price:.5f} (5M/15M)\n*1H:* {s1h} | *4H:* {t4h}\n\n*LOOPHOLE CHECK:*\nRSI: {rsi15:.1f} (Loophole: >30) {'✅' if rsi15>30 else '❌'}\nEMA: 9={ema9:.5f} > 21={ema21:.5f}? {'✅' if ema9>ema21 else '❌'} 50={ema50:.5f}\nBOS: {'REAL BOS UP' if bos_up_real else 'LOOPHOLE BOS UP (99.5%)' if bos_up_loophole else 'NO BOS'} {'✅' if bos_up_loophole else '❌'}\nHigh20: ${high_20:.5f}\nVOLUME: x{vol_spike:.2f} {vol_trend} (Loophole >=0.8) {'✅' if vol_loophole else '❌'}\nPATTERN: W={w_pat} DB-Loophole={double_bottom_loophole} {'✅' if w_pat or double_bottom_loophole else '❌'}\n\n*MATH:*\nSL: ${sl_l:.5f} (-{((price-sl_l)/price)*100:.2f}%)\nTP1: ${tp1_l:.5f} (+{((tp1_l-price)/price)*100:.2f}%)\nTP2: ${tp2_l:.5f} (+{((tp2_l-price)/price)*100:.2f}%)\nTP3: ${tp3_l:.5f} (+{((tp3_l-price)/price)*100:.2f}%)"
                send_telegram(msg)
                break

            elif loophole_score_short >= 3:
                msg = f"🔴 *LOOPHOLE SELL {sym}* [{ex_name.upper()}] Score {loophole_score_short}/5\n\n*ENTRY:* ${price:.5f} (5M/15M)\n*1H:* {s1h} | *4H:* {t4h}\n\n*LOOPHOLE CHECK:*\nRSI: {rsi15:.1f} (Loophole: <70) {'✅' if rsi15<70 else '❌'}\nEMA: 9={ema9:.5f} < 21={ema21:.5f}? {'✅' if ema9<ema21 else '❌'} 50={ema50:.5f}\nBOS: {'REAL BOS DOWN' if bos_down_real else 'LOOPHOLE BOS DOWN (100.5%)' if bos_down_loophole else 'NO BOS'} {'✅' if bos_down_loophole else '❌'}\nLow20: ${low_20:.5f}\nVOLUME: x{vol_spike:.2f} {vol_trend} (Loophole >=0.8) {'✅' if vol_loophole else '❌'}\nPATTERN: M={m_pat} DT-Loophole={double_top_loophole} {'✅' if m_pat or double_top_loophole else '❌'}\n\n*MATH:*\nSL: ${sl_s:.5f} (+{((sl_s-price)/price)*100:.2f}%)\nTP1: ${tp1_s:.5f} (-{((price-tp1_s)/price)*100:.2f}%)\nTP2: ${tp2_s:.5f}\nTP3: ${tp3_s:.5f}"
                send_telegram(msg)
                break

            else:
                msg = f"⚪ *NO TRADE {sym}* [{ex_name.upper()}] Score L:{loophole_score}/5 S:{loophole_score_short}/5\n\nPrice: ${price:.5f} | RSI: {rsi15:.1f} | EMA9 {'>' if ema9>ema21 else '<'} EMA21\nBOS: {'UP' if bos_up_real else 'DOWN' if bos_down_real else 'No'} (High ${high_20:.5f} Low ${low_20:.5f})\nLoophole BOS: Up={bos_up_loophole} Down={bos_down_loophole}\nVol: x{vol_spike:.2f} {vol_trend} | Pattern: W={w_pat} M={m_pat} DB={double_bottom_loophole} DT={double_top_loophole}\n1H:{s1h} 4H:{t4h}\n\nPotential: SL Long ${sl_l:.5f} TP1 ${tp1_l:.5f} | SL Short ${sl_s:.5f} TP1 ${tp1_s:.5f}"
                send_telegram(msg)
                break

        except Exception as e:
            print(f"Err {sym} {ex_name}: {e}")
            continue
    time.sleep(1)

send_telegram("✅ Loophole Scan Done - Next in 15min")
