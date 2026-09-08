import requests, os
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

print(f"DEBUG TOKEN exists: {bool(BOT_TOKEN)}")
print(f"DEBUG CHAT_ID: {CHAT_ID}")

# Test 1: Check bot is valid
try:
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
    print(f"getMe status: {r.status_code} {r.text}")
except Exception as e:
    print(f"getMe error: {e}")

# Test 2: Try send and show REAL Telegram answer
try:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": "✅ BOSS TEST! If you see this, Telegram is FIXED! Bot will now send signals every 15 min!"}
    r = requests.post(url, data=data, timeout=10)
    print(f"SEND status: {r.status_code}")
    print(f"SEND response: {r.text}")
    if r.status_code == 200:
        print("SENT SUCCESS!")
    else:
        print("FAILED - Check CHAT_ID / BOT_TOKEN!")
except Exception as e:
    print(f"Send error: {e}")
