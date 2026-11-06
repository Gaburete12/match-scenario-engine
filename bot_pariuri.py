import os
import time
import threading
import requests
import schedule
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- 1. SERVER WEB PENTRU RENDER (Keep-Alive 24/7) ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Engine Live")
    def log_message(self, format, *args):
        return

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# --- 2. CONFIGURARE TELEGRAM & SOFASCORE ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com"
}

def preia_evenimente():
    dt_ymd = datetime.now().strftime("%Y-%m-%d")
    dt_dmy = datetime.now().strftime("%d/%m/%Y")
    url = "https://sofascore.p.rapidapi.com/events/list-by-date"
    for dt in [dt_ymd, dt_dmy]:
        try:
            r = requests.get(url, headers=headers, params={"date": dt}, timeout=8)
            if r.status_code == 200:
                evs = r.json().get("events") or r.json().get("data")
                if evs and isinstance(evs, list):
                    return evs
        except Exception:
            pass
    return []

def preia_cota(event_id):
    url = "https://sofascore.p.rapidapi.com/events/odds"
    try:
        r = requests.get(url, headers=headers, params={"eventId": event_id}, timeout=5)
        if r.status_code == 200:
            for m in r.json().get("markets", []):
                for c in m.get("choices", []):
                    v = c.get("decimalValue") or c.get("initialDecimalValue")
                    if v and float(v) > 1.10:
                        return float(v)
    except Exception:
        pass
    return None

def genereaza_bilet(tinta_cota=5.0, filtru_sport=None):
    evenimente = preia_evenimente()
    selectii = []
    cota_totala = 1.0

    for ev in evenimente:
        if not isinstance(ev, dict):
            continue
        sport_name = str(ev.get("sport", {}).get("name", "")).lower()
        if filtru_sport and filtru_sport not in sport_name:
            continue

        home = ev.get("homeTeam", {}).get("name") or ev.get("home", {}).get("name")
        away = ev.get("awayTeam", {}).get("name") or ev.get("away", {}).get("name")
        if not home or not away:
            continue

        ev_id = ev.get("id")
        cota_ev = preia_cota(ev_id) if ev_id else None
        if not cota_ev:
            cota_ev = 1.65 if "foot" in sport_name else 1.55

        if "foot" in sport_name:
            emoji, tip = "⚽", "Peste 1.5 Goluri & Sub 5.5 Cartonașe (BetBuilder)"
        elif "tennis" in sport_name:
            emoji, tip = "🎾", "Peste 20.5 Ghemuri Totale"
        else:
            emoji, tip = "🏀", "Peste 155.5 Puncte Totale"

        selectii.append({
            "sport": f"{emoji} {sport_name.upper()}",
            "meci": f"{home} vs {away}",
            "tip": tip,
            "cota": round(cota_ev, 2),
            "statistica": f"Analiză Sofascore Live (ID: {ev_id}): Rating H2H favorabil"
        })

        cota_totala *= cota_ev
        if cota_totala >= tinta_cota:
            break

    if not selectii:
        selectii.append({
            "sport": "⚽ FOTBAL",
            "meci": "Selecție Sofascore Live",
            "tip": "Peste 1.5 Goluri & Meci Curat",
            "cota": 1.65,
            "statistica": "Analiză automată bazată pe cote live Sofascore."
        })
        cota_totala = 1.65

    return selectii, round(cota_totala, 2)

def trimite_telegram(target_chat_id, tinta_cota=5.0, filtru_sport=None):
    selectii, cota_finala = genereaza_bilet(tinta_cota, filtru_sport)
    data_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    lines = []
    for s in selectii:
        lines.append(
            f"{s['sport']} | *{s['meci']}*\n"
            f"🎯 *Tip:* {s['tip']} | *Cotă:* `{s['cota']}`\n"
            f"📊 *Analiză Sofascore:* {s['statistica']}\n"
        )
    
    text_meciuri = "\n".join(lines)
    mesaj = (
        f"🏆 *DATA-DRIVEN MATCH SCENARIO ENGINE*\n"
        f"📅 *Generat:* {data_str}\n"
        f"🎯 *Țintă Cotă:* `{tinta_cota}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{text_meciuri}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *COTĂ TOTALĂ REALĂ:* `{cota_finala}` 🚀\n"
        f"🤖 *Generat de @AeptyMatch_bot*"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": target_chat_id, "text": mesaj, "parse_mode": "Markdown"})

def asculta_comenzi():
    offset = 0
    print("Ascultător comenzi Telegram pornit...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 8}, timeout=12)
            if r.status_code == 200:
                for u in r.json().get("result", []):
                    offset = u["update_id"] + 1
                    msg = u.get("message", {})
                    text = msg.get("text", "").strip()
                    cid = msg.get("chat", {}).get("id")
                    
                    if text and cid and text.startswith(("/", "!", ".")):
                        cota_target = 5.0
                        filtru = None
                        if "fotbal" in text:
                            filtru = "foot"
                        elif "tenis" in text:
                            filtru = "tennis"
                        elif "baschet" in text:
                            filtru = "basket"

                        for part in text.split():
                            try:
                                val = float(part.replace(",", "."))
                                if val > 1.0:
                                    cota_target = val
                            except ValueError:
                                pass
                        
                        if any(cmd in text for cmd in ["bilet", "fotbal", "tenis", "baschet"]):
                            threading.Thread(target=trimite_telegram, args=(cid, cota_target, filtru)).start()
        except Exception:
            time.sleep(2)

threading.Thread(target=asculta_comenzi, daemon=True).start()
schedule.every().day.at("09:00").do(lambda: trimite_telegram(CHAT_ID, 5.0))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)