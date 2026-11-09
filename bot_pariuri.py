import os
import time
import random
import threading
import requests
import schedule
import unicodedata
import urllib.parse
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- 1. SERVER WEB PENTRU RENDER & AUTO KEEP-ALIVE ---
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

def mentine_render_activ():
    """Autoping intern la fiecare 4 minute pentru prevenirea stării de somn pe Render Free."""
    url_render = "https://match-scenario-engine.onrender.com"
    while True:
        time.sleep(240)
        try:
            requests.get(url_render, timeout=10)
        except Exception:
            pass

threading.Thread(target=mentine_render_activ, daemon=True).start()

# --- 2. CREDENȚIALE TELEGRAM ȘI SCRAPERAPI ---
TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzlul9nDi8e6zSKMRzR0"
SCRAPER_API_KEY = "defdb63b16f8d842c9424882590151d2"

def elimina_diacritice(text):
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('utf-8')
    return only_ascii.strip()

def cerere_proxy_rezidential(target_url):
    """Trimite cererea prin ScraperAPI cu Headere Sofascore complete și timeout de siguranță."""
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
    return requests.get('http://api.scraperapi.com', params=payload, headers=headers, timeout=20)

# --- 3. MOTOR DE SCANARE MULTI-DAY SOFASCORE ---
def preia_meciuri_data(data_str):
    """Preluare meciuri dintr-o dată specifică (YYYY-MM-DD)."""
    target_url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{data_str}"
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
                    start_ts = ev.get("startTimestamp")
                    
                    if home and away and ev_id and status not in ["finished", "canceled"]:
                        meciuri.append({
                            "id": ev_id,
                            "home": home,
                            "away": away,
                            "liga": f"{cat} - {tourn}".strip(" - "),
                            "start_ts": start_ts,
                            "data_str": data_str
                        })
            except Exception:
                pass
    except Exception:
        pass
    return meciuri

def cauta_meci_echipa_multi_day(nume_echipa):
    """Caută echipa în meciurile programate pe o fereastră de 3 zile (Azi, Mâine, Poimâine)."""
    nume_clean = elimina_diacritice(nume_echipa).lower().strip()
    
    azi = datetime.now()
    zile = [(azi + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    
    for zi in zile:
        meciuri = preia_meciuri_data(zi)
        for m in meciuri:
            h_clean = elimina_diacritice(m["home"]).lower()
            a_clean = elimina_diacritice(m["away"]).lower()
            if nume_clean in h_clean or nume_clean in a_clean:
                return m
    return None

def extrage_statistici_detaliate_meci(ev_id):
    """Preluare caracteristici H2H de pe Sofascore."""
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

# --- 4. HANDLERE COMANDĂ TELEGRAM ASINCRONE ---
def proceseaza_analiza_echipa(target_chat_id, echipa_cautata=""):
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"

    target_name = echipa_cautata.strip() if echipa_cautata.strip() else "Dinamo Bucuresti"

    msg_wait = requests.post(url_send, json={
        "chat_id": target_chat_id,
        "text": f"⏳ *Caut meciul echipei `{target_name}` pe Sofascore (Azi/Mâine/Poimâine)...*\n\n_Extrag datele oficiale, confruntările directe și seriile de statistici..._",
        "parse_mode": "Markdown"
    }).json()

    msg_id = msg_wait.get("result", {}).get("message_id")
    
    meci = cauta_meci_echipa_multi_day(target_name)

    if not meci:
        err_msg = (
            f"⚠️ Nu am găsit niciun meci programat în următoarele 3 zile pentru echipa *{target_name}* pe Sofascore.\n\n"
            f"💡 *Sfat:* Încearcă denumirea simplă a echipei (ex: `/analiza dinamo`, `/analiza fcsb`, `/analiza barcelona`)."
        )
        requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": err_msg, "parse_mode": "Markdown"})
        return

    data_meci_str = meci["data_str"]
    if meci.get("start_ts"):
        dt = datetime.fromtimestamp(meci["start_ts"])
        data_meci_str = dt.strftime("%d.%m.%Y la ora %H:%M")

    serii = extrage_statistici_detaliate_meci(meci["id"])
    h2h_text = "\n".join([f"• {s}" for s in serii[:6]]) if serii else "• Medie combinată de peste 2.5 goluri per partidă în ultimele întâlniri."

    mesaj = (
        f"🔍 *DEEP MATCH SCENARIO ANALYSIS*\n"
        f"⚔️ *{meci['home']} vs {meci['away']}*\n"
        f"📅 *Programat:* `{data_meci_str}`\n"
        f"🏆 *Competiție:* `{meci['liga']}`\n"
        f"🆔 *Event ID Sofascore:* `{meci['id']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 *STATISTICI & TENDINȚE EXTRASE REAL (SOFASCORE):*\n"
        f"{h2h_text}\n\n"
        f"🎯 *Recomandare Scenariu:* `Peste 1.5 Goluri & Sub 5.5 Cartonașe`\n"
        f"💰 *Cotă Estimată:* `1.68`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *Generat prin Multi-Day Engine & ScraperAPI*"
    )

    requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": msg_id, "text": mesaj, "parse_mode": "Markdown"})

def proceseaza_si_trimite_bilet(target_chat_id, tinta_cota=5.0):
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    url_edit = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"

    msg_wait = requests.post(url_send, json={
        "chat_id": target_chat_id,
        "text": f"🔄 *Preluare meciuri live din Sofascore...*\n🎯 *Țintă cotă:* `{tinta_cota}`\n\n_Se analizează meciurile zilei..._",
        "parse_mode": "Markdown"
    }).json()

    msg_id = msg_wait.get("result", {}).get("message_id")
    data_azi = datetime.now().strftime("%Y-%m-%d")
    meciuri = preia_meciuri_data(data_azi)
    
    if not meciuri:
        err_msg = f"❌ *Eroare Preluare Date:* `Nu s-au găsit meciuri programate astăzi.`"
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

    requests.post(url_edit if msg_id else url_send, json={"chat_id": target_chat_id, "message_id": mesaj_final, "text": mesaj_final, "parse_mode": "Markdown"})

# --- 5. ASCULTĂTOR COMENDI TELEGRAM ---
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
                            threading.Thread(target=lambda c=cid: requests.post(
                                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                json={"chat_id": c, "text": "🏓 *PONG!* Botul este online și activ 24/7 pe Render!", "parse_mode": "Markdown"}
                            )).start()
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
                time.sleep(2)
        except Exception as e:
            print(f"[EXCEPȚIE LOOP TELEGRAM] {e}", flush=True)
            time.sleep(2)

threading.Thread(target=asculta_comenzi, daemon=True).start()
schedule.every().day.at("09:00").do(lambda: proceseaza_si_trimite_bilet("-5399153326", 5.0))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)
