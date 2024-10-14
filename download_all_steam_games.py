import json
import requests
import html
from bs4 import BeautifulSoup
import time
import logging

# Konfiguracja logowania
logging.basicConfig(filename='steam_games.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_game_details(app_id, retries=3):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if str(app_id) in data and data[str(app_id)]['success']:
                    if data[str(app_id)]['data']['type'] == 'game':
                        return data[str(app_id)]['data']
            else:
                logging.warning(f"Niepoprawny status odpowiedzi dla ID {app_id}: {response.status_code}")
        except requests.RequestException as e:
            logging.error(f"Błąd podczas pobierania danych dla ID {app_id}: {str(e)}")
        
        time.sleep(1)  # Czekaj chwilę przed kolejną próbą
    return None

def remove_html_tags(text):
    if not text or text.strip() == "":
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean_text = soup.get_text(separator=" ")
    return clean_text.replace("\n", " ")

def save_games_data(app_id=None):
    url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'
    try:
        response = requests.get(url)
        data = response.json()
    except requests.RequestException as e:
        logging.error(f"Błąd podczas pobierania listy gier: {str(e)}")
        return

    gry = []

    if app_id: 
        game_details = get_game_details(app_id)
        if game_details:
            gry.append(process_game_details(app_id, game_details))
    else:  
        for app in data['applist']['apps']:
            app_id = app['appid']
            game_details = get_game_details(app_id)
            if game_details:
                gry.append(process_game_details(app_id, game_details))
            else:
                logging.info(f"Pominięto grę o ID: {app_id}")

    with open('test.json', 'w', encoding='utf-8') as file:
        json.dump(gry, file, ensure_ascii=False, indent=4)

    print(f"Dane dla {'wszystkich gier' if not app_id else f'gry o ID {app_id}'} zostały zapisane do pliku lista_gier_steam.json")

def process_game_details(app_id, game_details):
    try:
        is_free = game_details.get('is_free', False)

        if is_free:
            price = "Free"
        else:
            price = game_details.get('price_overview', {}).get('final_formatted', 'N/A')

        detailed_description = game_details.get('detailed_description', '')
        detailed_description = html.unescape(detailed_description)
        detailed_description = remove_html_tags(detailed_description).replace("\n", " ")

        pc_requirements = game_details.get('pc_requirements', {})
        
        if isinstance(pc_requirements, dict):
            minimal_requirements = pc_requirements.get('minimum', 'Brak danych')
            recommended_requirements = pc_requirements.get('recommended', 'Brak')
        else:
            minimal_requirements = 'Brak danych'
            recommended_requirements = 'Brak danych'

        minimal_requirements = remove_html_tags(minimal_requirements).replace("\n", " ")
        recommended_requirements = remove_html_tags(recommended_requirements).replace("\n", " ") if recommended_requirements != 'Brak' else 'Brak danych'

        return {
            'App ID': app_id,
            'Nazwa gry': game_details['name'],
            'Typ': game_details['type'],
            'Developer': game_details.get('developers', []),
            'Wydawca': game_details.get('publishers', []),
            'Czy darmowa': is_free,
            'Cena': price,
            'Wiek': game_details.get('required_age', 'N/A'),
            'Szczegółowy opis': detailed_description,
            'O grze': game_details.get('about_the_game', 'Brak danych'),
            'Krótki opis': game_details.get('short_description', 'Brak danych'),
            'Minimalne wymagania': minimal_requirements,
            'Zalecane wymagania': recommended_requirements,
            'Kategorie': game_details.get('categories', [])
        }
    except Exception as e:
        logging.error(f"Błąd podczas przetwarzania danych dla gry o ID {app_id}: {str(e)}")
        return None

# Zapisz dane dla wszystkich gier
save_games_data()

# Możliwość zapisania danych dla konkretnego ID
# save_games_data(app_id=570)
