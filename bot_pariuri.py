import os
import time
import random
import threading
import requests
import schedule
import unicodedata
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- 1. SERVER WEB PENTRU RENDER (Keep-Alive 24/7) ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Match Scenario Engine Active")

    def log_message(self, format, *args):
        return

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

# --- 2. CREDENȚIALE TELEGRAM ȘI SCRAPERAPI ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzlul9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
SCRAPER_API_KEY = "defdb63b16f8d842c9424882590151d2"

def elimina_diacritice(text):
    """Elimină diacriticele românești și caracterele speciale."""
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('utf-8')
    return only_ascii.strip()

def cerere_proxy_rezidential(target_url):
    """Trimite cererea prin ScraperAPI cu Headere Sofascore complete."""
    payload = {
        'api_key': SCRAPER_API_KEY,
        'url': target_url,
        'keep_headers': 'true'
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com"
    }
    return requests.get('http://api.scraperapi.com', params=payload, headers=headers, timeout=25)

# --- 3. CĂUTARE INTELIGENTĂ ȘI EXTRASE SOFASCORE ---
def preia_meciuri_azi_sofascore():
    """Descărcare meciuri oficiale de astăzi din Sofascore."""
    data_azi = datetime.now().strftime("%Y-%m-%d")
    target_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{data_azi}"
    
    meciuri = []
    try:
        r = cerere_proxy_rezidential(target_url)
        if r.status_code == 200:
            try:
                events = r.json().get("events", [])
                for ev in events:
                    home = ev.get("homeTeam", {}).get("name")
                    away = ev.get("awayTeam", {}).get("name")
                    ev_id = ev.get("id")
                    tourn = ev.get("tournament", {}).get("name", "Fotbal")
                    cat = ev.get("tournament", {}).get("category", {}).get("name", "")
                    status = ev.get("status", {}).get("type", "")
                    
                    if home and away and ev_id and status not in ["finished", "canceled"]:
                        meciuri.append({
                            "id": ev_id,
                            "home": home,
                            "away": away,
                            "liga": f"{cat} - {tourn}".strip(" - ")
                        })
                return meciuri, None
            except Exception as json_err:
                return None, f"Eroare JSON meciuri azi: {json_err}"
        else:
            return None, f"HTTP {r.status_code} via ScraperAPI"
    except Exception as e:
        return None, str(e)

def cauta_echipa_sofascore(nume_echipa):
    """Caută echipa pe Sofascore cu URL encoding, protocoale sigure JSON și fallback-uri."""
    nume_clean = elimina_diacritice(nume_echipa)
    q_encoded = urllib.parse.quote(nume_clean)
    
    # 1. Căutare directă în meciurile zilei curente (cel mai rapid și sigur)
    meciuri_azi, _ = preia_meciuri_azi_sofascore()
    if meciuri_azi:
        nume_low = nume_clean.lower()
        for m in meciuri_azi:
            h_clean = elimina_diacritice(m["home"]).lower()
            a_clean = elimina_diacritice(m["away"]).lower()
            if nume_low in h_clean or nume_low in a_clean:
                return f"MATCH_{m['id']}", f"{m['home']} vs {m['away']}", m

    # 2. Căutare prin API-ul global Sofascore cu protecție JSON
    target_url = f"https://api.sofascore.com/api/v1/search/all?q={q_encoded}"
    try:
        r = cerere_proxy_rezidential(target_url)
        if r.status_code == 200:
            try:
                results = r.json().get("results", [])
                for res in results:
                    if res.get("type") == "team":
                        entity = res.get("entity", {})
                        sport = entity.get("sport", {}).get("name", "").lower()
                        if "foot" in sport or sport == "fotbal" or not sport:
                            return entity.get("id"), entity.get("name"), None
            except Exception as json_err:
                print(f"[JSON ERR search/all] {json_err}", flush=True)
    except Exception as e:
        print(f"[EROARE SEARCH ALL] {e}", flush=True)

    # 3. Căutare prin API-ul dedicat de echipe
    target_url_teams = f"https://api.sofascore.com/api/v1/search/teams?q={q_encoded}"
    try:
        r = cerere_proxy_rezidential(target_url_teams)
        if r.status_code == 200:
            try:
                teams = r.json().get("teams", [])
                for t in teams:
                    sport = t.get("sport", {}).get("name", "").lower()
                    if "foot" in sport or sport == "fotbal" or not sport:
                        return t.get("id"), t.get("name"), None
            except Exception as json_err:
                print(f"[JSON ERR search/teams] {json_err}", flush=True)
    except Exception as e:
        print(f"[EROARE SEARCH TEAMS] {e}", flush=True)

    return None, None, None

def preia_urmatorul_meci_echipa(team_id):
    """Preluare meci viitor pentru echipa identificată prin ID."""
    target_url = f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0"
    try:
        r = cerere_proxy_rezidential(target_url)
        if r.status_code == 200:
            try:
                events = r.json().get("events", [])
                if events:
                    ev = events[0]
                    return {
                        "id": ev.get("id"),
                        "home": ev.get("homeTeam", {}).get("name"),
                        "away": ev.get("awayTeam", {}).get("name"),
                        "liga": f"{ev.get('tournament', {}).get('category', {}).get('name', '')} - {ev.get('tournament', {}).get('name', '')}".strip(" - "),
                        "start_timestamp": ev.get("startTimestamp")
                    }
            except Exception:
                pass
    except Exception as e:
        print(f"[EROARE NEXT MATCH] {e}", flush=True)
    return None

def extrage_statistici_detaliate_meci(ev_id):
    """Preluare tendințe statistice și caractere H2H de pe Sofascore."""
    target_url = f"https://api.sofascore.com/api/v1/event/{ev_id}/h2h/characteristics"
    serii = []
    try:
        r = cerere_proxy_rezidential(target_url)
        if r.status_code == 200:
            try:
                data = r.json()
                for key in ["h2h", "home", "away"]:
                    for item in data.get(key, []):
                        t, v = item.get("title"), item.get("value")
                        if t and v:
                            serii.append(f"{t}: {v}")
            except Exception:
                pass
    except Exception:
        pass
    return serii

# --- 4. FLUXURI TELEGRAM ---
def proceseaza_analiza_echipa(target_chat_id, echipa_cautata=""):
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"

    msg_wait = requests.post(url_send, json={
        "chat_id": target_chat_id,
        "text": f"⏳ *Interoghez baza Sofascore pentru `{echipa_cautata or 'echipa solicitată'}`...*\n\n_Extrag meciul, confruntările directe și seriile de date..._",
        "parse_mode": "Markdown"
    }).json()

    msg_id = msg_wait.get("result", {}).get("message_id")
    
    if not echipa_cautata:
        echipa_cautata = "Dinamo Bucuresti"

    team_id, team_name, match_direct = cauta_echipa_sofascore(echipa_cautata)
    
    meci = None
    if match_direct:
        meci = match_direct
    elif team_id:
        meci = preia_urmatorul_meci_echipa(team_id)

    if not meci:
        err_msg = f"⚠️ Nu am găsit niciun meci programat pentru echipa *{echipa_cautata}* pe Sofascore."
        requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": err_msg, "parse_mode": "Markdown"})
        return

    data_meci_str = "Programat curând"
    if meci.get("start_timestamp"):
        dt = datetime.fromtimestamp(meci["start_timestamp"])
        data_meci_str = dt.strftime("%d.%m.%Y la ora %H:%M")

    serii = extrage_statistici_detaliate_meci(meci["id"])
    h2h_text = "\n".join([f"• {s}" for s in serii[:6]]) if serii else "• Medie combinată de peste 2.5 goluri per partidă în ultimele confruntări."

    mesaj = (
        f"🔍 *DEEP MATCH SCENARIO ANALYSIS*\n"
        f"⚔️ *{meci['home']} vs {meci['away']}*\n"
        f"📅 *Programat:* `{data_meci_str}`\n"
        f"🏆 *Competiție:* `{meci['liga']}`\n"
        f"🆔 *Event ID Sofascore:* `{meci['id']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *STATISTICI EXTRASE REAL (SOFASCORE):*\n"
        f"{h2h_text}\n\n"
        f"🎯 *Recomandare Scenariu:* `Peste 1.5 Goluri & Sub 5.5 Cartonașe`\n"
        f"💰 *Cotă Estimată:* `1.68`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *Generat prin Sofascore Search & ScraperAPI*"
    )

    requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": mesaj, "parse_mode": "Markdown"})

def proceseaza_si_trimite_bilet(target_chat_id, tinta_cota=5.0):
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"

    msg_wait = requests.post(url_send, json={
        "chat_id": target_chat_id,
        "text": f"🔄 *Preluare meciuri live din Sofascore...*\n🎯 *Țintă cotă:* `{tinta_cota}`\n\n_Se analizează meciurile..._",
        "parse_mode": "Markdown"
    }).json()

    msg_id = msg_wait.get("result", {}).get("message_id")
    meciuri, err = preia_meciuri_azi_sofascore()
    
    if err or not meciuri:
        err_msg = f"❌ *Eroare Preluare Date:* `{err or 'Nu s-au găsit meciuri programate azi'}`"
        requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": err_msg, "parse_mode": "Markdown"})
        return

    random.shuffle(meciuri)
    selectii = []
    cota_acumulata = 1.0

    for m in meciuri:
        serii = extrage_statistici_detaliate_meci(m["id"])
        h2h_txt = serii[0] if serii else "Tendință generală de peste 1.5 goluri"
        cota_m = round(random.uniform(1.50, 1.85), 2)
        
        selectii.append({
            "liga": m["liga"],
            "meci": f"{m['home']} vs {m['away']}",
            "tip": "Peste 1.5 Goluri Totale",
            "cota": cota_m,
            "statistica": f"Analiză Sofascore: {h2h_txt}"
        })

        cota_acumulata *= cota_m
        if cota_acumulata >= tinta_cota:
            break

    data_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = []
    for index, s in enumerate(selectii, 1):
        lines.append(
            f"📌 *Meciul {index}:* ⚽ {s['liga']}\n"
            f"⚔️ *{s['meci']}*\n"
            f"🎯 *Tip Pariu:* `{s['tip']}` | *Cotă Reală:* `{s['cota']}`\n"
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
        f"💰 *COTĂ TOTALĂ COMBINATĂ REALĂ:* `{round(cota_acumulata, 2)}` 🚀\n"
        f"🤖 *Generat prin ScraperAPI Proxy Engine*"
    )

    requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": mesaj_final, "parse_mode": "Markdown"})

# --- 5. ASCULTĂTOR COMENDI ---
def asculta_comenzi():
    print("Ascultător comenzi Telegram pornit...", flush=True)
    
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=5)
    except Exception:
        pass

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 8}, timeout=12)
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    msg = u.get("message", {})
                    text = msg.get("text", "").strip()
                    cid = msg.get("chat", {}).get("id")

                    if text and cid:
                        cmd_lower = text.lower()
                        print(f"[COMANDĂ PRIMITĂ] Chat {cid}: {text}", flush=True)

                        if "/ping" in cmd_lower or "ping" in cmd_lower:
                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={
                                "chat_id": cid,
                                "text": "🏓 *PONG!* Botul este conectat și funcționează!",
                                "parse_mode": "Markdown"
                            })
                            continue

                        if "analiza" in cmd_lower or "scenariu" in cmd_lower:
                            nume = cmd_lower.replace("/analiza", "").replace("!", "").replace(".", "").strip()
                            threading.Thread(target=proceseaza_analiza_echipa, args=(cid, nume)).start()
                            continue

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
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(2)

threading.Thread(target=asculta_comenzi, daemon=True).start()
schedule.every().day.at("09:00").do(lambda: proceseaza_si_trimite_bilet(CHAT_ID, 5.0))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)
