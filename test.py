import json
import requests
import time

max_iterations = 10
iteration_count = 0

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
        print(f'Błąd przy pobieraniu danych dla app_id: {app_id} - {e}')
        return None

with open('steam_game_list.json', 'r', encoding='utf-8') as file:
    game_list = json.load(file)

processed_games = []

for game in game_list:
    if iteration_count >= max_iterations:
        break

    app_id = game['appid']
    details = get_app_details(app_id)

    if details and details.get('type') == 'game':
        name = details.get('name', 'Brak nazwy')
        developer = details.get('developers', ['Brak informacji'])[0]
        publisher = details.get('publishers', ['Brak informacji'])[0]
        print(f"Gra: {name}\nDeweloper: {developer}\nWydawca: {publisher}\n")

    processed_games.append(game)

    iteration_count += 1
    time.sleep(0.5)

remaining_games = [game for game in game_list if game not in processed_games]

with open('steam_game_list.json', 'w', encoding='utf-8') as file:
    json.dump(remaining_games, file, ensure_ascii=False, indent=4)

print("Lista została zaktualizowana, przetworzone app_id usunięte.")