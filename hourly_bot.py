import requests
from datetime import datetime

TOKEN = "8916111832:AAGAUhBAZA9rJaeJHKnnOGy4H-qJwIbP-Ow"
CHAT_ID = "7738947953"

def send_tg(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": text}, timeout=15)
        print("Sent!")
    except Exception as e:
        print(e)

def get_data():
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr?symbol=KOMAUSDT", timeout=10).json()
        return float(r['lastPrice']), float(r['quoteVolume'])
    except Exception as e:
        print(f"Error getting price: {e}")
        return None, None

price, vol = get_data()
now = datetime.now().strftime("%d %b %H:%M")

if price:
    msg = f"✅ KOMA Bot LIVE\n{now}\nPrice: ${price}\nVol: ${int(vol/1000)}k\nFREE GitHub Bot Works!"
    send_tg(msg)
    print(msg)
else:
    print("Failed to get price")
