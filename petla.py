import json
import requests
import logging
import time
import random

def get_game_details(app_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if str(app_id) in data and data[str(app_id)]['success']:
                if data[str(app_id)]['data'].get('type') == 'game':
                    logging.info(f"App ID {app_id} is a game. Type: {data[str(app_id)]['data'].get('type')}")
                    return data[str(app_id)]['data']  
                else:
                    logging.info(f"App ID {app_id} is not a game. Type: {data[str(app_id)]['data'].get('type')}")
                    return None  # Return None if it's not a game
        else:
            logging.warning(f"Invalid response status for ID {app_id}: {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"Error fetching data for ID {app_id}: {str(e)}")
    
    return None  # Return None for any request errors

def save_games_data(start_id=1, end_id=10, app_id=None):
    url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'
    try:
        response = requests.get(url)
        data = response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching game list: {str(e)}")
        return

    games = []

    if app_id:
        game_details = get_game_details(app_id)
        if game_details:  # Now it just checks if details are returned
            games.append(process_game_details(app_id, game_details))
    else:
        # Loop through the specified range of app IDs
        for app_id in range(start_id, end_id + 1):
            game_details = get_game_details(app_id)

            if game_details:  # Only append if game_details are valid
                games.append(process_game_details(app_id, game_details))
            else:
                logging.info(f"App ID {app_id} is not a valid game. Skipping.")

            time.sleep(1)  # Sleep between attempts to avoid hitting the API too hard

    with open('steam_game.json', 'w', encoding='utf-8') as file:
        json.dump(games, file, ensure_ascii=False, indent=4)

    print(f"Data for {'all games' if not app_id else f'game with ID {app_id}'} has been saved to steam_game.json")

def process_game_details(app_id, game_details):
        is_free = game_details.get('is_free', False)

        if is_free:
            price = "Free"
        else:
            price = game_details.get('price_overview', {}).get('final_formatted', 'N/A')

        return {
            'App ID': app_id,
            'Game Name': game_details['name'],
            'Type': game_details['type'],
            'Is Free': is_free,
            'Price': price,
        }

# Enable logging to see the output in console or log file
logging.basicConfig(level=logging.INFO)

# Call the function to save game data with specified range
save_games_data(start_id=1, end_id=10)
# Alternatively, you can call for a specific app_id
# save_games_data(app_id=703400)
