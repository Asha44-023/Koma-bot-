import os, requests
from datetime import datetime
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
def send_tg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text}, timeout=15)
def get_data():
    try:
        r = requests.get("https://api.mexc.com/api/v3/ticker/24hr?symbol=KOMAUSDT", timeout=10).json()
        return float(r['lastPrice']), float(r['quoteVolume'])
    except:
        return None, None
price, vol = get_data()
now = datetime.now().strftime("%d %b %H:%M")
if price:
    msg = f"KOMA LIVE\n{now}\nPrice: ${price}\nVol: ${int(vol/1000)}k"
    send_tg(msg)
