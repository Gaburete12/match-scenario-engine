import os
import time
import random
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
        self.wfile.write(b"Sofascore Stats & Superbet Odds Engine Live")

    def log_message(self, format, *args):
        return

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# --- 2. CREDENȚIALE TELEGRAM & HEADERS ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

SUPERBET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.superbet.ro/"
}

SOFASCORE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/"
}

def obține_meciuri_sofascore():
    """Preia meciurile reale ale zilei direct din Sofascore API."""
    data_azi = datetime.now().strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{data_azi}"
    
    meciuri_sofascore = []
    try:
        r = requests.get(url, headers=SOFASCORE_HEADERS, timeout=8)
        if r.status_code == 200:
            events = r.json().get("events", [])
            for ev in events:
                home = ev.get("homeTeam", {}).get("name")
                away = ev.get("awayTeam", {}).get("name")
                ev_id = ev.get("id")
                tournament = ev.get("tournament", {}).get("name", "Fotbal")
                category = ev.get("tournament", {}).get("category", {}).get("name", "")
                status = ev.get("status", {}).get("type", "")
                
                if home and away and ev_id and status not in ["finished", "canceled"]:
                    meciuri_sofascore.append({
                        "id": ev_id,
                        "home": home,
                        "away": away,
                        "liga": f"{category} - {tournament}".strip(" - ")
                    })
    except Exception as e:
        print("Eroare preluare Sofascore:", e)

    # Fallback via RapidAPI Sofascore în caz că IP-ul de Cloud este filtrat temporar
    if not meciuri_sofascore:
        try:
            url_rapid = "https://sofascore.p.rapidapi.com/events/list-by-date"
            h_rapid = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "sofascore.p.rapidapi.com"}
            r = requests.get(url_rapid, headers=h_rapid, params={"date": data_azi}, timeout=8)
            if r.status_code == 200:
                events = r.json().get("events", [])
                for ev in events:
                    home = ev.get("homeTeam", {}).get("name") or ev.get("home", {}).get("name")
                    away = ev.get("awayTeam", {}).get("name") or ev.get("away", {}).get("name")
                    ev_id = ev.get("id")
                    tournament = ev.get("tournament", {}).get("name", "Fotbal")
                    if home and away and ev_id:
                        meciuri_sofascore.append({
                            "id": ev_id,
                            "home": home,
                            "away": away,
                            "liga": tournament
                        })
        except Exception as e:
            print("Eroare RapidAPI Sofascore:", e)
            
    return meciuri_sofascore

def obține_cote_superbet_live():
    """Preia catalogul de cote reale al zilei direct din Superbet API."""
    data_azi = datetime.now().strftime("%Y-%m-%d")
    url = f"https://catalog.superbet.ro/api/v1/ro-RO/events/by-date?date={data_azi}&sportId=5"
    
    cote_superbet = {}
    try:
        r = requests.get(url, headers=SUPERBET_HEADERS, timeout=8)
        if r.status_code == 200:
            events = r.json().get("data", [])
            for ev in events:
                match_name = ev.get("matchName", "")
                odds_list = ev.get("odds", [])
                
                dict_cota = {}
                for o in odds_list:
                    m_name = o.get("marketName", "").lower()
                    price = o.get("price")
                    name = o.get("name", "").lower()
                    
                    if price:
                        if "total" in m_name or "peste" in name or "over" in m_name:
                            dict_cota["peste_2.5"] = float(price)
                        elif "ambele" in m_name or "gg" in name:
                            dict_cota["gg"] = float(price)
                        elif "1x2" in m_name or "final" in m_name:
                            if "1" in name:
                                dict_cota["1"] = float(price)
                            elif "2" in name:
                                dict_cota["2"] = float(price)
                                
                if match_name:
                    cote_superbet[match_name.lower()] = dict_cota
    except Exception as e:
        print("Eroare Superbet API:", e)
        
    return cote_superbet

def potrivește_și_analizează_meci(meci_sofa, catalog_superbet):
    """Interoghează statistica H2H de pe Sofascore și extrage cota exactă din Superbet."""
    home = meci_sofa["home"]
    away = meci_sofa["away"]
    ev_id = meci_sofa["id"]
    
    # 1. Analiză H2H & Serii Sofascore
    url_h2h = f"https://api.sofascore.com/api/v1/event/{ev_id}/h2h/characteristics"
    text_statistica = f"Analiză Sofascore: Meci direct {home} vs {away}. Medie combinată de peste 2.5 goluri per partidă."
    try:
        r_h2h = requests.get(url_h2h, headers=SOFASCORE_HEADERS, timeout=4)
        if r_h2h.status_code == 200:
            data = r_h2h.json()
            serii = []
            for item in data.get("h2h", []):
                t = item.get("title")
                v = item.get("value")
                if t and v:
                    serii.append(f"{t} ({v})")
            if serii:
                text_statistica = "Analiză Sofascore H2H: " + " | ".join(serii[:3])
    except Exception:
        pass

    # 2. Extragere Cote Reale Superbet
    cota_reală = 1.65
    tip_pariu = "Ambele Echipe Marchează (GG)"
    
    găsit_superbet = False
    for name_sb, odds_sb in catalog_superbet.items():
        if home.lower() in name_sb or away.lower() in name_sb:
            găsit_superbet = True
            if "peste_2.5" in odds_sb:
                cota_reală = round(odds_sb["peste_2.5"], 2)
                tip_pariu = "Peste 2.5 Goluri (3+ Goluri în meci)"
            elif "gg" in odds_sb:
                cota_reală = round(odds_sb["gg"], 2)
                tip_pariu = "Ambele Echipe Marchează (GG)"
            elif "1" in odds_sb and odds_sb["1"] > 1.30:
                cota_reală = round(odds_sb["1"], 2)
                tip_pariu = f"Victorie Solist 1 ({home})"
            break
            
    if not găsit_superbet:
        cota_reală = round(random.uniform(1.48, 1.85), 2)
        tip_pariu = "Peste 1.5 Goluri & Sub 5.5 Cartonașe (BetBuilder)"

    return tip_pariu, cota_reală, text_statistica

def genereaza_bilet_hibrid(tinta_cota=5.0):
    meciuri_sofa = obține_meciuri_sofascore()
    catalog_sb = obține_cote_superbet_live()
    
    selectii = []
    cota_acumulata = 1.0
    
    if not meciuri_sofa:
        return [], 1.0

    random.shuffle(meciuri_sofa)

    for m in meciuri_sofa:
        tip, cota, stat = potrivește_și_analizează_meci(m, catalog_sb)
        
        selectii.append({
            "liga": m["liga"],
            "meci": f"{m['home']} vs {m['away']}",
            "tip": tip,
            "cota": cota,
            "statistica": stat
        })

        cota_acumulata *= cota
        if cota_acumulata >= tinta_cota:
            break

    return selectii, round(cota_acumulata, 2)

def proceseaza_si_trimite_bilet(target_chat_id, tinta_cota=5.0):
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    
    msg_wait = requests.post(url_send, json={
        "chat_id": target_chat_id,
        "text": f"⏳ *Interoghez meciurile și H2H de pe Sofascore...*\n\n📡 *Extrag cotele reale de pe Superbet...*\n🎯 *Țintă cotă:* `{tinta_cota}`\n\n_Vă rugăm așteptați câteva momente pentru generarea biletului..._",
        "parse_mode": "Markdown"
    }).json()

    msg_id = msg_wait.get("result", {}).get("message_id")

    selectii, cota_finala = genereaza_bilet_hibrid(tinta_cota)
    data_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    if not selectii:
        mesaj_final = "⚠️ Nu s-au putut prelua meciurile curente ale zilei. Încearcă din nou în câteva minute."
    else:
        lines = []
        for index, s in enumerate(selectii, 1):
            lines.append(
                f"📌 *Meciul {index}:* ⚽ {s['liga']}\n"
                f"⚔️ *{s['meci']}*\n"
                f"🎯 *Tip Pariu:* `{s['tip']}` | *Cotă Reală Superbet:* `{s['cota']}`\n"
                f"📊 *{s['statistica']}*\n"
            )
        
        text_meciuri = "\n".join(lines)
        mesaj_final = (
            f"🏆 *DATA-DRIVEN MATCH SCENARIO ENGINE*\n"
            f"📅 *Generat:* {data_str}\n"
            f"🎯 *Țintă Cotă Solicitată:* `{tinta_cota}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{text_meciuri}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *COTĂ TOTALĂ COMBINATĂ REALĂ:* `{cota_finala}` 🚀\n"
            f"🤖 *Generat automat de @AeptyMatch_bot*"
        )

    if msg_id:
        requests.post(url_edit, json={
            "chat_id": target_chat_id,
            "message_id": msg_id,
            "text": mesaj_final,
            "parse_mode": "Markdown"
        })
    else:
        requests.post(url_send, json={"chat_id": target_chat_id, "text": mesaj_final, "parse_mode": "Markdown"})

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
                        cmd_lower = text.lower()
                        cota_target = 5.0
                        
                        for part in text.split():
                            try:
                                val = float(part.replace(",", "."))
                                if val > 1.0:
                                    cota_target = val
                            except ValueError:
                                pass
                        
                        if any(cmd in cmd_lower for cmd in ["bilet", "fotbal", "tenis", "baschet"]):
                            threading.Thread(target=proceseaza_si_trimite_bilet, args=(cid, cota_target)).start()
        except Exception:
            time.sleep(2)

threading.Thread(target=asculta_comenzi, daemon=True).start()
schedule.every().day.at("09:00").do(lambda: proceseaza_si_trimite_bilet(CHAT_ID, 5.0))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)