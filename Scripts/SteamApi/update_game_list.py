import os
import sys
import json
import logging
import requests
import shutil
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding = 'utf-8', errors = 'replace')

base_path = '../GameRecommendation'
data_list_path = '/Data'
log_update_path = '/Logs/Update'

base_file_path = base_path + data_list_path + '/BaseList/steam_game_list_base.json'
removed_file_path = base_path + data_list_path + '/BaseList/steam_game_list_removed.json'
update_file_path = base_path + data_list_path + '/DownloadList/steam_game_list_to_update.json'
last_update_file_path = base_path + log_update_path + '/last_database_update.txt'

log_file_path = base_path + log_update_path + '/steam_game_updater.log'

def get_logger():
    logger = logging.getLogger("steam_game_updater")
    logger.setLevel(logging.INFO)
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(log_formatter)
    if not logger.hasHandlers():
        logger.addHandler(file_handler)
    return logger

logger = get_logger()

def should_update_database(hours = 24):
    try:
        with open(last_update_file_path, 'r', encoding = 'utf-8') as f:
            lines = f.readlines()
        for line in reversed(lines):
            if line.startswith("Last Update:"):
                timestamp = line.split("Last Update:")[1].strip()
                last_update_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                return datetime.now() - last_update_time >= timedelta(hours = hours)
    except Exception:
        return True

def fetch_steam_game_data():
    url = 'https://api.steampowered.com/ISteamApps/GetAppList/v2/'
    response = requests.get(url)
    if response.status_code == 200:
        return [{"appid": game["appid"], "name": game["name"]} for game in response.json()['applist']['apps']]
    else:
        logger.error(f"Error fetching data from Steam API: {response.status_code}")
        raise Exception(f"Error fetching data from Steam API: {response.status_code}")

def save_to_json(data, file_path):
    with open(file_path, 'w', encoding = 'utf-8') as f:
        json.dump(data, f, indent = 4, ensure_ascii = False)
    logger.info(f"Data saved to {file_path}")

def compare_game_lists(base_data, new_data):
    base_ids = {game['appid'] for game in base_data}
    new_ids = {game['appid'] for game in new_data}
    missing_games = [g for g in new_data if g['appid'] not in base_ids]
    removed_games = [g for g in base_data if g['appid'] not in new_ids]
    return missing_games, removed_games

def backup_base_file():
    if os.path.exists(base_file_path):
        backup_path = base_file_path.replace(".json", "_backup.json")
        shutil.copy(base_file_path, backup_path)
        logger.info(f"Backup created at {backup_path}")

def delete_duplicates():
    try:
        with open(update_file_path, 'r', encoding = 'utf-8') as f:
            data = json.load(f)
        seen = set()
        unique_data = []
        for entry in data:
            entry_str = json.dumps(entry, sort_keys = True)
            if entry_str not in seen:
                seen.add(entry_str)
                unique_data.append(entry)
        with open(update_file_path, 'w', encoding = 'utf-8') as f:
            json.dump(unique_data, f, indent = 4, ensure_ascii = False)
        logger.info(f"Removed duplicates. Unique entries: {len(unique_data)}")
    except Exception as e:
        logger.error(f"Error removing duplicates: {e}")

def update_game_list():
    if not should_update_database():
        logger.info("Game list update not required yet.")
        return

    logger.info("Starting safe update of the game list...")
    try:
        new_data = fetch_steam_game_data()

        if os.path.exists(base_file_path):
            with open(base_file_path, 'r', encoding = 'utf-8') as f:
                base_data = json.load(f)
        else:
            base_data = []

        if len(new_data) < 0.6 * len(base_data):
            logger.warning("New data looks suspiciously short. Aborting update.")
            return

        missing_games, removed_games = compare_game_lists(base_data, new_data)

        if not missing_games:
            logger.info("No new games found.")
        else:
            logger.info(f"New games: {len(missing_games)}")

        if removed_games:
            save_to_json(removed_games, removed_file_path)
            logger.info(f"Removed games saved to: {removed_file_path}")

        if os.path.exists(update_file_path):
            with open(update_file_path, 'r', encoding = 'utf-8') as f:
                current_update_data = json.load(f)
        else:
            current_update_data = []

        current_ids = {g['appid'] for g in current_update_data}
        new_unique_games = [g for g in missing_games if g['appid'] not in current_ids]

        current_update_data.extend(new_unique_games)
        save_to_json(current_update_data, update_file_path)
        logger.info(f"Appended {len(new_unique_games)} new unique games to update list.")

        delete_duplicates()
        save_to_json(new_data, base_file_path)
        backup_base_file()

        with open(last_update_file_path, 'a', encoding = 'utf-8') as f:
            f.write(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Elements Added: {len(new_unique_games)}\n")
            f.write(f"Removed App IDs: {len(removed_games)}\n")
            f.write("------------End of update------------\n\n")

        logger.info("Update completed successfully.\n")
        logger.info("------------End of update------------\n\n")

    except Exception as e:
        logger.error(f"Update failed: {e}")
