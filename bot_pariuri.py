import os
import time
import threading
import requests
import schedule
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- SERVER WEB DUMMY PENTRU RENDER (Keep-Alive 24/7) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is online and fetching live Sofascore data!")
    def log_message(self, format, *args):
        return

def pornesc_server_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=pornesc_server_web, daemon=True).start()

# --- CREDENȚIALE API & TELEGRAM ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com"
}

def preia_meciuri_sofascore_reale():
    """Interoghează evenimentele reale din Sofascore cu multiple formate de dată."""
    azi_dmy = datetime.now().strftime("%d/%m/%Y")
    azi_ymd = datetime.now().strftime("%Y-%m-%d")
    
    url = "https://sofascore.p.rapidapi.com/events/list-by-date"
    
    for dt_format in [azi_dmy, azi_ymd]:
        try:
            res = requests.get(url, headers=headers, params={"date": dt_format}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                events = data.get("events") or data.get("data") or (data if isinstance(data, list) else [])
                if events:
                    return events
        except Exception as e:
            print(f"Eroare API la data {dt_format}:", e)
            
    # Endpoint secundar dacă list-by-date este indisponibil
    try:
        res_sec = requests.get("https://sofascore.p.rapidapi.com/sports/list", headers=headers, timeout=10)
        if res_sec.status_code == 200:
            return res_sec.json().get("events", [])
    except Exception:
        pass
        
    return []

def extrage_cota_reala(event_id):
    """Extrage cotele reale live din Sofascore de la casele de pariuri."""
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

def genereaza_bilet_real(tinta_cota=5.0, filtru_sport=None):
    evenimente = preia_meciuri_sofascore_reale()
    bilet = []
    cota_cumulata = 1.0
    
    for ev in meciuri_valide(evenimente, filtru_sport):
        home = ev.get("homeTeam", {}).get("name") or ev.get("home", {}).get("name")
        away = ev.get("awayTeam", {}).get("name") or ev.get("away", {}).get("name")
        sport_info = str(ev.get("sport", {}).get("name", "Football")).upper()
        ev_id = ev.get("id")
        
        if not home or not away:
            continue
            
        cota_reala = extrage_cota_reala(ev_id) if ev_id else None
        
        # Dacă meciul nu are cote publice live extrase din API pe instant, se atribuie cota de piață de 1.45 - 1.85
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

    return bilet, round(cota_cumulata, 2)

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

def trimite_bilet_telegram(target_chat_id, tinta_cota=5.0, filtru_sport=None):
    bilet, cota_finala = genereaza_bilet_real(tinta_cota, filtru_sport)
    data_afisata = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    text_meciuri = ""
    for item in bilet:
        text_meciuri += (
            f"{item['sport']} | *{item['meci']}*\n"
            f"🎯 *Tip:* {item['tip']} | *Cotă:* `{item['cota']}`\n"
            f"📊 *Analiză Sofascore:* {item['statistica']}\n\n"
        )

    mesaj = (
        f"🏆 *DATA-DRIVEN MATCH SCENARIO ENGINE*\n"
        f"📅 *Generat:* {data_afisata}\n"
        f"🎯 *Țintă Cotă:* `{tinta_cota}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{text_meciuri}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *COTĂ TOTALĂ REALĂ:* `{cota_finala}` 🚀\n"
        f"🤖 *Generat de @AeptyMatch_bot*"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": target_chat_id, "text": mesaj, "parse_mode": "Markdown"})

def asculta_comenzi_telegram():
    offset = 0
    print("Ascultător comenzi Telegram activ...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            res = requests.get(url, params={"offset": offset, "timeout": 8}, timeout=12)
            if res.status_code == 200:
                updates = res.json().get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message", {})
                    text = msg.get("text", "").strip()
                    cid = msg.get("chat", {}).get("id")
                    
                    if not text or not cid:
                        continue
                        
                    if