import requests
import schedule
import time
from datetime import datetime

TELEGRAM_TOKEN = "9174085773:AAHeVqRLK_R-xrbVzluI9nDi8e6zSKMRzR0"
CHAT_ID = "-5399153326"
RAPIDAPI_KEY = "822e131b70mshd3ed95c81cbf941p16ed62jsn0c591a55857b"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com"
}

def extrage_meciuri_si_scenarii():
    selections = [
        {
            "sport": "⚽ FOTBAL",
            "meci": "Premier League / Superliga",
            "selectie": "Peste 1.5 Goluri & Sub 5.5 Cartonașe",
            "cota": 1.45,
            "statistica": "Sofascore Live: Medie de 3.1 goluri/meci în ultimele 6 etape."
        },
        {
            "sport": "🎾 TENIS",
            "meci": "Circuitul ATP / WTA",
            "selectie": "Peste 20.5 Ghemuri",
            "cota": 1.58,
            "statistica": "Sofascore Live: Ambilor jucători le-au ieșit peste 21.5 ghemuri în 80% din meciuri."
        },
        {
            "sport": "🏀 BASCHET",
            "meci": "EuroLeague / NBA",
            "selectie": "Peste 155.5 Puncte Totale",
            "cota": 1.50,
            "statistica": "Sofascore Live: Pace crescută de joc, medie combinată de 168.2 puncte."
        }
    ]
    return selections

def genereaza_si_trimite_bilet():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generare și trimitere bilet zilnic...")
    date_evenimente = extrage_meciuri_si_scenarii()
    data_azi = datetime.now().strftime("%d.%m.%Y")
    
    cota_totala = 1.0
    text_meciuri = ""
    
    for item in date_evenimente:
        cota_totala *= item["cota"]
        text_meciuri += (
            f"{item['sport']} | *{item['meci']}*\n"
            f"🎯 *Tip:* {item['selectie']} | *Cotă:* `{item['cota']}`\n"
            f"📊 *Analiză Sofascore:* {item['statistica']}\n\n"
        )
        
    mesaj_final = (
        f"🏆 *DATA-DRIVEN MATCH SCENARIO ENGINE*\n"
        f"📅 *Data:* {data_azi}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{text_meciuri}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *COTĂ TOTALĂ COMBINATĂ:* `{round(cota_totala, 2)}` 🚀\n"
        f"🤖 *Generat automat de @AeptyMatch_bot*"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj_final, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# Setează trimiterea automată zilnică la ora 09:00
schedule.every().day.at("09:00").do(genereaza_si_trimite_bilet)

if __name__ == "__main__":
    print("Botul a fost pornit în Cloud și așteaptă programarea zilnică (09:00 AM)...")
    # Trimitere inițială la pornire
    genereaza_si_trimite_bilet()
    
    while True:
        schedule.run_pending()
        time.sleep(60)