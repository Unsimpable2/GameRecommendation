import json
import os
import requests
import logging
from datetime import datetime


#TO CHANGE AFTER FULL BASE IS DOWNLOADED!!!!!!!!!!!!!!!!!!!!!!!!1


logging.basicConfig(filename='steam_game_updater.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

base_file_path = 'steam_game_list_base.json'
new_file_path = 'steam_game_list_new.json'
update_file_path = 'steam_game_list_to_update.json'
last_update_file_path = 'last_database_update.txt'

def fetch_steam_game_data():
    url = 'https://api.steampowered.com/ISteamApps/GetAppList/v2/'
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()['applist']['apps']
    else:
        logging.error(f"Error fetching data from Steam API: {response.status_code}")
        raise Exception(f"Error fetching data from Steam API: {response.status_code}")

def save_to_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4)
    logging.info(f"Data saved to {file_path}")

def compare_game_lists(base_data, new_data):
    base_ids = {game['appid'] for game in base_data}
    new_ids = {game['appid'] for game in new_data}
    
    missing_ids = new_ids - base_ids
    missing_games = [game for game in new_data if game['appid'] in missing_ids]
    
    return missing_games

def main():
    logging.info("Starting the update process.")
    new_data = fetch_steam_game_data()
    save_to_json(new_data, new_file_path)

    if os.path.exists(base_file_path):
        with open(base_file_path, 'r', encoding='utf-8') as base_file:
            base_data = json.load(base_file)
    else:
        logging.warning("No existing game database found, creating a new one.")
        base_data = []

    missing_games = compare_game_lists(base_data, new_data)

    if not missing_games:
        print("The game database is up to date. No missing games found.")
        logging.info("No missing games found. Database is up to date.")
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        if os.path.exists(update_file_path):
            os.remove(update_file_path)
        return

    save_to_json(missing_games, update_file_path)

    if os.path.exists(base_file_path):
        os.remove(base_file_path)
        logging.info(f"Removed old base file: {base_file_path}")
    os.rename(new_file_path, base_file_path)
    logging.info(f"Updated base file: {base_file_path}")

    with open(last_update_file_path, 'a', encoding='utf-8') as last_update_file:
        last_update_file.write(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        last_update_file.write(f"Games Added: {len(missing_games)}\n")
        last_update_file.write("Game Names:\n")
        for game in missing_games:
            last_update_file.write(f"- {game['name']}\n")
        
        last_update_file.write("---------------------------------------\n")
    
    logging.info("Updated timestamp of the last database update with new games information.")

if __name__ == "__main__":
    try:
        main()
        print("Game database update completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        print(f"An error occurred: {e}")
