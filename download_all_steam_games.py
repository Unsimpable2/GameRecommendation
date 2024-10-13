import json
import requests
import html
from bs4 import BeautifulSoup

def get_game_details(app_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if str(app_id) in data and data[str(app_id)]['success']:
            if data[str(app_id)]['data']['type'] == 'game':
                return data[str(app_id)]['data']
    return None

def remove_html_tags(text):
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator="\n")

def save_games_data(app_id=None):
    url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'
    response = requests.get(url)
    data = response.json()

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

    with open('lista_gier_steam.json', 'w', encoding='utf-8') as file:
        json.dump(gry, file, ensure_ascii=False, indent=4)

    print(f"Dane dla {'wszystkich gier' if not app_id else f'gry o ID {app_id}'} zostały zapisane do pliku lista_gier_steam.json")

def process_game_details(app_id, game_details):
    is_free = game_details.get('is_free', False)
    
    if is_free:
        price = "Free"
    else:
        price = game_details.get('price_overview', {}).get('final_formatted', 'N/A')

    detailed_description = game_details.get('detailed_description', '')
    detailed_description = html.unescape(detailed_description)
    detailed_description = remove_html_tags(detailed_description)

    pc_requirements = game_details.get('pc_requirements', {})
    minimal_requirements = pc_requirements.get('minimum', 'Brak danych')
    recommended_requirements = pc_requirements.get('recommended', 'Brak')

    minimal_requirements = remove_html_tags(minimal_requirements)
    recommended_requirements = remove_html_tags(recommended_requirements) if recommended_requirements != 'Brak' else 'Brak danych'

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

# save_games_data()

save_games_data(app_id=570)
