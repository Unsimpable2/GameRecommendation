import re
import os
import json
import time
import signal
import logging
import requests
from glob import glob
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

stop_requested = False
base_path = '../GameRecommendation'

def signal_handler(sig, frame):
    global stop_requested
    stop_requested = True

signal.signal(signal.SIGINT, signal_handler)

if not os.path.exists(base_path + "/Scripts/Logs/Download"):
    os.makedirs(base_path + "/Scripts/Logs/Download")

current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
log_file_path = os.path.join(base_path + "/Logs/Download", f'downloaded_games_{current_time}.log')
error_log_path = os.path.join(base_path + "/Logs/Download", 'error_id.log')
data_directory = os.path.join(base_path, "Data/GamesData")
os.makedirs(data_directory, exist_ok = True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename = log_file_path, filemode = 'w')

error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler(error_log_path, mode = 'a')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

def get_last_json_file(directory):
    json_files = glob(os.path.join(directory, "steam_games_processed_part*.json"))
    if not json_files:
        return None

    file_numbers = [
        int(re.search(r"steam_games_processed_part(\d+).json", f).group(1))
        for f in json_files if re.search(r"steam_games_processed_part(\d+).json", f)
    ]
    if not file_numbers:
        return None

    max_file_number = max(file_numbers)
    return os.path.join(directory, f"steam_games_processed_part{max_file_number}.json")

def load_json_file(file_path):
    with open(file_path, "r", encoding = "utf-8") as f:
        return json.load(f)

def save_json_file(data, file_path):
    with open(file_path, "w", encoding = "utf-8") as f:
        json.dump(data, f, ensure_ascii = False, indent = 4)

def append_to_json_file(directory, new_object):
    last_file = get_last_json_file(directory)

    if last_file and os.path.exists(last_file):
        data = load_json_file(last_file)
        current_count = len(data)
    else:
        data = []
        current_count = 0

    if current_count >= 10000:
        save_json_file(data, last_file)

        if last_file:
            match = re.search(r"steam_games_processed_part(\d+).json", last_file)
            if match:
                file_number = int(match.group(1)) + 1
            else:
                raise ValueError(f"Could not extract file number from filename: {last_file}")
        else:
            file_number = 1

        new_file = os.path.join(directory, f"steam_games_processed_part{file_number}.json")
        save_json_file([new_object], new_file)
    else:
        data.append(new_object)
        save_json_file(data, last_file)

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
            logging.info(f'Error for app_id: {app_id} has been logged in error_id.log')
        else:
            logging.error(f'Error while fetching data for app_id: {app_id} - {e}')
        return None
    except Exception as e:
        logging.error(f'Error while fetching data for app_id: {app_id} - {e}')
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
    with open(file_path_list, 'r', encoding = 'utf-8') as file:
        game_list = json.load(file)

    iteration_count = 0
    for game in game_list:
        if iteration_count >= max_iterations or stop_requested:
            if stop_requested:
                logging.info('Stop requested. Finishing current iteration before exiting...')
            break

        app_id = game['appid']
        details = get_app_details(app_id)

        if details and details.get('type') == 'game':
            logging.info(f"Processed game: {details.get('name', 'No name')} (app_id: {app_id})")

            detailed_description = details.get('detailed_description', '')
            short_description = details.get('short_description', '')
            about_game = details.get('about_the_game', '')

            if not (is_english(detailed_description) or is_english(short_description) or is_english(about_game) or is_english(details['name'])):
                logging.info(f"Skipping app_id: {app_id} because description is not in English.")
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
            append_to_json_file(data_directory, cleaned_game_details)
        else:
            logging.warning(f"Failed to fetch details or object is not a game: app_id: {app_id}")

        iteration_count += 1
        time.sleep(0.5)

file_path_list = os.path.join(base_path, "Data/DownloadList", 'steam_game_list_to_update.json')
download_steam_games(file_path_list)
