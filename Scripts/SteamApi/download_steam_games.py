import re
import os
import sys
import json
import gzip
import time
import signal
import logging
import requests
from glob import glob
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.stdout = open(os.devnull, 'w', encoding = 'utf-8')
sys.stderr = open(os.devnull, 'w', encoding = 'utf-8')

from update_game_list import should_update_database, update_game_list
from get_id_form_error import get_id_from_error
from Scripts.Database.db_connection_pool import create_connection_pool, close_connection_pool
from Scripts.Database.insert_data_to_database import insert_data_from_object, log_start_of_insert_session, log_end_of_insert_session
from game_data_to_vector import game_data_to_vector

DetectorFactory.seed = 0

PART_LIMIT = 2000 
MERGE_THRESHOLD = 3
DATA_DIR = "Data/GamesData"
stop_requested = False
base_path = '../GameRecommendation'

def signal_handler(sig, frame):
    global stop_requested
    stop_requested = True

signal.signal(signal.SIGINT, signal_handler)

if not os.path.exists(base_path + "/Scripts/Logs/Download"):
    os.makedirs(base_path + "/Scripts/Logs/Download")

current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
log_dir = os.path.join(base_path, "Logs/Download")
os.makedirs(log_dir, exist_ok=True)

logging.StreamHandler(sys.stdout).setStream(open(os.devnull, 'w', encoding = 'utf-8'))
download_logger = logging.getLogger('download_logger')
download_logger.setLevel(logging.INFO)
download_logger.handlers.clear()
download_logger.propagate = False
download_handler = logging.FileHandler(os.path.join(log_dir, f'downloaded_games_{current_time}.log'))
download_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
download_logger.addHandler(download_handler)

error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_logger.handlers.clear()
error_logger.propagate = False
error_handler = logging.FileHandler(os.path.join(log_dir, 'error_id.log'), mode = 'a')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

def save_update_list(data, file_path):
    with open(file_path, "w", encoding = "utf-8") as f:
        json.dump(data, f, ensure_ascii = False, indent = 4)

def load_json_file(file_path):
    with open(file_path, "r", encoding = "utf-8") as f:
        return json.load(f)

def get_last_json_file(directory):
    json_files = glob(os.path.join(directory, "steam_games_processed_vector_part*.jsonl"))
    if not json_files:
        return None

    file_numbers = [
        int(re.search(r"steam_games_processed_vector_part(\d+).jsonl", f).group(1))
        for f in json_files if re.search(r"steam_games_processed_vector_part(\d+).jsonl", f)
    ]
    if not file_numbers:
        return None

    max_file_number = max(file_numbers)
    return os.path.join(directory, f"steam_games_processed_vector_part{max_file_number}.jsonl")

def append_to_jsonl_file(base_name, obj, directory = DATA_DIR):
    os.makedirs(directory, exist_ok = True)

    jsonl_files = sorted(glob(os.path.join(directory, f"{base_name}*.jsonl")))
    gz_files = sorted(glob(os.path.join(directory, f"{base_name}*.gz")))

    used_numbers = set()
    for path in jsonl_files + gz_files:
        match = re.search(r"part(\d+)", path)
        if match:
            used_numbers.add(int(match.group(1)))

    for index in sorted(used_numbers):
        current_file = os.path.join(directory, f"{base_name}{index}.jsonl")
        if os.path.exists(current_file):
            with open(current_file, "r", encoding = "utf-8") as f:
                current_lines = sum(1 for _ in f)
            if current_lines < PART_LIMIT:
                break
    else:
        next_index = max(used_numbers) + 1 if used_numbers else 0
        current_file = os.path.join(directory, f"{base_name}{next_index}.jsonl")

    with open(current_file, "a", encoding = "utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii = False) + "\n")

def merge_jsonl_parts(base_name, directory = DATA_DIR):
    jsonl_files = sorted(glob(os.path.join(directory, f"{base_name}*.jsonl")))
    
    while len(jsonl_files) >= MERGE_THRESHOLD:
        to_merge = jsonl_files[:MERGE_THRESHOLD]
        
        all_full = all(
            sum(1 for _ in open(path, encoding = "utf-8")) >= PART_LIMIT
            for path in to_merge
        )
        
        if not all_full:
            return

        merged_index = int(re.search(r"part(\d+)", to_merge[0]).group(1))
        merged_filename = os.path.join(directory, f"{base_name}{merged_index}")

        with gzip.open(merged_filename + ".gz", "wt", encoding = "utf-8") as gz_file:
            for file in to_merge:
                with open(file, "r", encoding = "utf-8") as f:
                    for line in f:
                        gz_file.write(line)

        for file in to_merge:
            os.remove(file)

        break

def find_next_jsonl_filename_after_merge(base_name, directory = DATA_DIR):
    existing_jsonl = sorted(glob(os.path.join(directory, f"{base_name}*.jsonl")))
    existing_gz = sorted(glob(os.path.join(directory, f"{base_name}*.gz")))

    used_numbers = set()

    for path in existing_jsonl + existing_gz:
        match = re.search(r"part(\d+)", path)
        if match:
            used_numbers.add(int(match.group(1)))

    if not used_numbers:
        return os.path.join(directory, f"{base_name}0.jsonl")
    
    next_free = max(used_numbers) + 1
    while os.path.exists(os.path.join(directory, f"{base_name}{next_free}.jsonl")):
        next_free += 1

    return os.path.join(directory, f"{base_name}{next_free}.jsonl")

def get_app_details(app_id):
    url = f'http://store.steampowered.com/api/appdetails?appids={app_id}&l=english'
    try:
        response = requests.get(url)
        app_data = response.json()
        if app_data[str(app_id)]['success']:
            return app_data[str(app_id)]['data']
        else:
            return None
    except TypeError as e:
        if "'NoneType' object is not subscriptable" in str(e):
            error_logger.error(f'Error while fetching data for app_id: {app_id} - {e}')
            download_logger.info(f'Error for app_id: {app_id} has been logged in error_id.log')
        else:
            download_logger.error(f'Error while fetching data for app_id: {app_id} - {e}')
        return None
    except Exception as e:
        download_logger.error(f'Error while fetching data for app_id: {app_id} - {e}')
        return None

def get_steam_tags(app_id):
    url = f"https://store.steampowered.com/app/{app_id}/?l=english"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(url, headers = headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        tags = [tag.text.strip() for tag in soup.select('.app_tag')]

        if tags and tags[-1] == '+':
            tags.pop()

        return tags if tags else ["No tags for game"]
    else:
        logging.warning(f"Failed to access the Steam page for app_id: {app_id}. Status: {response.status_code}")
        return ["No tags for game because of error"]

def remove_html_tags(text):
    clean = re.compile('<.*?>')
    text_without_html = re.sub(clean, ' ', text)

    patterns_to_remove = [r'&quot;', r'!-&quot;', r'\?&quot;', r'!-&quot;', r'&amp;', r'&gt;', r'&lt;']
    for pattern in patterns_to_remove:
        text_without_html = re.sub(pattern, '', text_without_html)

    return re.sub(r'\s+', ' ', text_without_html).strip()

def clean_json_data(json_data):
    if isinstance(json_data, dict):
        return {key: clean_json_data(value) for key, value in json_data.items()}
    elif isinstance(json_data, list):
        return [clean_json_data(item) for item in json_data]
    elif isinstance(json_data, str):
        return remove_html_tags(json_data)
    else:
        return json_data

def is_english(text):
    try:
        return detect(text) == 'en'
    except Exception:
        return False

def download_steam_games(file_path_list, max_iterations = 90000):
    create_connection_pool(minconn = 1, maxconn = 10)
    
    try:
        if should_update_database(hours = 24):
            update_game_list()

        log_start_of_insert_session()
        total_inserted_counter = [0]

        with open(file_path_list, 'r', encoding = 'utf-8') as file:
            game_list = json.load(file)

        iteration_count = 0

        all_tags = set()
        all_genres = set()

        json_files = glob(os.path.join("Data/GamesData", "steam_games_processed_vector_part*.jsonl"))
        for file in json_files:
            try:
                data = load_json_file(file)
                for game in data:
                    all_tags.update(game.get("Tags", []))
                    for genre in game.get("Genres", []):
                        all_genres.add(genre["description"])
            except:
                pass

        all_tags = list(all_tags)
        all_genres = list(all_genres)

        while game_list:
            game = None
            app_id = None

            try:
                if iteration_count >= max_iterations or stop_requested:
                    if stop_requested:
                        download_logger.info('Stop requested. Finishing current iteration before exiting...')
                    break
                
                game = game_list.pop(0)
                app_id = game['appid']
                details = get_app_details(app_id)

                if details and details.get('type') == 'game':
                    download_logger.info(f"Processed game: {details.get('name', 'No name')} (app_id: {app_id})")

                    detailed_description = details.get('detailed_description', '')
                    short_description = details.get('short_description', '')
                    about_game = details.get('about_the_game', '')

                    if not (is_english(detailed_description) or is_english(short_description) or is_english(about_game) or is_english(details['name'])):
                        download_logger.info(f"Skipping app_id: {app_id} because description is not in English.")
                        iteration_count += 1
                        continue

                    is_free = details.get('is_free', False)
                    price_overview = details.get('price_overview', {})
                    price = price_overview.get('final_formatted', 'N/A') if price_overview else 'N/A'

                    pc_requirements = 'No information'
                    pc_requirements_data = details.get('pc_requirements', [])
                    pc_requirements = pc_requirements_data[0] if isinstance(pc_requirements_data, list) and pc_requirements_data else pc_requirements

                    minimal_requirements = 'No information'
                    recommended_requirements = 'No information'

                    if isinstance(pc_requirements, dict):
                        minimal_requirements = pc_requirements.get('minimum', 'No information')
                        recommended_requirements = pc_requirements.get('recommended', 'No information')

                    metacritic_score = details.get('metacritic', {}).get('score', 'No Information')
                    recommendations_total = details.get('recommendations', {}).get('total', 'No Information')
                    release_date_info = details.get('release_date', {})
                    release_date = release_date_info.get('date', 'No Information') if release_date_info else 'No Information'

                    tags = get_steam_tags(app_id)

                    game_details = {
                        'App ID': app_id,
                        'Game Name': details['name'],
                        'Type': details['type'],
                        'Developer': details.get('developers', ['No Information']),
                        'Publisher': details.get('publishers', ['No Information']),
                        'Is Free': is_free,
                        'Price': price,
                        'Age Rating': details.get('required_age', 'N/A'),
                        'Detailed Description': detailed_description,
                        'Short Description': short_description,
                        'About the Game': about_game,
                        'Minimum Requirements': minimal_requirements,
                        'Recommended Requirements': recommended_requirements,
                        'Metacritic': metacritic_score,
                        'Categories': details.get('categories', []),
                        'Tags': tags,
                        'Genres': details.get('genres', []),
                        'Recommendations': recommendations_total,
                        'Release Date': release_date
                    }

                    cleaned_game_details = clean_json_data(game_details)
                    processed_game = game_data_to_vector(cleaned_game_details, all_tags, all_genres)
                    append_to_jsonl_file("steam_games_processed_vector_part", processed_game)
                    merge_jsonl_parts("steam_games_processed_vector_part")
                    try:
                        insert_data_from_object([processed_game], silent = True)
                        total_inserted_counter[0] += 1
                        download_logger.info("New object successfully inserted into the database.")
                    except Exception as e:
                        download_logger.error(f"Failed to insert new object into the database: {e}")

                else:
                    download_logger.warning(f"Failed to fetch details or object is not a game: app_id: {app_id}")

            finally:
                if app_id is not None:
                    game_list = [g for g in game_list if g['appid'] != app_id]
                    save_update_list(game_list, file_path_list)
                iteration_count += 1
                time.sleep(0.5)

        get_id_from_error()
        log_end_of_insert_session(total_inserted_counter)
        merge_jsonl_parts("steam_games_processed_vector_part")

    finally:
        close_connection_pool()

file_path_list = os.path.join(base_path, "Data/DownloadList", 'steam_game_list_to_update.json')
download_steam_games(file_path_list)
