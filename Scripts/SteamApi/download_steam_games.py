import json
import requests
import time
import logging
import os
import signal
import re
from datetime import datetime
from bs4 import BeautifulSoup
from langdetect import detect, DetectorFactory
from typing import Any, Dict, List, Optional, Union

DetectorFactory.seed = 0

stop_requested: bool = False
base_path: str = '../GameRecommendation'

def signal_handler(sig: int, frame: Any) -> None:
    global stop_requested
    stop_requested = True

signal.signal(signal.SIGINT, signal_handler)

if not os.path.exists(base_path + "/Scripts/Logs/Download"):
    os.makedirs(base_path + "/Scripts/Logs/Download")

current_time: str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
log_file_path: str = os.path.join(base_path + "/Logs/Download", f'downloaded_games_{current_time}.log')
error_log_path: str = os.path.join(base_path + "/Logs/Download", 'error_id.log')
file_path_list: str = os.path.join(base_path + "/Data/IDList", 'steam_game_list_to_update.json')
file_path_processed: str = os.path.join(base_path + "/Data/GamesData", 'steam_games_processed_part11.json')

logging.basicConfig(level = logging.INFO, format = '%(asctime)s - %(levelname)s - %(message)s', filename = log_file_path, filemode = 'w')

error_logger: logging.Logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_handler: logging.FileHandler = logging.FileHandler(error_log_path, mode = 'a')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

def get_app_details(app_id: int) -> Optional[Dict[str, Any]]:
    url: str = f'http://store.steampowered.com/api/appdetails?appids={app_id}&l=english'
    try:
        response: requests.Response = requests.get(url)
        app_data: Dict[str, Any] = response.json()

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

def get_steam_tags(app_id: int) -> List[str]:
    url: str = f"https://store.steampowered.com/app/{app_id}/?l=english"
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response: requests.Response = requests.get(url, headers = headers)

    if response.status_code == 200:
        soup: BeautifulSoup = BeautifulSoup(response.text, 'html.parser')
        tags: List[str] = [tag.text.strip() for tag in soup.select('.app_tag')]

        if tags and tags[-1] == '+':
            tags.pop()

        return tags if tags else ["No tags for game"]
    else:
        logging.warning(f"Failed to access the Steam page for app_id: {app_id}. Status: {response.status_code}")
        return ["No tags for game because of error"]

def remove_html_tags(text: str) -> str:
    clean: re.Pattern = re.compile('<.*?>')
    text_without_html: str = re.sub(clean, ' ', text)

    patterns_to_remove: List[str] = [r'&quot;', r'!-&quot;', r'\?&quot;', r'!-&quot;', r'&amp;', r'&gt;', r'&lt;']
    for pattern in patterns_to_remove:
        text_without_html = re.sub(pattern, '', text_without_html)

    return re.sub(r'\s+', ' ', text_without_html).strip()

def clean_json_data(json_data: Any) -> Any:
    if isinstance(json_data, dict):
        return {key: clean_json_data(value) for key, value in json_data.items()}
    elif isinstance(json_data, list):
        return [clean_json_data(item) for item in json_data]
    elif isinstance(json_data, str):
        return remove_html_tags(json_data)
    else:
        return json_data

def save_remaining_games(game_list: List[Dict[str, Any]], processed_games: List[Dict[str, Any]], file_path_list: str) -> None:
    remaining_games: List[Dict[str, Any]] = [game for game in game_list if game not in processed_games]
    with open(file_path_list, 'w', encoding = 'utf-8') as file:
        json.dump(remaining_games, file, ensure_ascii = False, indent = 4)

def is_english(text: str) -> bool:
    try:
        return detect(text) == 'en'
    except Exception:
        return False

def download_steam_games(max_iterations: int = 90000) -> None:
    processed_games: List[Dict[str, Any]] = []
    iteration_count: int = 0

    with open(file_path_list, 'r', encoding = 'utf-8') as file:
        game_list: List[Dict[str, Any]] = json.load(file)

    try:
        with open(file_path_processed, 'r', encoding = 'utf-8') as file:
            existing_games: List[Dict[str, Any]] = json.load(file)
    except FileNotFoundError:
        existing_games = []

    for game in game_list:
        if iteration_count >= max_iterations or stop_requested:
            if stop_requested:
                logging.info('Stop requested. Finishing current iteration before exiting...')
            else:
                logging.info(f"Stopping process after {max_iterations} iteration to avoid IP block from SteamApi.")
            break

        app_id: int = game['appid']
        details: Optional[Dict[str, Any]] = get_app_details(app_id)

        if details:
            if details.get('type') == 'game':
                logging.info(f"Processed game: {details.get('name', 'No name')} (app_id: {app_id})")

                detailed_description: str = details.get('detailed_description', '')
                short_description: str = details.get('short_description', '')
                about_game: str = details.get('about_the_game', '')

                if not (is_english(detailed_description) or is_english(short_description) or is_english(about_game) or is_english(details['name'])):
                    logging.info(f"Skipping app_id: {app_id} because description is not in English.")
                    processed_games.append(game)
                    save_remaining_games(game_list, processed_games, file_path_list)
                    iteration_count += 1
                    continue

                is_free: bool = details.get('is_free', False)
                price_overview: Dict[str, Any] = details.get('price_overview', {})
                price: str = price_overview.get('final_formatted', 'N/A') if price_overview else 'N/A'
                pc_requirements_data: Union[List[Dict[str, Any]], Dict[str, Any]] = details.get('pc_requirements', [])
                pc_requirements: Dict[str, Any] = pc_requirements_data[0] if isinstance(pc_requirements_data, list) and pc_requirements_data else pc_requirements_data
                
                minimal_requirements: str = 'No information'
                recommended_requirements: str = 'No information'

                if isinstance(pc_requirements, dict):
                    minimal_requirements = pc_requirements.get('minimum', 'No information')
                    recommended_requirements = pc_requirements.get('recommended', 'No information')

                metacritic_score: Union[int, str] = details.get('metacritic', {}).get('score', 'No Information')
                recommendations_total: Union[int, str] = details.get('recommendations', {}).get('total', 'No Information')
                release_date_info: Dict[str, str] = details.get('release_date', {})
                release_date: str = release_date_info.get('date', 'No Information') if release_date_info else 'No Information'

                tags: List[str] = get_steam_tags(app_id)

                game_details: Dict[str, Any] = {
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

                cleaned_game_details: Dict[str, Any] = clean_json_data(game_details)
                existing_games.append(cleaned_game_details)

                with open(file_path_processed, 'w', encoding = 'utf-8') as file:
                    json.dump(existing_games, file, ensure_ascii = False, indent = 4)

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

download_steam_games()
