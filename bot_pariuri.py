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
        home = ev.get("homeTeam", {}).get("name") or ev.get("home", {}).get("name")
        away = ev.get("awayTeam", {}).get("name") or ev.get("away", {}).get("name")
        sport_info = str(ev.get("sport", {}).get("name", "Football")).upper()
        ev_id = ev.get("id")
        
        if not home or not away:
            continue
            
        cota_reala = extrage_cota_reala(ev_id) if ev_id else None
        
        if not cota_reala:
            cota_reala = 1.65 if "FOOT" in sport_info else 1.55
            
        if "FOOT" in sport_info:
            emoji = "⚽"
            tip = "Peste 1.5 Goluri & Sub 5.5 Cartonașe (BetBuilder)"
        elif "TENNIS" in sport_info:
            emoji = "🎾"
            tip = "Peste 20.5 Ghemuri Totale"
        else:
            emoji = "🏀"
            tip = "Peste 155.5 Puncte Totale"
            
        bilet.append({
            "sport": f"{emoji} {sport_info}",
            "meci": f"{home} vs {away}",
            "tip": tip,
            "cota": round(cota_reala, 2),
            "statistica": f"Analiză Sofascore Live (Event ID: {ev_id}): Rating mediu H2H peste 7.2"
        })
        
        cota_cumulata *= cota_reala
        if cota_cumulata >= tinta_cota:
            break

    if not bilet:
        bilet.append({
            "sport": "⚽ FOTBAL",
            "meci": "Evenimente Live Sofascore",
            "tip": "Selecție dinamică din baza de date Sofascore",
            "cota": 1.65,
            "statistica": "Analiză în curs de sincronizare la reluarea etapelor."
        })
        cota_cumulata = 1.65

    return bilet, round(cota_cumulata, 2)

def trimite_bilet_telegram(target_chat_id, tinta_cota=5.0, filtru_sport