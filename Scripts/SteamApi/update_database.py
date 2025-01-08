import os
import json
import logging
import requests
from datetime import datetime

base_path = '../GameRecommendation'
data_list_path = '/Data'
log_update_path = '/Logs/Update'

base_file_path = base_path + data_list_path + '/BaseList/steam_game_list_base.json'
new_file_path = base_path + data_list_path + '/BaseList/steam_game_list_new.json'
update_file_path = base_path + data_list_path + '/DownloadList/steam_game_list_to_update.json'
last_update_file_path = base_path + log_update_path + '/last_database_update.txt'

logging.basicConfig(
    filename = base_path + log_update_path + '/steam_game_updater.log',
    level = logging.INFO,
    format = '%(asctime)s - %(levelname)s - %(message)s'
)

def fetch_steam_game_data():
    url = 'https://api.steampowered.com/ISteamApps/GetAppList/v2/'
    response = requests.get(url)

    if response.status_code == 200:
        return [{"appid": game["appid"], "name": game["name"]} for game in response.json()['applist']['apps']]
    else:
        logging.error(f"Error fetching data from Steam API: {response.status_code}")
        raise Exception(f"Error fetching data from Steam API: {response.status_code}")

def save_to_json(data, file_path):
    with open(file_path, 'w', encoding = 'utf-8') as json_file:
        json.dump(data, json_file, indent = 4, ensure_ascii = False)
    logging.info(f"Data saved to {file_path}")

def compare_game_lists(base_data, new_data):
    base_ids = {game['appid'] for game in base_data}
    new_ids = {game['appid'] for game in new_data}

    missing_ids = new_ids - base_ids
    missing_games = [game for game in new_data if game['appid'] in missing_ids]

    return missing_games

def delete_duplicates():
    file_path = update_file_path

    try:
        with open(file_path, 'r', encoding = 'utf-8') as f:
            data = json.load(f)
            logging.info(f"Read {len(data)} entries from the file before removing duplicates.")

        if not data:
            logging.warning("The file is empty. Skipping duplicate removal.")
            return

        seen = set()
        unique_data = []
        for entry in data:
            entry_str = json.dumps(entry, sort_keys = True)
            if entry_str not in seen:
                seen.add(entry_str)
                unique_data.append(entry)

        if len(unique_data) == len(data):
            logging.info("No duplicates found in the file.")
        else:
            logging.info("Duplicates have been removed.")

        with open(file_path, 'w', encoding = 'utf-8') as f:
            json.dump(unique_data, f, indent = 4, ensure_ascii = False)
            logging.info(f"Unique data saved: {unique_data}")

    except json.JSONDecodeError:
        logging.error(f"File {file_path} is not a valid JSON. Skipping duplicate removal.")
    except Exception as e:
        logging.error(f"Error during duplicate removal: {e}")
        raise

def main():
    logging.info("Starting the update process.")
    try:
        new_data = fetch_steam_game_data()
        save_to_json(new_data, new_file_path)

        if os.path.exists(base_file_path):
            with open(base_file_path, 'r', encoding = 'utf-8') as base_file:
                base_data = json.load(base_file)
        else:
            logging.warning("No existing game database found, creating a new one.")
            base_data = []

        if os.path.exists(update_file_path):
            with open(update_file_path, 'r', encoding = 'utf-8') as update_file:
                current_update_data = json.load(update_file)
        else:
            current_update_data = []

        initial_update_count = len(current_update_data)

        missing_games = compare_game_lists(base_data, new_data)

        if not missing_games:
            print("The game database is up to date. No missing games found.")
            logging.info("No missing games found. Database is up to date.")
            if os.path.exists(new_file_path):
                os.remove(new_file_path)
            return

        current_update_data.extend(missing_games)
        save_to_json(current_update_data, update_file_path)

        if os.path.exists(base_file_path):
            os.remove(base_file_path)
            logging.info(f"Removed old base file: {base_file_path}")
        os.rename(new_file_path, base_file_path)
        logging.info(f"Updated base file: {base_file_path}")

        delete_duplicates()

        final_update_count = len(current_update_data)
        num_added_elements = final_update_count - initial_update_count

        with open(last_update_file_path, 'a', encoding = 'utf-8') as last_update_file:
            last_update_file.write(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            last_update_file.write(f"Elements Added: {num_added_elements}\n")
            last_update_file.write("------------End of update------------\n\n")

        logging.info("Updated timestamp of the last database update with new games information.")
        logging.info("------------End of update------------\n")
        print("Game database update completed successfully.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
