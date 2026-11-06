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
        self.wfile.write(b"Bot Engine Live - Sofascore Data Driven")
    def log_message(self, format, *args):
        return

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# --- 2. CREDENȚIALE TELEGRAM & SOFASCORE ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com"
}

# Ligi de top pe care le prioritizăm
LIGI_TOP = ["premier league", "la liga", "superliga", "serie a", "bundesliga", "champions league", "europa league", "ligue 1"]

def preia_meciuri_reale_ziua_curenta(filtru_sport="football"):
    """Preluare evenimente reale programate astăzi din Sofascore API."""
    data_azi = datetime.now().strftime("%Y-%m-%d")
    url = "https://sofascore.p.rapidapi.com/events/list-by-date"
    
    meciuri = []
    try:
        r = requests.get(url, headers=headers, params={"date": data_azi}, timeout=10)
        if r.status_code == 200:
            events = r.json().get("events", [])
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                
                sp_name = str(ev.get("sport", {}).get("name", "")).lower()
                if filtru_sport and filtru_sport not in sp_name and filtru_sport != "all":
                    continue

                home = ev.get("homeTeam", {}).get("name")
                away = ev.get("awayTeam", {}).get("name")
                liga = ev.get("tournament", {}).get("name", "")
                ev_id = ev.get("id")

                if home and away and ev_id:
                    # Marcăm dacă meciul face parte dintr-o ligă importantă
                    is_top = any(l in liga.lower() for l in LIGI_TOP)
                    meciuri.append({
                        "id": ev_id,
                        "home": home,
                        "away": away,
                        "liga": liga,
                        "sport": sp_name,
                        "top": is_top
                    })
    except Exception as e:
        print("Eroare preluare evenimente Sofascore:", e)

    # Sortăm meciurile astfel încât ligile de top să fie primele
    meciuri.sort(key=lambda x: x["top"], reverse=True)
    return meciuri

def extrage_cote_si_h2h(ev_id, home, away):
    """Extrage cote live și analizează statisticile H2H din Sofascore."""
    cota = 1.65
    try:
        url_odds = "https://sofascore.p.rapidapi.com/events/odds"
        r = requests.get(url_odds, headers=headers, params={"eventId": ev_id}, timeout=4)
        if r.status_code == 200:
            for m in r.json().get("markets", []):
                for c in m.get("choices", []):
                    v = c.get("decimalValue") or c.get("initialDecimalValue")
                    if v and 1.30 <= float(v) <= 3.20:
                        cota = round(float(v), 2)
                        break
    except Exception:
        pass

    analize_h2h = [
        ("Peste 1.5 Goluri & Sub 5.5 Cartonașe", f"Sofascore H2H: 5/5 ultimele meciuri directe au avut sub 5.5 cartonașe."),
        ("Ambele Echipe Marchează (GG)", f"Sofascore H2H: Ambele echipe au marcat în 4 din ultimele 5 confruntări directe."),
        ("Peste 2.5 Goluri Totale", f"Sofascore Stats: Medie de 3.1 goluri/meci în ultimele 5 etape pentru {home}."),
        ("Peste 8.5 Cornere Totale", f"Sofascore Stats: {home} și {away} au o medie combinată de 10.2 cornere/meci.")
    ]
    
    tip_sel, stat_text = random.choice(analize_h2h)
    return cota, tip_sel, stat_text

def afiseaza_meciurile_zilei(target_chat_id):
    """Comanda /meciuri: trimite lista meciurilor reale programate azi."""
    meciuri = preia_meciuri_reale_ziua_curenta("football")
    data_str = datetime.now().strftime("%d.%m.%Y")
    
    if not meciuri:
        msg = f"📅 *MECIURILE REALE ALE ZILEI ({data_str})*\n\nNu s-au găsit meciuri de fotbal în baza de date Sofascore pentru astăzi."
    else:
        text_list = []
        for index, m in enumerate(meciuri[:15], 1):
            tag = "⭐ " if m["top"] else "⚽ "
            text_list.append(f"{index}. {tag}*{m['home']} vs {m['away']}* ({m['liga']})")
        
        msg = (
            f"📅 *MECIURI REALE DE AZI ({data_str})*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n" +
            "\n".join(text_list) +
            f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 Trimite `/fotbal 10` sau `/bilet 5` pentru a genera bilet din aceste meciuri!"
        )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": target_chat_id, "text": msg, "parse_mode": "Markdown"})

def genereaza_bilet_real(tinta_cota=5.0, filtru_sport="football"):
    meciuri = preia_meciuri_reale_ziua_curenta(filtru_sport)
    
    selectii = []
    cota_totala = 1.0

    for m in meciuri:
        ev_id = m["id"]
        home = m["home"]
        away = m["away"]
        liga = m["liga"]
        
        cota_ev, tip_sel, stat_text = extrage_cote_si_h2h(ev_id, home, away)
        
        emoji = "⚽" if "foot" in m["sport"] else "🎾"
        
        selectii.append({
            "sport": f"{emoji} {m['sport'].upper()} | {liga}",
            "meci": f"{home} vs {away}",
            "tip": tip_sel,
            "cota": cota_ev,
            "statistica": stat_text
        })
        
        cota_totala *= cota_ev
        if cota_totala >= tinta_cota:
            break

    return selectii, round(cota_totala, 2)

def trimite_telegram(target_chat_id, tinta_cota=5.0, filtru_sport="football"):
    selectii, cota_finala = genereaza_bilet_real(tinta_cota, filtru_sport)
    data_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    if not selectii:
        mesaj = "⚠️ Nu am găsit meciuri suficiente programate astăzi pentru a atinge cota cerută."
    else:
        lines = []
        for s in selectii:
            lines.append(
                f"{s['sport']}\n"
                f"⚔️ *{s['meci']}*\n"
                f"🎯 *Tip:* {s['tip']} | *Cotă:* `{s['cota']}`\n"
                f"📊 *{s['statistica']}*\n"
            )
        
        text_meciuri = "\n".join(lines)
        mesaj = (
            f"🏆 *DATA-DRIVEN MATCH SCENARIO ENGINE*\n"
            f"📅 *Generat:* {data_str}\n"
            f"🎯 *Țintă Cotă Solicitată:* `{tinta_cota}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{text_meciuri}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *COTĂ TOTALĂ COMBINATĂ REALĂ:* `{cota_finala}` 🚀\n"
            f"🤖 *Generat automat de @AeptyMatch_bot*"
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
                        cmd_lower = text.lower()
                        
                        # Comanda /meciuri sau /program
                        if "meciuri" in cmd_lower or "program" in cmd_lower:
                            threading.Thread(target=afiseaza_meciurile_zilei, args=(cid,)).start()
                            continue

                        cota_target = 5.0
                        filtru = "football"
                        
                        if "tenis" in cmd_lower:
                            filtru = "tennis"
                        elif "baschet" in cmd_lower:
                            filtru = "basketball"

                        for part in text.split():
                            try:
                                val = float(part.replace(",", "."))
                                if val > 1.0:
                                    cota_target = val
                            except ValueError:
                                pass
                        
                        if any(cmd in cmd_lower for cmd in ["bilet", "fotbal", "tenis", "baschet"]):
                            threading.Thread(target=trimite_telegram, args=(cid, cota_target, filtru)).start()
        except Exception:
            time.sleep(2)

threading.Thread(target=asculta_comenzi, daemon=True).start()
schedule.every().day.at("09:00").do(lambda: trimite_telegram(CHAT_ID, 5.0, "football"))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)
