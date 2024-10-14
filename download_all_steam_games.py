import json
import requests
import time
import logging

max_iterations = 3000
iteration_count = 0

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='steam_app_processing.log', filemode='w')

def get_app_details(app_id):
    url = f'http://store.steampowered.com/api/appdetails?appids={app_id}'
    try:
        response = requests.get(url)
        app_data = response.json()
        if app_data[str(app_id)]['success']:
            return app_data[str(app_id)]['data']
        else:
            return None
    except Exception as e:
        logging.error(f'Błąd przy pobieraniu danych dla app_id: {app_id} - {e}')
        return None

# Wczytanie listy gier
with open('steam_game_list.json', 'r', encoding='utf-8') as file:
    game_list = json.load(file)

processed_games = []
game_details_list = []

for game in game_list:
    if iteration_count >= max_iterations:
        break

    app_id = game['appid']
    details = get_app_details(app_id)

    if details:
        if details.get('type') == 'game':
            # Logowanie, gdy obiekt jest grą
            logging.info(f"Przetworzono grę: {details.get('name', 'Brak nazwy')} (app_id: {app_id})")
            
            # Pobranie szczegółów gry
            is_free = details.get('is_free', False)
            price_overview = details.get('price_overview', {})
            price = price_overview.get('final_formatted', 'N/A') if price_overview else 'N/A'
            detailed_description = details.get('detailed_description', 'Brak opisu')
            short_description = details.get('short_description', 'Brak opisu')
            about_game = details.get('about_the_game', 'Brak opisu')
            pc_requirements_data = details.get('pc_requirements', [])
            if isinstance(pc_requirements_data, list) and pc_requirements_data:
                pc_requirements = pc_requirements_data[0]
            elif isinstance(pc_requirements_data, dict):
                pc_requirements = pc_requirements_data
            else:
                pc_requirements = {}
            minimal_requirements = pc_requirements.get('minimum', 'Brak informacji')
            recommended_requirements = pc_requirements.get('recommended', 'Brak informacji')
            
            # Dodanie szczegółów gry do listy
            game_details_list.append({
                'App ID': app_id,
                'Game Name': details['name'],
                'Type': details['type'],
                'Developer': details.get('developers', ['Brak informacji']),
                'Publisher': details.get('publishers', ['Brak informacji']),
                'Is Free': is_free,
                'Price': price,
                'Age Rating': details.get('required_age', 'N/A'),
                'Detailed Description': detailed_description,
                'Short Description': short_description,
                'About the Game': about_game,
                'Minimum Requirements': minimal_requirements,
                'Recommended Requirements': recommended_requirements,
                'Categories': details.get('categories', []),
                'Genres': details.get('genres', [])
            })
        else:
            # Logowanie, gdy obiekt nie jest grą
            logging.info(f"Obiekt nie jest grą: app_id: {app_id}")
    else:
        logging.warning(f"Nie udało się pobrać szczegółów dla app_id: {app_id}")
    
    processed_games.append(game)
    iteration_count += 1
    time.sleep(0.5)

# Zapisanie pozostałych gier do pliku steam_game_list.json
remaining_games = [game for game in game_list if game not in processed_games]
with open('steam_game_list.json', 'w', encoding='utf-8') as file:
    json.dump(remaining_games, file, ensure_ascii=False, indent=4)

# Dopisanie przetworzonych gier do pliku steam_games_processed.json
try:
    with open('steam_games_processed.json', 'r', encoding='utf-8') as file:
        existing_games = json.load(file)
except FileNotFoundError:
    existing_games = []

existing_games.extend(game_details_list)

with open('steam_games_processed.json', 'w', encoding='utf-8') as file:
    json.dump(existing_games, file, ensure_ascii=False, indent=4)

print("Lista została zaktualizowana, przetworzone app_id usunięte. Szczegóły gier zapisano do pliku steam_games_processed.json.")