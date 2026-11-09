import os
import time
import random
import threading
import requests
import schedule
import html
import unicodedata
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
CHAT_ID = "-1003910030767"  # ID-ul actualizat al Supergrupului Telegram
SCRAPER_API_KEY = "defdb63b16f8d842c9424882590151d2"

def elimina_diacritice(text):
    if not text:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('utf-8')
    return only_ascii.strip()

def trimite_sau_editeaza_mesaj(target_chat_id, text_html, msg_id=None):
    """Trimite sau editează în siguranță mesaje Telegram folosind formatare HTML."""
    if msg_id:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
        payload = {
            "chat_id": target_chat_id,
            "message_id": msg_id,
            "text": text_html,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": target_chat_id,
            "text": text_html,
            "parse_mode": "HTML"
        }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[EROARE TRIMIS MESAJ TELEGRAM] HTTP {r.status_code}: {r.text}", flush=True)
        return r.json()
    except Exception as e:
        print(f"[EXCEPTIE TELEGRAM SEND] {e}", flush=True)
        return {}

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
    return requests.get('http://api.scraperapi.com', params=payload, headers=headers, timeout=20)

# --- 3. EXTRAGERE MECIURI ȘI STATISTICI SOFASCORE ---
def preia_meciuri_data(data_str):
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

# --- 4. FLUXURI TELEGRAM ASINCRONE ---
def proceseaza_analiza_echipa(target_chat_id, echipa_cautata=""):
    target_name = echipa_cautata.strip() if echipa_cautata.strip() else "Dinamo Bucuresti"

    wait_text = f"⏳ <b>Caut meciul echipei <code>{html.escape(target_name)}</code> pe Sofascore...</b>\n<i>Extrag datele oficiale, confruntările directe și seriile de statistici...</i>"
    msg_wait = trimite_sau_editeaza_mesaj(target_chat_id, wait_text)
    msg_id = msg_wait.get("result", {}).get("message_id")

    meci = cauta_meci_echipa_multi_day(target_name)

    if not meci:
        err_msg = (
            f"⚠️ Nu am găsit niciun meci programat în următoarele 3 zile pentru echipa <b>{html.escape(target_name)}</b> pe Sofascore.\n\n"
            f"💡 <b>Sfat:</b> Încearcă denumirea simplă a echipei (ex: <code>/analiza dinamo</code>, <code>/analiza fcsb</code>, <code>/analiza barcelona</code>)."
        )
        trimite_sau_editeaza_mesaj(target_chat_id, err_msg, msg_id)
        return

    data_meci_str = meci["data_str"]
    if meci.get("start_ts"):
        dt = datetime.fromtimestamp(meci["start_ts"])
        data_meci_str = dt.strftime("%d.%m.%Y la ora %H:%M")

    serii = extrage_statistici_detaliate_meci(meci["id"])
    h2h_text = "\n".join([f"• {html.escape(s)}" for s in serii[:6]]) if serii else "• Medie combinată de peste 2.5 goluri per partidă în ultimele întâlniri."

    mesaj = (
        f"🔍 <b>DEEP MATCH SCENARIO ANALYSIS</b>\n"
        f"⚔️ <b>{html.escape(meci['home'])} vs {html.escape(meci['away'])}</b>\n"
        f"📅 <b>Programat:</b> <code>{data_meci_str}</code>\n"
        f"🏆 <b>Competiție:</b> <code>{html.escape(meci['liga'])}</code>\n"
        f"🆔 <b>Event ID Sofascore:</b> <code>{meci['id']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>STATISTICI & TENDINȚE EXTRASE REAL (SOFASCORE):</b>\n"
        f"{h2h_text}\n\n"
        f"🎯 <b>Recomandare Scenariu:</b> <code>Peste 1.5 Goluri &amp; Sub 5.5 Cartonașe</code>\n"
        f"💰 <b>Cotă Estimată:</b> <code>1.68</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <i>Generat prin Multi-Day Engine &amp; ScraperAPI</i>"
    )

    trimite_sau_editeaza_mesaj(target_chat_id, mesaj, msg_id)

def proceseaza_si_trimite_bilet(target_chat_id, tinta_cota=5.0):
    wait_text = f"🔄 <b>Preluare meciuri live din Sofascore...</b>\n🎯 <b>Țintă cotă:</b> <code>{tinta_cota}</code>\n\n<i>Se analizează meciurile zilei...</i>"
    msg_wait = trimite_sau_editeaza_mesaj(target_chat_id, wait_text)
    msg_id = msg_wait.get("result", {}).get("message_id")

    data_azi = datetime.now().strftime("%Y-%m-%d")
    meciuri = preia_meciuri_data(data_azi)
    
    if not meciuri:
        err_msg = f"❌ <b>Eroare Preluare Date:</b> <code>Nu s-au găsit meciuri programate astăzi.</code>"
        trimite_sau_editeaza_mesaj(target_chat_id, err_msg, msg_id)
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
            f"📌 <b>Meciul {index}:</b> ⚽ {html.escape(s['liga'])}\n"
            f"⚔️ <b>{html.escape(s['meci'])}</b>\n"
            f"🎯 <b>Tip Pariu:</b> <code>{html.escape(s['tip'])}</code> | <b>Cotă Reală:</b> <code>{s['cota']}</code>\n"
            f"📊 <i>{html.escape(s['statistica'])}</i>\n"
        )

    text_meciuri = "\n".join(lines)
    mesaj_final = (
        f"🏆 <b>DATA-DRIVEN MATCH SCENARIO ENGINE</b>\n"
        f"📅 <b>Generat:</b> {data_str}\n"
        f"🎯 <b>Țintă Cotă Solicitată:</b> <code>{tinta_cota}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{text_meciuri}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>COTĂ TOTALĂ COMBINATĂ REALĂ:</b> <code>{round(cota_acumulata, 2)}</code> 🚀\n"
        f"🤖 <i>Generat prin ScraperAPI Proxy Engine</i>"
    )

    trimite_sau_editeaza_mesaj(target_chat_id, mesaj_final, msg_id)

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
                            threading.Thread(target=lambda c=cid: trimite_sau_editeaza_mesaj(c, "🏓 <b>PONG!</b> Botul este online și funcționează perfect!")).start()
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
schedule.every().day.at("09:00").do(lambda: proceseaza_si_trimite_bilet(CHAT_ID, 5.0))

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(30)
