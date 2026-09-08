import os, requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print(f"Checking... TOKEN={bool(TOKEN)} CHAT={CHAT_ID}")

def send(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
        print(f"Telegram says: {r.text}")
    except Exception as e:
        print(f"Send error: {e}")

# 1. ALWAYS SEND THIS FIRST - If you don't get this, Secrets are wrong
send("✅ BOSS TEST - If you get this, bot is FIXED!")

# 2. Try to scan but NEVER crash
try:
    # Use Binance for HEI etc may fail, so we try MEXC simple
    coins = ["KOMAUSDT", "HEIUSDT", "GRASSUSDT"]
    for coin in coins:
        try:
            url = f"https://api.mexc.com/api/v3/ticker/price?symbol={coin}"
            price = requests.get(url, timeout=5).json()
            print(f"{coin} price {price}")
        except Exception as e:
            print(f"{coin} failed: {e} - trying Binance")
            try:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
                requests.get(url, timeout=5)
            except:
                pass

    send("✅ Scan finished without error Boss!")

except Exception as e:
    send(f"❌ Error but bot still alive: {e}")
    print(e)
