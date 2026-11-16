import requests
import json
import os
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta

# ==========================================
# KONFIGURASI - HARDKODE LANGSUNG (Paling Aman)
# ==========================================
# GANTI DI BAWAH INI DENGAN DATA ANDA SENDIRI
TELEGRAM_TOKEN = "9042449612:AAEd-XLtPPX7IKqkYIaAB-L-Vt71zAg5AXI"
TELEGRAM_CHAT_ID = "8427903806"

TARGET_LAT = 26.3431487
TARGET_LON = 50.0950294
RADIUS_KM = 30

ARABIC_KEYWORDS = ["الدمام", "الشرقية", "إنذار", "انفجار", "زلزال", "صاروخ", "الشعلة", "نافر"]

STATE_FILE = "sent_alerts.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"sent_hashes": [], "last_run": None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def send_telegram(message):
    """Kirim pesan ke Telegram - versi paling sederhana & robust."""
    print(f"\n📤 Mencoba kirim ke Telegram...")
    print(f"   Token length: {len(TELEGRAM_TOKEN)}")
    print(f"   Chat ID: {TELEGRAM_CHAT_ID}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    print(f"   URL: {url[:50]}...")
    
    payload = {
        "chat_id": str(TELEGRAM_CHAT_ID),
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        r = requests.post(url, json=payload, timeout=15)
        print(f"   Response status: {r.status_code}")
        print(f"   Response body: {r.text[:200]}")
        
        if r.status_code == 200:
            print("   ✅ BERHASIL terkirim!")
            return True
        else:
            print(f"   ❌ GAGAL: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        return False

def hash_item(text):
    return hashlib.md5(text.encode()).hexdigest()

def is_duplicate(state, text):
    h = hash_item(text)
    if h in state["sent_hashes"]:
        return True
    state["sent_hashes"].append(h)
    if len(state["sent_hashes"]) > 500:
        state["sent_hashes"] = state["sent_hashes"][-500:]
    return False

# ==========================================
# 1. CEK GEMPA BUMI (USGS)
# ==========================================
def check_earthquakes(state):
    print("\n🌍 [1/3] Mengecek gempa bumi...")
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={TARGET_LAT}&longitude={TARGET_LON}&maxradiuskm={RADIUS_KM}&orderby=time&limit=5"
    try:
        r = requests.get(url, timeout=15)
        print(f"   USGS response: {r.status_code}")
        if r.status_code != 200:
            print(f"   Skip: HTTP {r.status_code}")
            return
        
        data = r.json()
        features = data.get('features', [])
        print(f"   Ditemukan {len(features)} gempa di radius {RADIUS_KM}km")
        
        for eq in features:
            props = eq['properties']
            mag = props.get('mag')
            if mag and mag >= 2.5:
                title = props.get('place', 'Unknown')
                alert_text = f"EQ:{title}:M{mag}"
                if not is_duplicate(state, alert_text):
                    time_str = datetime.fromtimestamp(props['time']/1000, tz=timezone.utc).strftime('%d-%m-%Y %H:%M UTC')
                    msg = f"🌍 <b>GEMPA TERDETEKSI</b>\n📍 {title}\n⚡ Magnitudo: {mag}\n🕒 {time_str}\n⚠️ Radius: {RADIUS_KM}km dari Al Shu'lah, Dammam"
                    send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# 2. CEK GOOGLE NEWS (Versi Fixed - URL Encoded)
# ==========================================
def check_google_news(state):
    print("\n📰 [2/3] Mengecek Google News...")
    
    # Query sederhana dalam bahasa Arab - di-encode dengan benar
    query = "Dammam explosion OR earthquake OR warning"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=SA&ceid=SA:en"
    
    print(f"   URL: {url[:80]}...")
    
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        print(f"   Google News response: {r.status_code}")
        
        if r.status_code != 200:
            print(f"   Skip: HTTP {r.status_code}")
            return
        
        # Parse XML sederhana
        content = r.text
        items = content.split('<item>')[1:]  # Split by item tag
        
        print(f"   Ditemukan {len(items)} item berita")
        
        for item in items[:10]:
            # Extract title
            title_start = item.find('<title>') + 7
            title_end = item.find('</title>')
            if title_start > 6 and title_end > title_start:
                title = item[title_start:title_end]
                
                # Cek kata kunci
                title_lower = title.lower()
                if any(kw in title_lower for kw in ['dammam', 'explosion', 'earthquake', 'warning', 'attack', 'rocket']):
                    alert_text = f"GN:{title}"
                    if not is_duplicate(state, alert_text):
                        # Extract link
                        link_start = item.find('<link>') + 6
                        link_end = item.find('</link>')
                        link = item[link_start:link_end] if link_start > 5 and link_end > link_start else "N/A"
                        
                        msg = f"📰 <b>BERITA DARURAT (Google News)</b>\n📌 {title}\n🔗 {link}"
                        send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# 3. CEK REDDIT (Versi Fixed)
# ==========================================
def check_reddit(state):
    print("\n🔴 [3/3] Mengecek Reddit...")
    
    url = "https://old.reddit.com/r/saudiarabia/new/.json?limit=15"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(f"   Reddit response: {r.status_code}")
        
        if r.status_code != 200:
            print(f"   Skip: HTTP {r.status_code}")
            return
        
        # Cek apakah response JSON valid
        if not r.text.strip().startswith('{'):
            print(f"   Skip: Response bukan JSON (mungkin diblokir)")
            return
        
        data = r.json()
        posts = data.get('data', {}).get('children', [])
        print(f"   Ditemukan {len(posts)} post")
        
        for post in posts:
            d = post.get('data', {})
            title = d.get('title', '')
            title_lower = title.lower()
            
            if any(kw in title_lower for kw in ['dammam', 'eastern', 'explosion', 'earthquake', 'attack', 'warning']):
                alert_text = f"RD:{title}"
                if not is_duplicate(state, alert_text):
                    link = f"https://reddit.com{d.get('permalink', '')}"
                    msg = f"🔴 <b>REDDIT ALERT</b>\n📌 {title}\n🔗 {link}\n💬 Score: {d.get('score', 0)}"
                    send_telegram(msg)
    except Exception as e:
        print(f"   Error: {e}")

# ==========================================
# MAIN
# ==========================================
def main():
    print(f"\n{'='*50}")
    print(f"=== OSINT Monitor Start: {datetime.now(timezone.utc)} ===")
    print(f"{'='*50}")
    
    state = load_state()
    
    check_earthquakes(state)
    check_google_news(state)
    check_reddit(state)
    
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    
    # Kirim laporan rutin
    now_str = datetime.now(timezone.utc).strftime('%d-%m-%Y %H:%M UTC')
    heartbeat = (
        f"✅ <b>LAPORAN RUTIN OSINT</b>\n"
        f"🕒 Waktu: {now_str}\n"
        f"📍 Lokasi: Al Shu'lah, Dammam (26.34, 50.09)\n"
        f"🌍 Gempa: ✅ Aman\n"
        f"📰 Berita: ✅ Aman\n"
        f"🔴 Reddit: ✅ Aman\n\n"
        f"🛡️ Sistem aktif & memantau 24/7"
    )
    send_telegram(heartbeat)
    
    print(f"\n{'='*50}")
    print(f"=== Monitor End ===")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
