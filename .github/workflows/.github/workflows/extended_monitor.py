import requests
import json
import time
from datetime import datetime, timedelta

# ==========================================
# KONFIGURASI
# ==========================================
TELEGRAM_TOKEN = "9042449612:AAEd-XLtPPX7IKqkYIaAB-L-Vt71zAg5AXI"  # Ganti dengan token baru Anda
TELEGRAM_CHAT_ID = "8427903806"

# Koordinat Target
DAMMAM = {"lat": 26.3431487, "lon": 50.0950294, "name": "Al Shu'lah, Dammam"}
BAHRAIN = {"lat": 26.0667, "lon": 50.5577, "name": "Manama, Bahrain"}

# Bounding box untuk OpenSky API (Dammam + Bahrain + sekitarnya)
BOUNDING_BOX = {
    "lamin": 25.5,  # Selatan
    "lomin": 49.5,  # Barat
    "lamax": 26.8,  # Utara
    "lomax": 51.0   # Timur
}

# Kata kunci darurat
ARABIC_KEYWORDS = ["الدمام", "البحرين", "الشرقية", "إنذار", "انفجار", "زلزال", "صاروخ", "الشعلة", "نافر", "طائرة", "مسيرة"]

def send_telegram(message):
    """Kirim pesan ke Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error kirim Telegram: {e}")
        return False

def check_earthquakes():
    """Cek gempa untuk Dammam dan Bahrain"""
    alerts = []
    
    for location in [DAMMAM, BAHRAIN]:
        url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={location['lat']}&longitude={location['lon']}&maxradiuskm=50&orderby=time&limit=3"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            
            for eq in data.get('features', []):
                mag = eq['properties'].get('mag')
                if mag and mag >= 2.5:
                    place = eq['properties'].get('place', 'Tidak diketahui')
                    time_str = datetime.fromtimestamp(eq['properties']['time']/1000).strftime('%d-%m-%Y %H:%M')
                    alerts.append(f"🌍 *GEMPA - {location['name']}*\n📍 {place}\n⚡ Magnitudo: {mag}\n🕒 {time_str}")
        except Exception as e:
            print(f"Error cek gempa {location['name']}: {e}")
    
    return alerts

def check_news():
    """Cek berita darurat"""
    alerts = []
    rss_url = "https://www.alarabiya.net/.mrss/saudi-arabia"
    
    try:
        response = requests.get(rss_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            content = response.text
            for keyword in ARABIC_KEYWORDS:
                if keyword in content:
                    alerts.append(f"📰 *BERITA DARURAT TERDETEKSI*\nKata kunci '{keyword}' ditemukan di feed Al Arabiya")
                    break
    except Exception as e:
        print(f"Error cek berita: {e}")
    
    return alerts

def check_flights_opensky():
    """Cek anomali penerbangan via OpenSky Network"""
    alerts = []
    
    try:
        # Bounding box query
        url = f"https://opensky-network.org/api/states/all?lamin={BOUNDING_BOX['lamin']}&lomin={BOUNDING_BOX['lomin']}&lamax={BOUNDING_BOX['lamax']}&lomax={BOUNDING_BOX['lomax']}"
        response = requests.get(url, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            states = data.get('states', [])
            
            # Filter pesawat mencurigakan
            suspicious_flights = []
            military_callsigns = []
            
            for aircraft in states[:100]:  # Limit 100 pesawat
                icao24 = aircraft[0]  # ICAO address
                callsign = aircraft[1].strip() if aircraft[1] else ""
                altitude = aircraft[7]  # Geometric altitude in meters
                velocity = aircraft[9]  # Velocity in m/s
                vertical_rate = aircraft[11]  # Vertical rate
                
                # Deteksi pesawat tanpa callsign (mencurigakan)
                if not callsign and altitude and altitude < 3000:  # < 10000 ft
                    suspicious_flights.append({
                        "icao": icao24,
                        "altitude": altitude,
                        "velocity": velocity
                    })
                
                # Deteksi callsign militer (AWACS, Tanker, dll)
                military_patterns = ['RCH', 'RCHD', 'EVAC', 'CNV', 'ARMY', 'NAVY', 'USAF', 'RAAF', 'SAAF']
                if any(pattern in callsign.upper() for pattern in military_patterns):
                    military_callsigns.append({
                        "callsign": callsign,
                        "icao": icao24,
                        "altitude": altitude
                    })
            
            # Buat alert jika ada anomali
            if len(suspicious_flights) > 5:
                alerts.append(f"✈️ *ANOMALI PENERBANGAN*\nDitemukan {len(suspicious_flights)} pesawat tanpa callsign di altitude rendah (<3000m)\n⚠️ Potensi drone/UAV atau penerbangan tidak terdaftar")
            
            if military_callsigns:
                callsign_list = ", ".join([f['callsign'] for f in military_callsigns[:5]])
                alerts.append(f"🛩️ *PESAWAT MILITER TERDETEKSI*\nCallsign: {callsign_list}\nJumlah: {len(military_callsigns)} pesawat")
        
    except Exception as e:
        print(f"Error cek OpenSky: {e}")
    
    return alerts

def check_notam():
    """Cek NOTAM untuk drone/UAV (simulasi via berita)"""
    alerts = []
    
    # Cek NOTAM dari sumber publik (simulasi - bisa diganti dengan API NOTAM resmi)
    notam_keywords = ["drone", "UAV", "unmanned", "RPAS", "NOTAM", "restricted airspace"]
    
    # Cek feed berita untuk NOTAM-related news
    try:
        rss_url = "https://www.alarabiya.net/.mrss/saudi-arabia"
        response = requests.get(rss_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if response.status_code == 200:
            content = response.text.lower()
            for keyword in notam_keywords:
                if keyword in content:
                    alerts.append(f"⚠️ *NOTAM/DRONE ALERT*\nKata kunci '{keyword}' terdeteksi di feed berita\n🔍 Kemungkinan ada pembatasan ruang udara atau aktivitas drone")
                    break
    except Exception as e:
        print(f"Error cek NOTAM: {e}")
    
    return alerts

def main():
    print(f"=== Extended Monitor Started: {datetime.now()} ===")
    
    all_alerts = []
    
    # 1. Cek gempa
    print("Cek gempa...")
    all_alerts.extend(check_earthquakes())
    
    # 2. Cek berita
    print("Cek berita...")
    all_alerts.extend(check_news())
    
    # 3. Cek penerbangan
    print("Cek penerbangan...")
    all_alerts.extend(check_flights_opensky())
    
    # 4. Cek NOTAM
    print("Cek NOTAM...")
    all_alerts.extend(check_notam())
    
    # Kirim alert jika ada
    if all_alerts:
        report = "🚨 *EXTENDED ALERT - DAMMAM & BAHRAIN*\n\n"
        report += "\n\n".join(all_alerts)
        report += f"\n\n🕒 {datetime.now().strftime('%d-%m-%Y %H:%M WIB')}"
        
        if send_telegram(report):
            print("✅ Alert terkirim!")
        else:
            print("❌ Gagal kirim alert")
    else:
        print("✅ Aman. Tidak ada insiden terdeteksi.")
    
    print(f"=== Extended Monitor Finished: {datetime.now()} ===")

if __name__ == "__main__":
    main()
