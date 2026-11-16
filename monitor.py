import requests
import feedparser
import json
import os
import hashlib
from datetime import datetime, timezone, timedelta

# ==========================================
# KONFIGURASI
# ==========================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

TARGET_LAT = 26.3431487
TARGET_LON = 50.0950294
RADIUS_KM = 30

# Kata kunci darurat dalam bahasa Arab
ARABIC_KEYWORDS = ["الدمام", "الشرقية", "إنذار", "انفجار", "زلزال", "صاروخ", "الشعلة", "نافر", "دفاع مدني"]

# File state untuk hindari duplikat
STATE_FILE = "sent_alerts.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"sent_hashes": [], "last_run": None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def send_telegram(message):
    # DEBUG: Tampilkan apakah token & chat_id terbaca
    if not TELEGRAM_TOKEN:
        print("❌ ERROR: TELEGRAM_TOKEN kosong! Secrets belum di-set.")
        return False
    if not TELEGRAM_CHAT_ID:
        print("❌ ERROR: TELEGRAM_CHAT_ID kosong! Secrets belum di-set.")
        return False
    
    print(f"🔧 Debug: Token length = {len(TELEGRAM_TOKEN)}, Chat ID = {TELEGRAM_CHAT_ID}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🚨 *ALERT OSINT - DAMMAM*\n\n{message}",
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=data, timeout=10)
        response_text = r.text
        print(f"📡 Telegram response: {r.status_code} - {response_text}")
        if r.status_code == 200:
            print("✅ Alert terkirim sukses!")
            return True
        else:
            print(f"❌ Telegram API error: {response_text}")
            return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False
        
# ==========================================
# 1. CEK GEMPA BUMI (USGS)
# ==========================================
def check_earthquakes(state):
    print("\n🌍 [1/3] Mengecek gempa bumi...")
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={TARGET_LAT}&longitude={TARGET_LON}&maxradiuskm={RADIUS_KM}&orderby=time&limit=5"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        for eq in data.get('features', []):
            props = eq['properties']
            mag = props.get('mag')
            if mag and mag >= 2.5:
                title = props.get('place', 'Unknown')
                alert_text = f"{title} - M{mag}"
                if not is_duplicate(state, alert_text):
                    time_str = datetime.fromtimestamp(props['time']/1000, tz=timezone.utc).strftime('%d-%m-%Y %H:%M UTC')
                    msg = f"🌍 *GEMPA TERDETEKSI*\n📍 {title}\n⚡ Magnitudo: {mag}\n🕒 {time_str}\n⚠️ Radius: {RADIUS_KM}km dari Al Shu'lah"
                    send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# 2. CEK GOOGLE NEWS RSS (Chatter + Berita)
# ==========================================
def check_google_news(state):
    print("\n📰 [2/3] Mengecek Google News (Arab)...")
    # Query Google News dalam bahasa Arab untuk Dammam + kata kunci darurat
    query = "الدمام OR الشرقية OR الشعلة (انفجار OR إنذار OR صاروخ OR زلزال OR نافر OR دفاع_مدني)"
    url = f"https://news.google.com/rss/search?q={query}&hl=ar&gl=SA&ceid=SA:ar"
    try:
        feed = feedparser.parse(url)
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)
        
        for entry in feed.entries[:20]:  # Cek 20 berita terbaru
            published = entry.get('published_parsed')
            if published:
                pub_time = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_time < two_hours_ago:
                    continue  # Skip berita lama
            
            title = entry.get('title', '')
            link = entry.get('link', '')
            
            # Cek apakah ada kata kunci darurat
            has_keyword = any(kw in title for kw in ARABIC_KEYWORDS)
            if has_keyword:
                alert_text = f"GN:{title}"
                if not is_duplicate(state, alert_text):
                    msg = f"📰 *BERITA DARURAT (Google News)*\n📌 {title}\n🔗 {link}\n⏰ {entry.get('published', '')}"
                    send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# 3. CEK REDDIT r/saudiarabia
# ==========================================
def check_reddit(state):
    print("\n🔴 [3/3] Mengecek Reddit r/saudiarabia...")
    url = "https://www.reddit.com/r/saudiarabia/new.json?limit=15"
    headers = {'User-Agent': 'OSINT-Monitor/1.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        posts = data.get('data', {}).get('children', [])
        
        for post in posts:
            d = post.get('data', {})
            title = d.get('title', '')
            selftext = d.get('selftext', '')
            combined = f"{title} {selftext}"
            
            # Cek kata kunci Arab atau "Dammam"/"Eastern"
            has_keyword = any(kw in combined for kw in ARABIC_KEYWORDS) or \
                         any(kw.lower() in combined.lower() for kw in ['dammam', 'eastern province', 'al shu'])
            
            if has_keyword:
                alert_text = f"RD:{title}"
                if not is_duplicate(state, alert_text):
                    link = f"https://reddit.com{d.get('permalink', '')}"
                    msg = f"🔴 *REDDIT ALERT*\n📌 {title}\n🔗 {link}\n💬 Score: {d.get('score', 0)}"
                    send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# MAIN
# ==========================================
def main():
    print(f"=== OSINT Monitor Start: {datetime.now(timezone.utc)} ===")
    state = load_state()
    
    check_earthquakes(state)
    check_google_news(state)
    check_reddit(state)
    
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    
    print(f"\n=== Monitor End ===")
    print(f"Total alerts sent this run tracked in state.")
    
    # Kirim status heartbeat ke Telegram
    send_telegram(f"✅ *LAPORAN RUTIN*\n🕒 Waktu: {datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M UTC')}\n🌍 Gempa: Aman\n📰 Berita: Aman\n🔴 Reddit: Aman\n\nSistem OSINT Dammam aktif & memantau.")

if __name__ == "__main__":
    main()
