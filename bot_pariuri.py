import os
import time
import threading
import requests
import schedule
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- 1. SERVER WEB DUMMY PENTRU RENDER (Port Binding 24/7) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Engine is live and listening!")

    def log_message(self, format, *args):
        return

def pornesc_server_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=pornesc_server_web, daemon=True).start()

# --- 2. CREDENȚIALE TELEGRAM & SOFASCORE ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com"
}

def preia_meciuri_sofascore_reale():
    """Interoghează evenimentele reale din Sofascore cu datele curente."""
    azi_ymd = datetime.now().strftime("%Y-%m-%d")
    azi_dmy = datetime.now().strftime("%d/%m/%Y")
    
    url = "https://sofascore.p.rapidapi.com/events/list-by-date"
    
    for dt in [azi_ymd, azi_dmy]:
        try:
            res = requests.get(url, headers=headers, params={"date": dt}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                events = data.get("events") or data.get("data") or (data if isinstance(data, list) else [])
                if events:
                    return events
        except Exception as e:
            print(f"Eroare API la data {dt}:", e)
            
    return []

def extrage_cota_reala(event_id):
    """Extrage cotele reale live din Sofascore."""
    url = "https://sofascore.p.rapidapi.com/events/odds"
    try:
        res = requests.get(url, headers=headers, params={"eventId": event_id}, timeout=6)
        if res.status_code == 200:
            markets = res.json().get("markets", [])
            for m in markets:
                choices = m.get("choices", [])
                for c in choices:
                    val = c.get("decimalValue") or c.get("initialDecimalValue")
                    if val and float(val) > 1.10:
                        return float(val)
    except Exception:
        pass
    return None

def meciuri_valide(evenimente, filtru_sport):
    valide = []
    for ev in evenimente:
        if not isinstance(ev, dict):
            continue
        s = str(ev.get("sport", {}).get("name", "")).lower()
        if filtru_sport and filtru_sport not in s:
            continue
        valide.append(ev)
    return valide

def genereaza_bilet_real(tinta_cota=5.0, filtru_sport=None):
    evenimente = preia_meciuri_sofascore_reale()
    bilet = []
    cota_cumulata = 1.0
    
    valide = meciuri_valide(evenimente, filtru_sport)
    
    for ev in valide: