import json
import requests
import time
import logging
import os

base_path = '../MasterDeg/Database/SteamDatabase'
log_file_path = os.path.join(base_path, 'steam_app_processing.log')
file_path_list = os.path.join(base_path, 'steam_game_listW.json')
file_path_processed = os.path.join(base_path, 'steam_games_processedW.json')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=log_file_path, filemode='w')

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
        logging.error(f'Error while fetching data for app_id: {app_id} - {e}')
        return None

def save_remaining_games(game_list, processed_games, file_path_list):
    remaining_games = [game for game in game_list if game not in processed_games]
    with open(file_path_list, 'w', encoding='utf-8') as file:
        json.dump(remaining_games, file, ensure_ascii=False, indent=4)

def download_all_steam_games(max_iterations = 80000):
    processed_games = []
    iteration_count = 0

    with open(file_path_list, 'r', encoding='utf-8') as file:
        game_list = json.load(file)

    try:
        with open(file_path_processed, 'r', encoding='utf-8') as file:
            existing_games = json.load(file)
    except FileNotFoundError:
        existing_games = []

    for game in game_list:
        if iteration_count >= max_iterations:
            break

        app_id = game['appid']
        details = get_app_details(app_id)

        if details:
            if details.get('type') == 'game':
                logging.info(f"Processed game: {details.get('name', 'No name')} (app_id: {app_id})")

                is_free = details.get('is_free', False)
                price_overview = details.get('price_overview', {})
                price = price_overview.get('final_formatted', 'N/A') if price_overview else 'N/A'
                detailed_description = details.get('detailed_description', 'No description')
                short_description = details.get('short_description', 'No description')
                about_game = details.get('about_the_game', 'No description')
                pc_requirements_data = details.get('pc_requirements', [])
                if isinstance(pc_requirements_data, list) and pc_requirements_data:
                    pc_requirements = pc_requirements_data[0]
                elif isinstance(pc_requirements_data, dict):
                    pc_requirements = pc_requirements_data
                else:
                    pc_requirements = {}
                minimal_requirements = pc_requirements.get('minimum', 'No information')
                recommended_requirements = pc_requirements.get('recommended', 'No information')

                game_details = {
                    'App ID': app_id,
                    'Game Name': details['name'],
                    'Type': details['type'],
                    'Developer': details.get('developers', ['No information']),
                    'Publisher': details.get('publishers', ['No information']),
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
                }

                existing_games.append(game_details)

                with open(file_path_processed, 'w', encoding='utf-8') as file:
                    json.dump(existing_games, file, ensure_ascii=False, indent=4)

                processed_games.append(game)
                save_remaining_games(game_list, processed_games, file_path_list)
            else:
                logging.info(f"Object is not a game: app_id: {app_id}")
                processed_games.append(game)
                save_remaining_games(game_list, processed_games, file_path_list)
        else:
            logging.warning(f"Failed to fetch details for app_id: {app_id}")
            processed_games.append(game)
            save_remaining_games(game_list, processed_games, file_path_list)

        iteration_count += 1
        time.sleep(0.5)

download_all_steam_games()